"""
LiveKit SIP Agent Service

Architecture:
  Twilio (PSTN call) → SIP trunk → LiveKit SIP service → WebRTC room
  → AI Agent participant → Sarvam STT → LLM → Sarvam TTS → LiveKit playback

This module implements a LiveKit Agents-based voice AI agent that:
  1. Joins a LiveKit room as a participant
  2. Receives caller audio via WebRTC (originating from SIP/Twilio)
  3. Runs Sarvam streaming STT on the caller audio
  4. Generates LLM responses using Sarvam-m
  5. Converts responses to speech via Sarvam streaming TTS
  6. Plays audio back through LiveKit to the caller

Usage:
  - For outbound calls: POST /api/v1/calls/test-livekit-sip
    → Creates a LiveKit room, dispatches the agent, places outbound SIP call
  - For inbound calls: Configure LiveKit dispatch rules to route to this agent
"""
import asyncio
import json
import logging
import os
import uuid
from typing import Optional, Dict

from config.config import get_config

# Configure logging for child process (livekit-agents spawns subprocesses)
# Write to BOTH console and a log file so we can always inspect after a call
_log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "agent_session.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_log_file, mode="a", encoding="utf-8"),
    ],
    force=True,  # Override any existing config in child process
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
config = get_config()

# ---------------------------------------------------------------------------
# Lazy imports – these are optional heavy dependencies
# ---------------------------------------------------------------------------
try:
    from livekit import agents, api, rtc
    from livekit.agents import AgentSession, Agent
    LIVEKIT_AGENTS_AVAILABLE = True
except ImportError:
    LIVEKIT_AGENTS_AVAILABLE = False

try:
    from sarvamai import AsyncSarvamAI
    SARVAM_ASYNC_AVAILABLE = True
except ImportError:
    SARVAM_ASYNC_AVAILABLE = False

try:
    from google import genai
    from google.genai import types as genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    GOOGLE_GENAI_AVAILABLE = False


# ---------------------------------------------------------------------------
# Sarvam STT/TTS helpers (streaming via AsyncSarvamAI websockets)
# ---------------------------------------------------------------------------


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output. Handles unclosed tags."""
    import re
    if not text:
        return ""

    # Case 1: Complete <think>...</think> blocks — remove them
    clean = re.sub(r'(?is)<think>.*?</think>\s*', '', text).strip()
    if clean and '<think>' not in clean.lower():
        return clean

    # Case 2: Has </think> but regex above didn't fully clean
    if '</think>' in text.lower():
        parts = re.split(r'</think>', text, flags=re.IGNORECASE)
        after = parts[-1].strip()
        if after:
            return after

    # Case 3: Has <think> but NO </think> (model never closed the tag)
    # Take text before <think> if any; otherwise return empty
    idx = text.lower().find('<think>')
    if idx >= 0:
        before = text[:idx].strip()
        return before  # empty if response starts with <think>

    # Case 4: No think tags at all
    return text.strip()


class SarvamStreamingPipeline:
    """
    Manages Sarvam STT + TTS for a LiveKit agent's audio loop.

    Uses REST APIs instead of websockets for TTS (websocket connections
    are unstable inside livekit-agents' spawned subprocess on Windows).
    STT uses buffered REST calls for reliability.
    """

    def __init__(self, api_key: str, language_code: str = "hi-IN"):
        self.api_key = api_key
        self.language_code = language_code
        self.tts_language = language_code if language_code != "en-US" else "en-IN"
        self.tts_speaker = "aditya"
        self._client: Optional[AsyncSarvamAI] = None
        self._gemini_client = None
        self._gemini_disabled = False  # Set True on 429 to skip wasted requests
        # Accumulate PCM chunks for batch STT
        self._audio_buffer = bytearray()
        self._BUFFER_FLUSH_BYTES = 32000  # 1 second of 16kHz mono 16-bit

    async def connect(self):
        """Initialize the Sarvam async client and Gemini client."""
        self._client = AsyncSarvamAI(api_subscription_key=self.api_key)
        # Initialize Google Gemini client for LLM
        google_api_key = config.GOOGLE_API_KEY
        if google_api_key and GOOGLE_GENAI_AVAILABLE:
            self._gemini_client = genai.Client(api_key=google_api_key)
            logger.info("[LLM] Google Gemini client initialized")
        else:
            logger.warning("[LLM] Google Gemini not available, falling back to Sarvam LLM")

    async def close(self):
        """No persistent connections to close."""
        pass

    async def transcribe_chunk(self, audio_b64: str) -> Optional[str]:
        """Accumulate audio and transcribe via REST when buffer is full."""
        import base64
        self._audio_buffer.extend(base64.b64decode(audio_b64))
        if len(self._audio_buffer) < self._BUFFER_FLUSH_BYTES:
            return None
        return await self._flush_stt()

    async def flush_stt(self) -> Optional[str]:
        """Force-flush any remaining audio in the STT buffer."""
        if len(self._audio_buffer) > 0:
            return await self._flush_stt()
        return None

    async def _flush_stt(self) -> Optional[str]:
        """Send accumulated audio buffer to Sarvam STT REST API."""
        import base64, io, wave, time as _time
        if not self._client or len(self._audio_buffer) == 0:
            return None

        pcm_data = bytes(self._audio_buffer)
        audio_duration_ms = len(pcm_data) / 32  # 16kHz * 2 bytes = 32 bytes/ms
        self._audio_buffer.clear()

        # Wrap raw PCM in a WAV envelope (Sarvam REST STT expects WAV)
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(pcm_data)
        wav_bytes = wav_buf.getvalue()

        try:
            t0 = _time.perf_counter()
            resp = await self._client.speech_to_text.transcribe(
                file=wav_bytes,
                language_code=self.language_code,
                model="saaras:v3",
            )
            stt_ms = (_time.perf_counter() - t0) * 1000
            transcript = (getattr(resp, "transcript", "") or "").strip()
            logger.info(f"[TIMING] STT: {stt_ms:.0f}ms for {audio_duration_ms:.0f}ms audio → '{transcript[:60]}'")
            return transcript or None
        except Exception as e:
            logger.error(f"STT REST error: {e}")
            return None

    async def synthesize(self, text: str):
        """Convert text to speech via REST API. Yields base64-encoded PCM chunks."""
        import base64, time as _time
        if not self._client:
            return
        try:
            t0 = _time.perf_counter()
            resp = await self._client.text_to_speech.convert(
                text=text,
                target_language_code=self.tts_language,
                speaker=self.tts_speaker,
                model="bulbul:v3",
                output_audio_codec="linear16",
                speech_sample_rate=16000,
                enable_preprocessing=True,
            )
            tts_ms = (_time.perf_counter() - t0) * 1000
            total_bytes = sum(len(base64.b64decode(a)) for a in (resp.audios or []))
            logger.info(f"[TIMING] TTS: {tts_ms:.0f}ms for {len(text)} chars → {total_bytes/32000:.1f}s audio")
            for audio_b64 in (resp.audios or []):
                yield audio_b64
        except Exception as e:
            logger.error(f"TTS REST error: {e}")

    def _convert_messages_for_gemini(self, messages: list):
        """Convert OpenAI-style messages to Gemini format.
        Returns (system_instruction, contents) tuple."""
        system_instruction = None
        contents = []
        for msg in messages:
            role = msg["role"]
            text = msg["content"]
            if role == "system":
                system_instruction = text
            elif role == "user":
                contents.append(genai_types.Content(
                    role="user",
                    parts=[genai_types.Part(text=text)],
                ))
            elif role == "assistant":
                contents.append(genai_types.Content(
                    role="model",
                    parts=[genai_types.Part(text=text)],
                ))
        return system_instruction, contents

    async def llm_chat(self, messages: list, max_tokens: int = 512, temperature: float = 0.2) -> Optional[str]:
        """Call LLM via Google Gemini (preferred) or Sarvam fallback."""
        import time as _time

        # --- Google Gemini path ---
        if self._gemini_client and not self._gemini_disabled:
            try:
                t0 = _time.perf_counter()
                system_instruction, contents = self._convert_messages_for_gemini(messages)
                resp = await self._gemini_client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                )
                llm_ms = (_time.perf_counter() - t0) * 1000
                raw = resp.text or ""
                logger.info(f"[TIMING] LLM (Gemini): {llm_ms:.0f}ms, raw={len(raw)} chars")
                logger.info(f"[LLM] Gemini response ({len(raw)} chars): {raw[:120]}")
                clean = raw.strip()
                return clean or None
            except Exception as e:
                logger.error(f"[LLM] Gemini error: {type(e).__name__}: {e}")
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    self._gemini_disabled = True
                    logger.warning("[LLM] Gemini quota exhausted — disabled for this session")
                # Fall through to Sarvam

        # --- Sarvam fallback ---
        if not self._client:
            return None
        try:
            t0 = _time.perf_counter()
            resp = await self._client.chat.completions(
                messages=messages,
                model="sarvam-m",
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort="low",
            )
            llm_ms = (_time.perf_counter() - t0) * 1000
            raw = (resp.choices[0].message.content or "") if resp.choices else ""
            logger.info(f"[TIMING] LLM (Sarvam): {llm_ms:.0f}ms, raw={len(raw)} chars")
            logger.info(f"[LLM] Sarvam raw ({len(raw)} chars): {raw[:120]}...")

            clean = _strip_think_tags(raw)
            if clean:
                logger.info(f"[LLM] Clean response: {clean[:120]}")
            else:
                logger.warning(f"[LLM] Empty after sanitize. Raw={raw[:200]}")
            return clean or None
        except Exception as e:
            logger.error(f"[LLM] Sarvam error: {type(e).__name__}: {e}")
            return None

    async def llm_chat_streaming(self, messages: list, max_tokens: int = 512, temperature: float = 0.2):
        """
        Stream LLM tokens and yield complete sentences as they form.
        Yields (sentence, is_last) tuples for pipelined TTS.
        Uses Google Gemini (preferred) with Sarvam fallback.
        """
        import re, time as _time

        t0 = _time.perf_counter()
        first_sentence_time = None
        sentence_delimiters = re.compile(r'(?<=[.!?।])\s+')

        # --- Google Gemini streaming path ---
        if self._gemini_client and not self._gemini_disabled:
            try:
                system_instruction, contents = self._convert_messages_for_gemini(messages)
                raw_stream = ""
                buffer = ""

                async for chunk in await self._gemini_client.aio.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                ):
                    token = chunk.text or ""
                    if not token:
                        continue
                    raw_stream += token
                    buffer += token

                    # Try to yield complete sentences as they form
                    parts = sentence_delimiters.split(buffer)
                    if len(parts) > 1:
                        for sentence in parts[:-1]:
                            sentence = sentence.strip()
                            if sentence:
                                if first_sentence_time is None:
                                    first_sentence_time = (_time.perf_counter() - t0) * 1000
                                    logger.info(f"[TIMING] LLM first sentence ready: {first_sentence_time:.0f}ms")
                                yield (sentence, False)
                        buffer = parts[-1]

                # Yield remaining buffer
                remaining = buffer.strip()
                if remaining:
                    if first_sentence_time is None:
                        first_sentence_time = (_time.perf_counter() - t0) * 1000
                        logger.info(f"[TIMING] LLM first sentence ready: {first_sentence_time:.0f}ms")
                    yield (remaining, True)

                llm_ms = (_time.perf_counter() - t0) * 1000
                clean = raw_stream.strip()
                print(f"[AGENT] LLM streaming (Gemini): {llm_ms:.0f}ms, {len(clean)} chars: {clean[:80]}", flush=True)
                logger.info(f"[TIMING] LLM streaming (Gemini): {llm_ms:.0f}ms, raw={len(raw_stream)} chars, clean={len(clean)} chars")
                logger.info(f"[LLM] Gemini streamed: {clean[:120]}")
                return

            except Exception as e:
                print(f"[AGENT] Gemini streaming error: {type(e).__name__}: {e}", flush=True)
                logger.error(f"[LLM] Gemini streaming error: {type(e).__name__}: {e}")
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    self._gemini_disabled = True
                    logger.warning("[LLM] Gemini quota exhausted — disabled for this session")
                # Fall through to Sarvam

        # --- Sarvam fallback streaming path ---
        if not self._client:
            return

        raw_stream = ""
        try:
            stream = await self._client.chat.completions(
                messages=messages,
                model="sarvam-m",
                max_tokens=max_tokens,
                temperature=temperature,
                reasoning_effort="low",
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                token = delta.content or ""
                if token:
                    raw_stream += token

            clean = _strip_think_tags(raw_stream)

            llm_ms = (_time.perf_counter() - t0) * 1000
            print(f"[AGENT] LLM streaming (Sarvam): {llm_ms:.0f}ms, clean={len(clean)} chars: {clean[:80]}", flush=True)
            logger.info(f"[TIMING] LLM streaming (Sarvam): {llm_ms:.0f}ms, raw={len(raw_stream)} chars, clean={len(clean)} chars")

            if not clean:
                print(f"[AGENT] LLM empty! Raw: {raw_stream[:150]}", flush=True)
                logger.warning(f"[LLM] Streaming returned empty after stripping think. Raw: {raw_stream[:200]}")
                return

            logger.info(f"[LLM] Sarvam streamed: {clean[:120]}")

            sentences = sentence_delimiters.split(clean)
            for i, sentence in enumerate(sentences):
                sentence = sentence.strip()
                if sentence:
                    is_last = (i == len(sentences) - 1)
                    if first_sentence_time is None:
                        first_sentence_time = (_time.perf_counter() - t0) * 1000
                        logger.info(f"[TIMING] LLM first sentence ready: {first_sentence_time:.0f}ms")
                    yield (sentence, is_last)

        except Exception as e:
            print(f"[AGENT] LLM streaming error: {type(e).__name__}: {e}", flush=True)
            logger.error(f"[LLM] Streaming error: {type(e).__name__}: {e}")
            return


# ---------------------------------------------------------------------------
# LiveKit SIP Agent Service
# ---------------------------------------------------------------------------

class LiveKitSIPAgentService:
    """
    Orchestrates outbound (and inbound) calls via LiveKit SIP trunks.

    Outbound flow:
      1. create_outbound_call()  – creates room, dispatches agent, dials phone
      2. The LiveKit agent process (run_agent_worker) handles the room session
    """

    def __init__(self):
        self.livekit_url = config.LIVEKIT_URL
        self.api_key = config.LIVEKIT_API_KEY
        self.api_secret = config.LIVEKIT_API_SECRET
        self.sip_trunk_id = config.LIVEKIT_SIP_TRUNK_ID
        self.sarvam_api_key = config.SERVAM_API_KEY

    @property
    def is_configured(self) -> bool:
        return bool(self.livekit_url and self.api_key and self.api_secret)

    # ---- outbound call via LiveKit SIP ----

    async def create_outbound_call(
        self,
        phone_number: str,
        customer_name: str = "Guest",
        customer_id: str = "",
        language: str = "en",
        total_visits: int = 0,
        loyalty_score: float = 0.0,
        last_stay_date: Optional[str] = None,
        preferred_room_type: Optional[str] = None,
    ) -> Dict:
        """
        Place an outbound call through LiveKit SIP.

        Steps:
          1. Create a unique LiveKit room
          2. Dispatch the AI agent into the room
          3. Create a SIP participant (dials the phone number)

        Returns dict with room_name, participant info, and status.
        """
        if not LIVEKIT_AGENTS_AVAILABLE:
            raise RuntimeError("livekit-agents SDK not installed. pip install livekit-agents livekit-api livekit")

        if not self.is_configured:
            raise RuntimeError(
                "LiveKit not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET, and LIVEKIT_SIP_TRUNK_ID env vars."
            )

        room_name = f"sip-call-{uuid.uuid4().hex[:10]}"
        participant_identity = phone_number

        metadata = json.dumps({
            "phone_number": phone_number,
            "customer_name": customer_name,
            "customer_id": customer_id,
            "language": language,
            "total_visits": total_visits,
            "loyalty_score": loyalty_score,
            "last_stay_date": last_stay_date,
            "preferred_room_type": preferred_room_type,
        })

        lkapi = api.LiveKitAPI(
            url=self.livekit_url,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        try:
            # 1. Dispatch the agent into the room
            await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="hotel-rm-sip-agent",
                    room=room_name,
                    metadata=metadata,
                )
            )
            logger.info(f"Agent dispatched to room {room_name}")

            # 2. Place the SIP outbound call
            from livekit.protocol.sip import CreateSIPParticipantRequest

            sip_request = CreateSIPParticipantRequest(
                sip_trunk_id=self.sip_trunk_id,
                sip_call_to=phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=customer_name,
                krisp_enabled=True,
                wait_until_answered=True,
            )

            sip_info = await lkapi.sip.create_sip_participant(sip_request)
            logger.info(f"SIP participant created: {sip_info}")

            return {
                "status": "call_placed",
                "room_name": room_name,
                "sip_participant_id": getattr(sip_info, "participant_id", ""),
                "phone_number": phone_number,
                "customer_name": customer_name,
            }

        except Exception as e:
            logger.error(f"Failed to create outbound SIP call: {e}")
            raise
        finally:
            await lkapi.aclose()

    # ---- outbound call via Exotel SIP trunk ----

    async def create_outbound_call_exotel(
        self,
        phone_number: str,
        customer_name: str = "Guest",
        customer_id: str = "",
        language: str = "en",
        total_visits: int = 0,
        loyalty_score: float = 0.0,
        last_stay_date: Optional[str] = None,
        preferred_room_type: Optional[str] = None,
    ) -> Dict:
        """
        Place an outbound call through LiveKit SIP using Exotel trunk.

        Same architecture as Twilio SIP but routes through Exotel PSTN:
          1. Create a unique LiveKit room
          2. Dispatch the AI agent into the room
          3. Create a SIP participant via Exotel trunk (dials the phone number)

        Returns dict with room_name, participant info, and status.
        """
        if not LIVEKIT_AGENTS_AVAILABLE:
            raise RuntimeError("livekit-agents SDK not installed. pip install livekit-agents livekit-api livekit")

        exotel_trunk_id = config.EXOTEL_SIP_TRUNK_ID
        if not self.is_configured or not exotel_trunk_id:
            raise RuntimeError(
                "Exotel SIP not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET, and EXOTEL_SIP_TRUNK_ID env vars."
            )

        room_name = f"exotel-call-{uuid.uuid4().hex[:10]}"
        participant_identity = phone_number

        metadata = json.dumps({
            "phone_number": phone_number,
            "customer_name": customer_name,
            "customer_id": customer_id,
            "language": language,
            "total_visits": total_visits,
            "loyalty_score": loyalty_score,
            "last_stay_date": last_stay_date,
            "preferred_room_type": preferred_room_type,
            "sip_provider": "exotel",
        })

        lkapi = api.LiveKitAPI(
            url=self.livekit_url,
            api_key=self.api_key,
            api_secret=self.api_secret,
        )

        try:
            # 1. Dispatch the agent into the room
            await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    agent_name="hotel-rm-sip-agent",
                    room=room_name,
                    metadata=metadata,
                )
            )
            logger.info(f"Agent dispatched to Exotel room {room_name}")

            # 2. Place the SIP outbound call via Exotel trunk
            from livekit.protocol.sip import CreateSIPParticipantRequest

            sip_request = CreateSIPParticipantRequest(
                sip_trunk_id=exotel_trunk_id,
                sip_call_to=phone_number,
                room_name=room_name,
                participant_identity=participant_identity,
                participant_name=customer_name,
                krisp_enabled=True,
                wait_until_answered=True,
            )

            sip_info = await lkapi.sip.create_sip_participant(sip_request)
            logger.info(f"Exotel SIP participant created: {sip_info}")

            return {
                "status": "call_placed",
                "room_name": room_name,
                "sip_participant_id": getattr(sip_info, "participant_id", ""),
                "phone_number": phone_number,
                "customer_name": customer_name,
                "sip_provider": "exotel",
            }

        except Exception as e:
            logger.error(f"Failed to create Exotel outbound SIP call: {e}")
            raise
        finally:
            await lkapi.aclose()


# ---------------------------------------------------------------------------
# Agent entry-point  (run as: python -m livekit.agents start src.services.livekit_sip_agent)
# ---------------------------------------------------------------------------

def _build_system_prompt(customer_name: str, language: str, total_visits: int = 0,
                         loyalty_score: float = 0.0, last_stay_date: str = None,
                         preferred_room_type: str = None) -> str:
    _lang_label_map = {
        "en": "English", "hi": "Hindi", "ta": "Tamil",
        "te": "Telugu", "ml": "Malayalam", "kn": "Kannada",
        "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi", "bn": "Bengali",
    }
    lang_prefix = language.split("-")[0] if "-" in language else language
    lang_label = _lang_label_map.get(lang_prefix, "English")
    last_stay_info = f"last stayed with us in {last_stay_date}" if last_stay_date else "haven't visited recently"
    room_info = f"Their preferred room type is {preferred_room_type}." if preferred_room_type else ""

    # Determine discount based on engagement
    if total_visits >= 5:
        discount = 20
    elif total_visits >= 2:
        discount = 15
    else:
        discount = 10

    return f"""You are a warm, friendly relationship manager at Beacon Hotel. Your name is Raj.
You have placed an OUTBOUND call to {customer_name} — YOU called THEM.

Customer Profile:
- Name: {customer_name}
- Total Visits: {total_visits}
- Loyalty Score: {loyalty_score}
- Last Stay: {last_stay_info}
{room_info}

IMPORTANT CONTEXT: This is an outbound relationship management call. You called the customer to check in, 
ask about their experience, and invite them back with a special offer.

LANGUAGE RULES (MANDATORY):
1. For the FIRST response, you MUST reply in {lang_label}. This is the language the caller has chosen.
2. Always reply in the same language the user just used. If the user speaks Tamil, reply in Tamil. If the user speaks Hindi, reply in Hindi. If the user speaks English, reply in English. Do NOT mix languages. Do NOT translate. Do NOT explain your language choice.
3. If the user switches language, you must switch your reply to match their new language for that turn.
4. Never reply in both languages in the same turn.

RESPONSE RULES:
1. Keep responses SHORT: 1-2 sentences max.
2. ALWAYS respond to what the customer just said — never ignore their words.
3. If they ask why you called: explain you're calling to check in and share a special offer.
4. If they mention a bad experience: apologize sincerely, offer a 30% recovery discount.
5. NEVER say "How can I help you?" — YOU called THEM, not the other way around.
6. Do NOT include any thinking, reasoning, or internal monologue in your response. Just give the direct reply.

CONVERSATION FLOW:
- After greeting, ask: "How have you been? Are you planning to visit us again soon?"
- If YES: "Wonderful! As a valued guest, we have an exclusive {discount}% loyalty discount for your next stay."
- If NO / not sure: "No worries! Whenever you plan, we have a special {discount}% discount waiting for you."
- After offering discount: Thank them warmly and say goodbye. Use phrases like "Take care" or "Goodbye" to close.
- IMPORTANT: Once you've offered the discount and they acknowledge it, end the conversation. Say "Thank you so much, {customer_name}. Take care and goodbye sir!" and STOP.

Do NOT wrap your response in <think> tags or include any internal reasoning. Output ONLY the spoken reply.

Be warm, personal, and genuine — like talking to a friend, not reading a script."""


async def _run_sip_session(ctx: "agents.JobContext"):
    """
    Called when the agent is dispatched into a LiveKit room.
    Handles the full STT → LLM → TTS loop for a SIP caller.
    """
    import base64, wave, os, time

    # Connect to the LiveKit room (required before any room interaction)
    await ctx.connect(auto_subscribe="subscribe_all")
    print("[AGENT] Connected to room", flush=True)
    logger.info("Agent connected to room")

    # Parse metadata passed via dispatch
    meta = json.loads(ctx.job.metadata or "{}")
    phone_number = meta.get("phone_number", "")
    customer_name = meta.get("customer_name", "Guest")
    customer_id = meta.get("customer_id", "")
    language = meta.get("language", "en")
    total_visits = meta.get("total_visits", 0)
    loyalty_score = meta.get("loyalty_score", 0.0)
    last_stay_date = meta.get("last_stay_date")
    preferred_room_type = meta.get("preferred_room_type")

    # Map language to Sarvam language code
    _lang_code_map = {
        "en": "en-IN", "hi": "hi-IN", "ta": "ta-IN",
        "te": "te-IN", "ml": "ml-IN", "kn": "kn-IN",
        "mr": "mr-IN", "gu": "gu-IN", "pa": "pa-IN", "bn": "bn-IN",
    }
    lang_prefix = language.split("-")[0] if "-" in language else language
    lang_code = _lang_code_map.get(lang_prefix, language if "-" in language else "en-IN")
    system_prompt = _build_system_prompt(
        customer_name, language,
        total_visits=total_visits,
        loyalty_score=loyalty_score,
        last_stay_date=last_stay_date,
        preferred_room_type=preferred_room_type,
    )
    conversation = [{"role": "system", "content": system_prompt}]

    # Wait for the SIP participant (the phone caller) to join
    participant_identity = phone_number or None
    try:
        participant = await ctx.wait_for_participant(identity=participant_identity)
        logger.info(f"SIP participant joined: {participant.identity}")
    except Exception as e:
        logger.error(f"SIP participant did not join: {e}")
        ctx.shutdown()
        return

    # Create streaming pipeline (connect later, right before first use)
    pipeline = SarvamStreamingPipeline(api_key=config.SERVAM_API_KEY, language_code=lang_code)

    # Set up audio track subscription
    audio_stream = None
    for pub in participant.track_publications.values():
        if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
            audio_stream = rtc.AudioStream(pub.track, sample_rate=16000, num_channels=1)
            break

    if audio_stream is None:
        # Wait for audio track to be published
        track_event = asyncio.Event()
        received_track = {}

        @ctx.room.on("track_subscribed")
        def _on_track(track: rtc.Track, publication: rtc.TrackPublication, remote_participant: rtc.RemoteParticipant):
            if remote_participant.identity == participant.identity and track.kind == rtc.TrackKind.KIND_AUDIO:
                received_track["stream"] = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
                track_event.set()

        try:
            await asyncio.wait_for(track_event.wait(), timeout=15.0)
            audio_stream = received_track.get("stream")
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for audio track from SIP participant")
            await pipeline.close()
            ctx.shutdown()
            return

    if audio_stream is None:
        logger.error("No audio stream obtained")
        await pipeline.close()
        ctx.shutdown()
        return

    # Create an audio source to play TTS back into the room
    audio_source = rtc.AudioSource(sample_rate=16000, num_channels=1)
    local_track = rtc.LocalAudioTrack.create_audio_track("agent-voice", audio_source)
    await ctx.room.local_participant.publish_track(local_track)

    print(f"[AGENT] Audio loop started for {customer_name} ({phone_number})", flush=True)
    logger.info(f"Agent audio loop started for {customer_name} ({phone_number})")

    # Record incoming audio to WAV file for debugging
    audio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "audio")
    os.makedirs(audio_dir, exist_ok=True)
    ts = int(time.time())
    recording_path = os.path.join(audio_dir, f"call_{customer_id}_{ts}.wav")
    wav_file = wave.open(recording_path, "wb")
    wav_file.setnchannels(1)
    wav_file.setsampwidth(2)
    wav_file.setframerate(16000)

    # Also record agent's outbound audio
    agent_recording_path = os.path.join(audio_dir, f"agent_{customer_id}_{ts}.wav")
    agent_wav = wave.open(agent_recording_path, "wb")
    agent_wav.setnchannels(1)
    agent_wav.setsampwidth(2)
    agent_wav.setframerate(16000)
    print(f"[AGENT] Recording to: {recording_path} (caller) and {agent_recording_path} (agent)", flush=True)
    logger.info(f"[SIP] Recording caller audio to: {recording_path}")

    # Open streaming pipeline now (just before first use to avoid idle timeout)
    await pipeline.connect()

    # Send greeting — outbound RM call, introduce yourself and purpose
    _greetings = {
        "en": f"Hello {customer_name}! This is Raj calling from Beacon Hotel. Hope you're doing well! I'm just calling to check in and see how your experience has been with us.",
        "hi": f"नमस्ते {customer_name}! मैं Raj, Beacon Hotel से बात कर रहा हूँ। उम्मीद है आप अच्छे हैं! बस आपसे बात करने के लिए कॉल किया, जानना चाहता था कि हमारे साथ आपका अनुभव कैसा रहा।",
        "ta": f"வணக்கம் {customer_name}! நான் Raj, Beacon Hotel-லிருந்து அழைக்கிறேன். நீங்கள் நலமாக இருப்பீர்கள் என்று நம்புகிறேன்! எங்களுடன் உங்கள் அனுபவம் எப்படி இருந்தது என்று தெரிந்துகொள்ள விரும்புகிறேன்.",
        "te": f"నమస్కారం {customer_name}! నేను Raj, Beacon Hotel నుండి కాల్ చేస్తున్నాను. మీరు బాగున్నారని ఆశిస్తున్నాను! మాతో మీ అనుభవం ఎలా ఉందో తెలుసుకోవాలనుకుంటున్నాను.",
        "ml": f"നമസ്കാകം {customer_name}! ഞാൻ Raj, Beacon Hotel-ൽ നിന്ന് വിളിക്കുകയാണ്. നിങ്ങൾ സുഖമായിരിക്കും എന്ന് പ്രതീക്ഷിക്കുന്നു! ഞങ്ങളുമായുള്ള നിങ്ങളുടെ അനുഭവം എങ്ങനെയായിരുന്നു എന്ന് അറിയാൻ ആഗ്രഹിക്കുന്നു.",
    }
    lang_prefix_for_greeting = language.split("-")[0] if "-" in language else language
    greeting = _greetings.get(lang_prefix_for_greeting, _greetings["en"])

    # NOTE: Don't add greeting to conversation yet — Sarvam-m requires
    # the first non-system message to be from the user. We'll inject it
    # right before the first user message.
    greeting_added_to_history = False

    # Synthesize and play greeting
    greeting_chunks = 0
    greeting_bytes = 0
    print(f"[AGENT] Synthesizing greeting: {greeting[:60]}...", flush=True)
    logger.info(f"[SIP] Synthesizing greeting TTS...")
    async for audio_b64_chunk in pipeline.synthesize(greeting):
        pcm_bytes = base64.b64decode(audio_b64_chunk)
        greeting_chunks += 1
        greeting_bytes += len(pcm_bytes)
        agent_wav.writeframes(pcm_bytes)
        # Split into 20ms frames (640 bytes at 16kHz mono 16-bit) for smooth playback
        FRAME_BYTES = 640
        for offset in range(0, len(pcm_bytes), FRAME_BYTES):
            chunk = pcm_bytes[offset:offset + FRAME_BYTES]
            if len(chunk) == 0:
                break
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=len(chunk) // 2,
            )
            await audio_source.capture_frame(frame)
    print(f"[AGENT] Greeting played: {greeting_bytes/32000:.1f}s", flush=True)
    logger.info(f"[SIP] Greeting TTS done: {greeting_chunks} chunks, {greeting_bytes} bytes ({greeting_bytes/32000:.1f}s)")

    # Call ending keywords
    AGENT_GOODBYE_KEYWORDS = ["goodbye", "good bye", "bye bye", "take care", "have a great", "have a wonderful",
                               "have a lovely", "see you soon", "looking forward to welcoming",
                               "alvida", "namaste", "dhanyavaad", "phir milenge"]
    USER_GOODBYE_KEYWORDS = ["bye", "ok bye", "thank you bye", "thanks bye", "goodbye",
                              "ok thank you", "ok thanks", "that's all", "nothing else",
                              "alvida", "dhanyavaad", "shukriya"]
    MAX_TURNS = 8  # Safety: end call after this many user turns
    turn_count = 0
    should_end_call = False

    # Main audio processing loop
    silence_frames = 0
    voice_frames = 0
    accumulated_transcript = ""
    SILENCE_THRESHOLD_FRAMES = 25  # ~1.0s at 25fps (40ms frames)
    VOICE_RMS_THRESHOLD = 10
    total_frames = 0
    voice_detected_total = 0

    try:
        async for frame_event in audio_stream:
            frame: rtc.AudioFrame = frame_event.frame

            # Convert frame to base64 PCM for Sarvam STT
            pcm_data = bytes(frame.data)
            total_frames += 1

            # Write to recording file
            wav_file.writeframes(pcm_data)

            rms = 0
            if len(pcm_data) >= 2:
                import struct
                samples = struct.unpack(f"<{len(pcm_data)//2}h", pcm_data)
                rms = (sum(s * s for s in samples) / len(samples)) ** 0.5

            if total_frames == 1:
                logger.info(f"[SIP] First audio frame received: {len(pcm_data)} bytes, rms={rms:.1f}, sr={frame.sample_rate}, ch={frame.num_channels}, spc={frame.samples_per_channel}")

            if rms > VOICE_RMS_THRESHOLD:
                voice_frames += 1
                voice_detected_total += 1
                if voice_frames == 1:
                    logger.info(f"[SIP] Voice detected (rms={rms:.1f}, total_frames={total_frames})")
                silence_frames = 0
            else:
                silence_frames += 1

            # Log progress every 250 frames (~10 seconds)
            if total_frames % 250 == 0:
                logger.info(f"[SIP] Audio loop: {total_frames} frames, voice_total={voice_detected_total}, current_voice={voice_frames}, silence={silence_frames}, stt_buf={len(pipeline._audio_buffer)}, transcript='{accumulated_transcript[:50]}'")

            # Always send audio to STT for continuous transcription
            audio_b64 = base64.b64encode(pcm_data).decode("ascii")
            partial = await pipeline.transcribe_chunk(audio_b64)
            if partial:
                logger.info(f"[SIP] STT partial: '{partial}'")
                accumulated_transcript += " " + partial

            # End-of-utterance: enough silence after some voice
            if voice_frames > 3 and silence_frames >= SILENCE_THRESHOLD_FRAMES:
                # Flush any remaining audio in the STT buffer
                final_partial = await pipeline.flush_stt()
                if final_partial:
                    accumulated_transcript += " " + final_partial

                if not accumulated_transcript.strip():
                    voice_frames = 0
                    silence_frames = 0
                    continue

                user_text = accumulated_transcript.strip()
                accumulated_transcript = ""
                voice_frames = 0
                silence_frames = 0

                import time as _time
                _turn_start = _time.perf_counter()
                print(f"[AGENT] User said: {user_text}", flush=True)
                logger.info(f"[SIP] User said: {user_text}")

                # On first user message, prepend greeting context so Sarvam-m
                # sees: system → user → (we reply). We embed the greeting in
                # the user message so the model knows what was already said.
                if not greeting_added_to_history:
                    user_text = f"[You already greeted me with: \"{greeting}\"] My response: {user_text}"
                    greeting_added_to_history = True

                turn_count += 1

                # Check if user is saying goodbye
                user_lower = user_text.lower()
                user_is_goodbye = any(kw in user_lower for kw in USER_GOODBYE_KEYWORDS)

                conversation.append({"role": "user", "content": user_text})

                # Try streaming LLM first for lower latency, fall back to non-streaming
                llm_text_full = ""
                first_audio_played = False
                streaming_failed = False

                async def _play_tts(text):
                    """Synthesize and play one sentence."""
                    async for tts_b64 in pipeline.synthesize(text):
                        tts_pcm = base64.b64decode(tts_b64)
                        agent_wav.writeframes(tts_pcm)
                        FRAME_BYTES = 640
                        for offset in range(0, len(tts_pcm), FRAME_BYTES):
                            chunk = tts_pcm[offset:offset + FRAME_BYTES]
                            if len(chunk) == 0:
                                break
                            out_frame = rtc.AudioFrame(
                                data=chunk,
                                sample_rate=16000,
                                num_channels=1,
                                samples_per_channel=len(chunk) // 2,
                            )
                            await audio_source.capture_frame(out_frame)

                try:
                    async for (sentence, is_last) in pipeline.llm_chat_streaming(conversation, max_tokens=2048):
                        llm_text_full += sentence + (" " if not is_last else "")
                        if not first_audio_played:
                            _first_audio_ms = (_time.perf_counter() - _turn_start) * 1000
                            logger.info(f"[TIMING] First audio starts at: {_first_audio_ms:.0f}ms after user stopped")
                            first_audio_played = True
                        await _play_tts(sentence)
                except Exception as stream_err:
                    print(f"[AGENT] Streaming failed: {type(stream_err).__name__}: {stream_err}", flush=True)
                    logger.error(f"[SIP] Streaming LLM failed: {type(stream_err).__name__}: {stream_err}")
                    streaming_failed = True

                # Fallback to non-streaming if streaming yielded nothing
                if not llm_text_full.strip():
                    if streaming_failed:
                        print("[AGENT] Falling back to non-streaming LLM", flush=True)
                        logger.info("[SIP] Falling back to non-streaming LLM")
                    else:
                        print("[AGENT] Streaming empty, falling back to non-streaming", flush=True)
                        logger.warning("[SIP] Streaming LLM returned empty, falling back to non-streaming")
                    llm_text_full = await pipeline.llm_chat(conversation, max_tokens=2048) or ""

                # Retry: if model spent all tokens on thinking, ask directly
                if not llm_text_full.strip():
                    logger.warning("[SIP] Both LLM paths returned only thinking. Retrying with direct prompt.")
                    print("[AGENT] Retrying LLM with direct prompt", flush=True)
                    retry_msgs = conversation.copy()
                    # Amend the last user message instead of adding a second one
                    # (API requires alternating user/assistant turns)
                    if retry_msgs and retry_msgs[-1]["role"] == "user":
                        retry_msgs[-1] = {
                            "role": "user",
                            "content": retry_msgs[-1]["content"] + "\n\n(Please respond directly in 1-2 sentences. No reasoning needed.)",
                        }
                    else:
                        retry_msgs.append({"role": "user", "content": "Please respond directly in 1-2 sentences. No reasoning needed."})
                    llm_text_full = await pipeline.llm_chat(retry_msgs, max_tokens=256) or ""

                # Last resort fallback
                if not llm_text_full.strip():
                    llm_text_full = f"I completely understand, {customer_name}. We truly value your feedback and would love to make it up to you with a special discount on your next stay."

                # If we haven't played audio yet (non-streaming path), play now
                if not first_audio_played:
                    await _play_tts(llm_text_full)

                llm_text_full = llm_text_full.strip()

                conversation.append({"role": "assistant", "content": llm_text_full})
                print(f"[AGENT] Says (turn {turn_count}): {llm_text_full}", flush=True)
                logger.info(f"[SIP] Agent says (turn {turn_count}): {llm_text_full}")

                # Check if agent response is a goodbye/closing
                agent_lower = llm_text_full.lower()
                agent_is_goodbye = any(kw in agent_lower for kw in AGENT_GOODBYE_KEYWORDS)

                if user_is_goodbye or agent_is_goodbye or turn_count >= MAX_TURNS:
                    should_end_call = True
                    reason = "user goodbye" if user_is_goodbye else ("agent goodbye" if agent_is_goodbye else f"max turns ({MAX_TURNS})")
                    logger.info(f"[SIP] Call will end after this response. Reason: {reason}")

                _total_ms = (_time.perf_counter() - _turn_start) * 1000
                logger.info(f"[TIMING] Turn {turn_count} total: {_total_ms:.0f}ms (user spoke → agent finished playing)")

                # End call if goodbye detected or max turns reached
                if should_end_call:
                    logger.info(f"[SIP] Ending call after {turn_count} turns")
                    # Brief pause so the last TTS finishes playing
                    await asyncio.sleep(1.5)
                    break

    except Exception as e:
        print(f"[AGENT] Audio loop error: {type(e).__name__}: {e}", flush=True)
        logger.error(f"SIP agent audio loop error: {e}", exc_info=True)
    finally:
        wav_file.close()
        agent_wav.close()
        print(f"[AGENT] Recordings saved: {recording_path}, {agent_recording_path}", flush=True)
        logger.info(f"[SIP] Recording saved: {recording_path} ({total_frames} frames, {turn_count} turns)")
        await pipeline.close()

        # Hang up the SIP/PSTN call by removing the SIP participant from the room.
        # This sends a SIP BYE to Twilio, which ends the phone call.
        room_name = ctx.room.name
        logger.info(f"[SIP] Hanging up call for {customer_name} in room {room_name}")
        try:
            lkapi = api.LiveKitAPI(
                url=config.LIVEKIT_URL,
                api_key=config.LIVEKIT_API_KEY,
                api_secret=config.LIVEKIT_API_SECRET,
            )
            # Remove the SIP participant (phone_number is the identity)
            await lkapi.room.remove_participant(
                api.RoomParticipantIdentity(
                    room=room_name,
                    identity=participant.identity,
                )
            )
            logger.info(f"[SIP] SIP participant {participant.identity} removed — call hung up")
            await lkapi.aclose()
        except Exception as hangup_err:
            logger.warning(f"[SIP] Could not remove SIP participant: {hangup_err}")
            # Fallback: delete the entire room to force-disconnect everyone
            try:
                await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
                logger.info(f"[SIP] Room {room_name} deleted as fallback")
                await lkapi.aclose()
            except Exception as del_err:
                logger.warning(f"[SIP] Could not delete room either: {del_err}")

        ctx.shutdown()
        logger.info(f"SIP agent session ended for {customer_name}")


# ---------------------------------------------------------------------------
# Agent worker entry-point (standalone mode)
#
# Run with:
#   python -m livekit.agents start src.services.livekit_sip_agent
#
# Or import and call run_agent_worker() from your own process.
# ---------------------------------------------------------------------------

_server = None


async def _agent_entrypoint(ctx: agents.JobContext):
    """Module-level entrypoint for the SIP agent (must be picklable)."""
    await _run_sip_session(ctx)


def _get_agent_server():
    """Lazily create the AgentServer singleton."""
    global _server
    if _server is not None:
        return _server

    if not LIVEKIT_AGENTS_AVAILABLE:
        raise RuntimeError("livekit-agents SDK not installed")

    server = agents.AgentServer()
    server.rtc_session(_agent_entrypoint, agent_name="hotel-rm-sip-agent")

    _server = server
    return server


def run_agent_worker():
    """
    Start the LiveKit agent worker (blocking).
    Typically run in a separate process / container.

    Usage (CLI):
        python -m livekit.agents dev src.services.livekit_sip_agent
    Or:
        python run_agent.py
    """
    server = _get_agent_server()
    agents.cli.run_app(server)


# Module-level service instance for use from FastAPI endpoints
livekit_sip_service = LiveKitSIPAgentService()
