"""
LiveKit Streaming Bridge Service

Workflow:
LiveKit audio stream -> Sarvam Streaming STT -> LLM -> Sarvam Streaming TTS
"""
import asyncio
import json
import logging
from typing import Dict, Optional

from fastapi import WebSocket

from src.services.servam_service import ServamService

logger = logging.getLogger(__name__)

try:
    from sarvamai import AsyncSarvamAI
    SARVAM_ASYNC_AVAILABLE = True
except ImportError:
    SARVAM_ASYNC_AVAILABLE = False


class LiveKitStreamingService:
    """Bridge LiveKit-style websocket audio streams with Sarvam streaming APIs."""

    def __init__(self):
        self.servam = ServamService()
        self.api_key = self.servam.api_key

    def _normalize_language_code(self, language: str) -> str:
        if not language:
            return "unknown"
        language = language.strip()
        if language.lower() == "unknown":
            return "unknown"
        code = self.servam.get_language_code(language)
        if code == "en-US":
            return "en-IN"
        return code

    def _target_tts_language(self, language_code: str) -> str:
        if not language_code or language_code == "unknown":
            return "en-IN"
        if language_code == "en-US":
            return "en-IN"
        return language_code

    def _build_system_prompt(self, customer_name: str, language_code: str) -> str:
        if language_code.startswith("hi"):
            language_name = "Hindi"
        elif language_code.startswith("en"):
            language_name = "English"
        else:
            language_name = "the detected language"

        return (
            f"You are a friendly hotel relationship manager speaking with {customer_name}. "
            f"Respond in {language_name}. Keep responses concise (1-2 sentences). "
            "Prioritize: understand user intent, ask about next visit plan, then provide relevant offer naturally."
        )

    def _generate_llm_response(self, messages: list) -> Optional[str]:
        return self.servam.call_llm_safe(
            messages=messages,
            model="sarvam-m",
            max_tokens=140,
            temperature=0.2,
        )

    async def _send_json(self, websocket: WebSocket, payload: Dict):
        await websocket.send_text(json.dumps(payload, ensure_ascii=False))

    async def _drain_tts_audio(self, tts_socket, websocket: WebSocket):
        while True:
            try:
                tts_response = await asyncio.wait_for(tts_socket.recv(), timeout=3.0)
            except asyncio.TimeoutError:
                break

            response_type = getattr(tts_response, "type", None)
            if response_type == "audio":
                data = getattr(tts_response, "data", None)
                if data and getattr(data, "audio", None):
                    await self._send_json(
                        websocket,
                        {
                            "type": "tts_audio_chunk",
                            "audio": data.audio,
                            "content_type": getattr(data, "content_type", "audio/mpeg"),
                            "request_id": getattr(data, "request_id", None),
                        },
                    )
            elif response_type == "event":
                event_data = getattr(tts_response, "data", None)
                event_type = getattr(event_data, "event_type", "final") if event_data else "final"
                await self._send_json(websocket, {"type": "tts_event", "event": event_type})
                if event_type == "final":
                    break
            elif response_type == "error":
                await self._send_json(websocket, {"type": "tts_error", "error": str(tts_response)})
                break

    async def run_bridge_session(
        self,
        websocket: WebSocket,
        customer_name: str = "Guest",
        language: str = "unknown",
    ):
        if not SARVAM_ASYNC_AVAILABLE or not self.api_key or self.api_key == "your-api-key":
            await self._send_json(
                websocket,
                {
                    "type": "error",
                    "message": "Sarvam async client not available or API key not configured",
                },
            )
            return

        normalized_lang = self._normalize_language_code(language)
        target_tts_lang = self._target_tts_language(normalized_lang)
        conversation = [{"role": "system", "content": self._build_system_prompt(customer_name, target_tts_lang)}]

        try:
            client = AsyncSarvamAI(api_subscription_key=self.api_key)

            async with client.speech_to_text_streaming.connect(
                language_code=normalized_lang,
                model="saaras:v3",
                mode="transcribe",
                input_audio_codec="pcm_s16le",
                sample_rate="16000",
            ) as stt_socket:
                async with client.text_to_speech_streaming.connect(
                    model="bulbul:v3",
                    send_completion_event="true",
                ) as tts_socket:
                    await tts_socket.configure(
                        target_language_code=target_tts_lang,
                        speaker="anushka" if target_tts_lang.startswith("en") else "aditya",
                        output_audio_codec="mp3",
                        speech_sample_rate=24000,
                        enable_preprocessing=True,
                    )

                    await self._send_json(
                        websocket,
                        {
                            "type": "ready",
                            "language": normalized_lang,
                            "tts_language": target_tts_lang,
                            "input_format": "base64 pcm_s16le @16kHz",
                        },
                    )

                    while True:
                        client_msg_raw = await websocket.receive_text()
                        client_msg = json.loads(client_msg_raw)
                        msg_type = client_msg.get("type")

                        if msg_type == "audio_chunk":
                            audio_b64 = client_msg.get("audio")
                            sample_rate = int(client_msg.get("sample_rate", 16000))
                            encoding = client_msg.get("encoding", "audio/pcm")
                            if not audio_b64:
                                continue

                            await stt_socket.transcribe(audio=audio_b64, encoding=encoding, sample_rate=sample_rate)

                            while True:
                                try:
                                    stt_response = await asyncio.wait_for(stt_socket.recv(), timeout=0.12)
                                except asyncio.TimeoutError:
                                    break

                                if getattr(stt_response, "type", None) != "data":
                                    continue

                                stt_data = getattr(stt_response, "data", None)
                                transcript = (getattr(stt_data, "transcript", "") or "").strip()
                                detected_lang = getattr(stt_data, "language_code", None)

                                if not transcript:
                                    continue

                                await self._send_json(
                                    websocket,
                                    {
                                        "type": "stt",
                                        "transcript": transcript,
                                        "language_code": detected_lang,
                                    },
                                )

                                if detected_lang and detected_lang != target_tts_lang:
                                    target_tts_lang = self._target_tts_language(detected_lang)
                                    await tts_socket.configure(
                                        target_language_code=target_tts_lang,
                                        speaker="anushka" if target_tts_lang.startswith("en") else "aditya",
                                        output_audio_codec="mp3",
                                        speech_sample_rate=24000,
                                        enable_preprocessing=True,
                                    )

                                conversation.append({"role": "user", "content": transcript})
                                llm_text = await asyncio.to_thread(self._generate_llm_response, conversation)
                                if not llm_text:
                                    llm_text = "I heard you. Could you please say that once more?"

                                conversation.append({"role": "assistant", "content": llm_text})

                                await self._send_json(websocket, {"type": "llm", "text": llm_text})

                                await tts_socket.convert(llm_text)
                                await tts_socket.flush()
                                await self._drain_tts_audio(tts_socket, websocket)

                        elif msg_type == "flush":
                            await stt_socket.flush()
                            await self._send_json(websocket, {"type": "stt_flush_ack"})

                        elif msg_type == "ping":
                            await self._send_json(websocket, {"type": "pong"})

                        elif msg_type == "close":
                            await self._send_json(websocket, {"type": "session_closed"})
                            break

                        else:
                            await self._send_json(
                                websocket,
                                {
                                    "type": "error",
                                    "message": "Unsupported message type",
                                    "supported": ["audio_chunk", "flush", "ping", "close"],
                                },
                            )

        except Exception as e:
            logger.error(f"LiveKit bridge session error: {str(e)}")
            await self._send_json(websocket, {"type": "error", "message": str(e)})