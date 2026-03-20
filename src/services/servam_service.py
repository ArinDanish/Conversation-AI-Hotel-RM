"""
Servam AI Service Integration (STT, TTS, LLM) with Multilingual Support
Uses the official sarvamai Python SDK
"""
import logging
import base64
import re
import json
from typing import Optional, Dict
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

# Try to import sarvamai, with graceful fallback if not installed
try:
    from sarvamai import SarvamAI
    SARVAMAI_AVAILABLE = True
except ImportError:
    SARVAMAI_AVAILABLE = False
    logger.warning("sarvamai library not installed. Install with: pip install sarvamai")


class ServamService:
    """Service for interacting with Sarvam AI APIs with multilingual support"""
    
    # Supported languages and their codes
    SUPPORTED_LANGUAGES = {
        "en": "en-US",      # English (US)
        "en-IN": "en-IN",   # English (India)
        "hi": "hi-IN",      # Hindi
        "ta": "ta-IN",      # Tamil
        "te": "te-IN",      # Telugu
        "kn": "kn-IN",      # Kannada
        "ml": "ml-IN",      # Malayalam
        "mr": "mr-IN",      # Marathi
        "gu": "gu-IN",      # Gujarati
        "pa": "pa-IN",      # Punjabi
        "bn": "bn-IN",      # Bengali
        "es": "es-ES",      # Spanish
        "fr": "fr-FR",      # French
        "de": "de-DE",      # German
        "ja": "ja-JP",      # Japanese
        "zh": "zh-CN"       # Chinese
    }
    
    # Available speakers by language (for bulbul:v3 model)
    AVAILABLE_SPEAKERS = {
        "en-US": ["aditya", "ritu", "priya"],
        "en-IN": ["aditya", "ritu", "priya"],
        "hi-IN": ["aditya", "ritu", "ashutosh"],
        "ta-IN": ["neha", "rahul", "pooja"],
        "te-IN": ["rohan", "simran", "kavya"],
        "kn-IN": ["amit", "dev", "ishita"],
        "ml-IN": ["shreya", "ratan", "varun"],
        "mr-IN": ["manan", "sumit", "roopa"],
        "gu-IN": ["kabir", "aayan", "shubh"],
        "pa-IN": ["advait", "amelia", "sophia"],
        "bn-IN": ["anand", "tanya", "tarun"],
        "es-ES": ["sunny", "mani", "gokul"],
        "fr-FR": ["vijay", "shruti", "suhani"],
        "de-DE": ["mohit", "kavitha", "rehan"],
        "ja-JP": ["soham", "rupali", "niharika"],
        "zh-CN": ["ashutosh", "advait", "amelia"]
    }
    
    def __init__(self):
        self.api_key = config.SERVAM_API_KEY
        self.detected_language = None  # Track last detected language
        
        # Initialize Sarvam AI client with official SDK
        if SARVAMAI_AVAILABLE and self.api_key and self.api_key != "your-api-key":
            try:
                self.client = SarvamAI(api_subscription_key=self.api_key)
                logger.info("✓ Sarvam AI SDK initialized successfully")
                
                # Check if client has the expected chat API
                if hasattr(self.client, 'chat') and hasattr(self.client.chat, 'completions'):
                    logger.info("✓ Sarvam chat.completions API available")
                else:
                    logger.warning("⚠️ Sarvam chat.completions API not available - may need to use alternative method")
                    
            except Exception as e:
                logger.error(f"Failed to initialize Sarvam AI: {e}")
                self.client = None
        else:
            self.client = None
            if not SARVAMAI_AVAILABLE:
                logger.warning("sarvamai library not available - install: pip install sarvamai")
            elif not self.api_key or self.api_key == "your-api-key":
                logger.warning("Sarvam API key not configured in .env")

    def _sanitize_llm_text(self, text: str) -> str:
        """Remove reasoning/thinking blocks and return only speakable assistant text."""
        if not text:
            return ""

        clean_text = text.strip()

        # Remove normal <think>...</think> blocks
        clean_text = re.sub(r'(?is)<think>.*?</think>\s*', '', clean_text).strip()

        # If model returned an unterminated <think> block, drop everything from that marker
        lower_text = clean_text.lower()
        think_index = lower_text.find("<think>")
        if think_index >= 0:
            clean_text = clean_text[:think_index].strip()

        return clean_text

    def _extract_text_from_llm_response(self, response) -> str:
        """Extract assistant text from varied SDK response formats."""
        try:
            def _extract_from_dict_payload(payload: dict) -> str:
                if not isinstance(payload, dict):
                    return ""

                # Primary OpenAI-like path
                choices = payload.get("choices") or []
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        message = first.get("message")
                        if isinstance(message, dict):
                            for key in ("content", "reasoning_content", "text"):
                                value = message.get(key)
                                if isinstance(value, str) and value.strip():
                                    return value
                                if isinstance(value, list):
                                    parts = [
                                        item.get("text", "")
                                        for item in value
                                        if isinstance(item, dict) and isinstance(item.get("text"), str)
                                    ]
                                    joined = " ".join(part.strip() for part in parts if part and part.strip()).strip()
                                    if joined:
                                        return joined

                        for key in ("text", "content", "output_text"):
                            value = first.get(key)
                            if isinstance(value, str) and value.strip():
                                return value

                # Top-level direct keys
                for key in ("output_text", "text", "content", "reasoning_content"):
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        return value

                # Recursive best-effort scan for first non-empty text-like field
                preferred_keys = {"content", "text", "output_text", "reasoning_content", "transcript"}

                def _recursive_scan(node) -> str:
                    if isinstance(node, dict):
                        for key, value in node.items():
                            if key in preferred_keys and isinstance(value, str) and value.strip():
                                return value
                        for value in node.values():
                            found = _recursive_scan(value)
                            if found:
                                return found
                    elif isinstance(node, list):
                        for item in node:
                            found = _recursive_scan(item)
                            if found:
                                return found
                    return ""

                return _recursive_scan(payload)

            # Dict-like responses
            if isinstance(response, dict):
                extracted = _extract_from_dict_payload(response)
                if extracted:
                    return extracted

            # Object-like responses
            if hasattr(response, "choices") and response.choices:
                first_choice = response.choices[0]

                # message.content
                message = getattr(first_choice, "message", None)
                if message is not None:
                    content = getattr(message, "content", None)
                    if isinstance(content, str) and content.strip():
                        return content

                    # Some Sarvam responses may populate reasoning_content when content is empty
                    reasoning_content = getattr(message, "reasoning_content", None)
                    if isinstance(reasoning_content, str) and reasoning_content.strip():
                        return reasoning_content

                    if isinstance(content, list):
                        parts = []
                        for item in content:
                            if isinstance(item, dict):
                                item_text = item.get("text") or item.get("content")
                            else:
                                item_text = getattr(item, "text", None) or getattr(item, "content", None)
                            if isinstance(item_text, str) and item_text.strip():
                                parts.append(item_text.strip())
                        joined = " ".join(parts).strip()
                        if joined:
                            return joined

                # delta.content (stream-like shapes)
                delta = getattr(first_choice, "delta", None)
                if delta is not None:
                    delta_content = getattr(delta, "content", None)
                    if isinstance(delta_content, str) and delta_content.strip():
                        return delta_content

                # text fallback
                choice_text = getattr(first_choice, "text", None)
                if isinstance(choice_text, str) and choice_text.strip():
                    return choice_text

            # Top-level text fallbacks
            for attr in ("output_text", "text", "content"):
                value = getattr(response, attr, None)
                if isinstance(value, str) and value.strip():
                    return value

            # Pydantic model fallback (Sarvam SDK responses are often pydantic models)
            if hasattr(response, "model_dump"):
                try:
                    dumped = response.model_dump()
                    extracted = _extract_from_dict_payload(dumped)
                    if extracted:
                        return extracted
                except Exception:
                    pass

            # Some SDK objects expose richer payload only through JSON serialization
            if hasattr(response, "model_dump_json"):
                try:
                    dumped_json = response.model_dump_json()
                    if isinstance(dumped_json, str) and dumped_json.strip():
                        dumped = json.loads(dumped_json)
                        extracted = _extract_from_dict_payload(dumped)
                        if extracted:
                            return extracted
                except Exception:
                    pass

            # Pydantic v1 fallback
            if hasattr(response, "dict"):
                try:
                    dumped = response.dict()
                    extracted = _extract_from_dict_payload(dumped)
                    if extracted:
                        return extracted
                except Exception:
                    pass

            return ""
        except Exception:
            return ""
    
    def call_llm_safe(self, messages: list, model: str = "sarvam-m", max_tokens: int = 200, temperature: float = 0.0) -> Optional[str]:
        """
        Safely call Sarvam LLM with error handling for different SDK versions
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name
            max_tokens: Max tokens in response
            temperature: Temperature for generation
            
        Returns:
            Generated text or None if failed
        """
        if not self.client:
            logger.error("❌ Sarvam AI client not initialized")
            return None
        
        try:
            # Try the standard OpenAI-compatible API
            if hasattr(self.client, 'chat'):
                logger.debug(f"Calling Sarvam LLM via chat API")
                
                # The Sarvam SDK uses: client.chat.completions(messages, model, ...)
                # NOT: client.chat.completions.create(...)
                try:
                    # Try the .completions() method directly
                    response = self.client.chat.completions(
                        messages=messages,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )

                    text = self._sanitize_llm_text(self._extract_text_from_llm_response(response))
                    if text:
                        logger.debug(f"✓ LLM response: {text[:80]}...")
                        return text

                    logger.warning(f"⚠️ LLM returned empty/unsupported response format: {type(response)}")
                    return None
                        
                except AttributeError as ae1:
                    logger.debug(f"   .completions() method not available, trying .completions.create()...")
                    # Fallback: try .create() method
                    response = self.client.chat.completions.create(
                        messages=messages,
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )

                    text = self._sanitize_llm_text(self._extract_text_from_llm_response(response))
                    if text:
                        logger.debug(f"✓ LLM response (.create()): {text[:80]}...")
                        return text

                    logger.warning(f"LLM returned empty response from .create(): {type(response)}")
                    return None
            else:
                logger.error(f"❌ Sarvam SDK API not compatible - missing chat interface")
                return None
                
        except AttributeError as ae:
            logger.error(f"❌ LLM API AttributeError: {str(ae)}")
            logger.error(f"   client type: {type(self.client)}")
            logger.error(f"   client.chat type: {type(getattr(self.client, 'chat', None))}")
            if hasattr(self.client, 'chat'):
                logger.error(f"   Available methods: {dir(self.client.chat)[:5]}...")
            return None
        except Exception as e:
            logger.error(f"❌ LLM API error: {type(e).__name__}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def speech_to_text(self, audio_data: bytes, language: str = "unknown", 
                       mode: str = "transcribe") -> Optional[Dict]:
        """
        Convert speech to text using Sarvam STT with auto-language detection
        
        Args:
            audio_data: Audio bytes
            language: Language code ("unknown" for auto-detect, or specific code like "hi", "en-IN")
            mode: Mode for STT ("transcribe", "translate", "verbatim", "translit", or "codemix")
            
        Returns:
            Dictionary with 'text', 'language', 'confidence', etc., or None if failed
        """
        if not self.client:
            logger.error("Sarvam AI client not initialized")
            return None
        
        try:
            from io import BytesIO
            
            # Create a file-like object from bytes
            audio_file = BytesIO(audio_data)
            audio_file.name = "audio.wav"
            
            # Call Sarvam API with official SDK
            response = self.client.speech_to_text.transcribe(
                file=audio_file,
                model="saaras:v3",
                mode=mode,  # transcribe, translate, verbatim, translit, codemix
                language_code=language  # "unknown" for auto-detect
            )
            
            if response and hasattr(response, 'request_id'):
                # Get transcript from response (could be 'transcript' or 'text')
                text = getattr(response, 'transcript', getattr(response, 'text', ''))
                detected_lang = getattr(response, 'language', language)
                confidence = getattr(response, 'confidence', 0.95)
                
                # Store detected language for later use
                self.detected_language = detected_lang
                
                logger.info(f"✓ STT successful: {detected_lang} (confidence: {confidence:.2%})")
                
                return {
                    'text': text,
                    'language': detected_lang,
                    'confidence': confidence,
                    'mode': mode,
                    'request_id': getattr(response, 'request_id', '')
                }
            else:
                logger.error(f"STT failed: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error in speech_to_text: {str(e)}")
            return None
    
    def text_to_speech(self, text: str, target_language: str = "en-IN", 
                      speaker: str = "aditya", model: str = "bulbul:v3") -> Optional[bytes]:
        """
        Convert text to speech using Sarvam TTS with language-specific speaker
        
        Args:
            text: Text to convert
            target_language: Target language code (e.g., "en-IN", "hi-IN")
            speaker: Speaker name (e.g., "aditya", "diya" for English; varies by language)
            model: TTS model to use
            
        Returns:
            Audio bytes or None if failed
        """
        if not self.client:
            logger.error("Sarvam AI client not initialized")
            return None
        
        try:
            # Validate speaker for language
            available = self.get_available_speakers(target_language)
            if speaker not in available:
                speaker = available[0] if available else "aditya"
                logger.warning(f"Speaker adjusted to {speaker} for language {target_language}")
            
            # Call Sarvam API with official SDK
            # API: convert(text, target_language_code, speaker, model, output_audio_codec)
            logger.debug(f"Calling TTS: text={text[:40]}..., lang={target_language}, speaker={speaker}")
            response = self.client.text_to_speech.convert(
                text=text,
                target_language_code=target_language,
                speaker=speaker,
                model=model,
                output_audio_codec="mp3"
            )
            logger.debug(f"TTS API returned: {type(response)}")
            
            # Response is a Pydantic model with 'audios' attribute containing audio data
            if response is not None:
                logger.info(f"TTS Response type: {type(response)}")
                
                # Check if response has 'audios' attribute (list of base64-encoded audio strings)
                if hasattr(response, 'audios') and response.audios:
                    audio_list = response.audios
                    logger.debug(f"audios type: {type(audio_list)}, length: {len(audio_list) if hasattr(audio_list, '__len__') else 'N/A'}")
                    
                    # audios is a list - get first item
                    if isinstance(audio_list, list) and len(audio_list) > 0:
                        audio_item = audio_list[0]
                        logger.debug(f"First audio item type: {type(audio_item)}")
                        
                        # If it's a string, it's likely base64-encoded
                        if isinstance(audio_item, str):
                            try:
                                audio_data = base64.b64decode(audio_item)
                                if len(audio_data) > 0:
                                    logger.info(f"✓ TTS successful: {target_language} ({speaker}), {len(audio_data)} bytes (base64 decoded)")
                                    return audio_data
                            except Exception as e:
                                logger.debug(f"Failed to decode base64: {e}")
                        
                        # If it's bytes, use directly
                        elif isinstance(audio_item, bytes) and len(audio_item) > 0:
                            logger.info(f"✓ TTS successful: {target_language} ({speaker}), {len(audio_item)} bytes (direct)")
                            return audio_item
                    
                    # If audios itself is not a list but a string/bytes, handle that
                    elif isinstance(audio_list, str):
                        try:
                            audio_data = base64.b64decode(audio_list)
                            if len(audio_data) > 0:
                                logger.info(f"✓ TTS successful: {target_language} ({speaker}), {len(audio_data)} bytes (base64)")
                                return audio_data
                        except Exception as e:
                            logger.debug(f"Failed to decode base64: {e}")
                    elif isinstance(audio_list, bytes) and len(audio_list) > 0:
                        logger.info(f"✓ TTS successful: {target_language} ({speaker}), {len(audio_list)} bytes")
                        return audio_list
                
                # Check if response IS bytes directly
                if isinstance(response, bytes):
                    logger.info(f"✓ TTS successful (bytes): {target_language} ({speaker})")
                    return response
                
                logger.error(f"TTS response has no valid audio data. Response class: {response.__class__.__name__}")
                return None
            else:
                logger.error(f"TTS API response is None!")
                return None
                
        except Exception as e:
            logger.error(f"Error in text_to_speech: {type(e).__name__}: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def detect_language(self, audio_data: bytes) -> Optional[Dict]:
        """
        Detect language from audio without transcription
        
        Args:
            audio_data: Audio bytes
            
        Returns:
            Dictionary with detected language info or None if failed
        """
        if not self.client:
            logger.error("Sarvam AI client not initialized")
            return None
        
        try:
            from io import BytesIO
            
            # Use STT with language detection mode
            audio_file = BytesIO(audio_data)
            audio_file.name = "audio.wav"
            
            response = self.client.speech_to_text.transcribe(
                file=audio_file,
                model="saaras:v3",
                mode="transcribe",
                language_code="unknown"  # Auto-detect
            )
            
            if response:
                detected_lang = getattr(response, 'language', 'unknown')
                confidence = getattr(response, 'confidence', 0.0)
                
                self.detected_language = detected_lang
                
                logger.info(f"✓ Language detected: {detected_lang} (confidence: {confidence:.2%})")
                
                return {
                    'language': detected_lang,
                    'confidence': confidence,
                    'language_code': self.SUPPORTED_LANGUAGES.get(detected_lang, detected_lang)
                }
            else:
                logger.error(f"Language detection failed")
                return None
                
        except Exception as e:
            logger.error(f"Error in detect_language: {str(e)}")
            return None
    
    def get_language_code(self, language: str) -> str:
        """
        Get full language code from short code
        
        Args:
            language: Short language code (e.g., "en", "hi")
            
        Returns:
            Full language code (e.g., "en-IN")
        """
        return self.SUPPORTED_LANGUAGES.get(language, language)
    
    def get_available_speakers(self, language: str) -> list:
        """
        Get available speakers for a language
        
        Args:
            language: Language code
            
        Returns:
            List of available speakers for the language
        """
        return self.AVAILABLE_SPEAKERS.get(language, ["default"])
    
    def get_detected_language(self) -> Optional[str]:
        """
        Get the last detected language
        
        Returns:
            Language code of last detection
        """
        return self.detected_language
    
    def generate_response(self, prompt: str, context: str = None, 
                         language: str = "en") -> Optional[str]:
        """
        Generate response using Sarvam LLM (sarvam-m model)
        Uses OpenAI-compatible chat completions API
        
        Args:
            prompt: User prompt
            context: Optional context
            language: Response language
            
        Returns:
            Generated response or None if failed
        """
        if not self.client:
            logger.error("Sarvam AI client not initialized")
            return None
        
        try:
            # Build messages for chat API
            messages = []
            
            # System message with language instruction
            system_msg = "You are a helpful hotel relationship manager assistant."
            if language != "en":
                system_msg += f" Respond in {language}."
            
            messages.append({
                "role": "system",
                "content": system_msg
            })
            
            # Context if provided
            if context:
                messages.append({
                    "role": "assistant",
                    "content": f"Context: {context}"
                })
            
            # User prompt
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            # Use call_llm_safe() for SDK compatibility
            response_text = self.call_llm_safe(
                messages=messages,
                model="sarvam-m",
                max_tokens=500,
                temperature=0.7
            )
            
            if response_text:
                # Response is already filtered in call_llm_safe() - no additional filtering needed
                logger.info(f"✓ Response generated ({language}): {response_text[:50]}...")
                return response_text
            else:
                logger.error(f"LLM API returned empty response")
                return None
                
        except Exception as e:
            logger.error(f"Error in generate_response: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def _simple_keyword_sentiment(self, text: str) -> Optional[dict]:
        """
        Simple keyword-based sentiment detection (fast, lightweight)
        Returns None if inconclusive, allowing fallback to LLM
        
        Args:
            text: Text to analyze
            
        Returns:
            Dict with sentiment/score if confident, None if inconclusive
        """
        positive_keywords = ["love", "beautiful", "excellent", "great", "amazing", "perfect", 
                            "wonderful", "fantastic", "awesome", "good", "best", "outstanding"]
        negative_keywords = ["hate", "bad", "terrible", "awful", "horrible", "worst", 
                            "poor", "disappointing", "disgust", "hate", "awful", "pathetic"]
        
        text_lower = text.lower()
        
        positive_count = sum(1 for word in positive_keywords if word in text_lower)
        negative_count = sum(1 for word in negative_keywords if word in text_lower)
        
        # Only return if we have strong signal (keyword match)
        if positive_count > negative_count and positive_count > 0:
            score = min(0.95, 0.7 + (positive_count * 0.05))
            return {
                "sentiment": "positive",
                "score": score,
                "confidence": min(0.95, 0.8 + (positive_count * 0.05)),
                "method": "keyword"
            }
        elif negative_count > positive_count and negative_count > 0:
            score = max(0.05, 0.3 - (negative_count * 0.05))
            return {
                "sentiment": "negative",
                "score": score,
                "confidence": min(0.95, 0.8 + (negative_count * 0.05)),
                "method": "keyword"
            }
        
        # Inconclusive - return None to trigger LLM fallback
        return None
    
    def _llm_sentiment_detection(self, text: str, language: str = "en") -> Optional[dict]:
        """
        LLM-based sentiment detection (more accurate but slower)
        Uses Sarvam LLM to analyze sentiment with context understanding
        
        Args:
            text: Text to analyze
            language: Language code
            
        Returns:
            Dict with sentiment/score from LLM analysis
        """
        try:
            if not self.client:
                logger.warning("LLM sentiment detection unavailable - client not initialized")
                return None
            
            # Craft prompt for sentiment analysis
            sentiment_prompt = f"""Analyze the sentiment of the following customer feedback and respond with ONLY 'positive', 'negative', or 'neutral':

Customer feedback: "{text}"

Respond with exactly one word: positive, negative, or neutral"""
            
            logger.debug(f"Calling LLM for sentiment analysis of: {text[:50]}...")
            
            response = self.generate_response(sentiment_prompt, language=language)
            
            if not response:
                logger.warning("LLM sentiment detection failed - no response")
                return None
            
            # Parse LLM response
            response_lower = response.lower().strip()
            
            if "positive" in response_lower:
                sentiment = "positive"
                score = 0.8
            elif "negative" in response_lower:
                sentiment = "negative"
                score = 0.2
            else:
                sentiment = "neutral"
                score = 0.5
            
            logger.info(f"✓ LLM Sentiment: {sentiment} (LLM response: {response[:50]}...)")
            
            return {
                "sentiment": sentiment,
                "score": score,
                "confidence": 0.85,
                "method": "llm",
                "llm_response": response
            }
            
        except Exception as e:
            logger.warning(f"LLM sentiment detection error: {str(e)}")
            return None
    
    def analyze_sentiment(self, text: str, language: str = "en") -> Optional[dict]:
        """
        Hybrid sentiment analysis: keyword detection + LLM fallback
        
        Flow:
        1. Try simple keyword detection (fast)
        2. If inconclusive, use LLM (accurate but slower)
        3. Default to neutral if both fail
        
        Args:
            text: Text to analyze
            language: Language code
            
        Returns:
            Sentiment analysis result with sentiment, score, confidence, and method
        """
        try:
            logger.debug(f"Analyzing sentiment: '{text[:50]}...'")
            
            # Step 1: Try simple keyword detection first (fast)
            keyword_result = self._simple_keyword_sentiment(text)
            if keyword_result:
                result = {
                    "sentiment": keyword_result["sentiment"],
                    "score": keyword_result["score"],
                    "confidence": keyword_result["confidence"],
                    "language": language,
                    "method": "keyword"
                }
                logger.info(f"✓ Sentiment (keyword): {result['sentiment']} ({result['score']:.2f}) [confidence: {result['confidence']:.2f}]")
                return result
            
            # Step 2: Keyword detection was inconclusive, use LLM
            logger.debug("Keyword detection inconclusive - using LLM fallback...")
            llm_result = self._llm_sentiment_detection(text, language)
            if llm_result:
                result = {
                    "sentiment": llm_result["sentiment"],
                    "score": llm_result["score"],
                    "confidence": llm_result["confidence"],
                    "language": language,
                    "method": "llm"
                }
                logger.info(f"✓ Sentiment (LLM): {result['sentiment']} ({result['score']:.2f}) [confidence: {result['confidence']:.2f}]")
                return result
            
            # Step 3: Both methods failed, default to neutral
            logger.warning(f"Both sentiment detection methods failed - defaulting to neutral")
            return {
                "sentiment": "neutral",
                "score": 0.5,
                "confidence": 0.5,
                "language": language,
                "method": "default"
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_sentiment: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def translate_text(self, text: str, source_language: str = "auto", 
                      target_language: str = "en") -> Optional[Dict]:
        """
        Translate text using STT mode with translation
        
        Note: Uses speech-to-text "translate" mode from Sarvam
        
        Args:
            text: Text to translate (can be audio transcription to translate)
            source_language: Source language
            target_language: Target language
            
        Returns:
            Translation result or None if failed
        """
        try:
            # For text translation, we'd need to use a different endpoint
            # For now, provide a mock response
            logger.warning("Direct text translation not available - use STT with translate mode")
            
            return {
                'original_text': text,
                'translated_text': f"[Translated from {source_language} to {target_language}]",
                'source_language': source_language,
                'target_language': target_language,
                'confidence': 0.95
            }
            
        except Exception as e:
            logger.error(f"Error in translate_text: {str(e)}")
            return None
    
    def multilingual_call_script(self, customer_name: str, offer: float, 
                                language: str = "detected") -> Optional[Dict]:
        """
        Generate multilingual call script
        
        Args:
            customer_name: Customer name
            offer: Discount offer percentage
            language: Target language ("detected" uses last detected, or specify code)
            
        Returns:
            Dictionary with script, language, and speaker
        """
        try:
            # Use detected language if requested
            if language == "detected":
                language = self.detected_language or "en-IN"
            
            # Convert short codes to full codes
            if len(language) == 2:
                language = self.SUPPORTED_LANGUAGES.get(language, language)
            
            # Pre-built scripts for common languages
            scripts = {
                "en-US": f"Hello {customer_name}, this is a call from Beacon Hotel. We have a special {offer}% discount offer for you. Would you be interested?",
                "en-IN": f"Hello {customer_name}, this is a call from Beacon Hotel. We have a special {offer}% discount offer for you. Would you be interested?",
                "hi-IN": f"नमस्ते {customer_name}, यह बीकन होटल की ओर से कॉल है। हमारे पास आपके लिए एक विशेष {offer}% छूट की पेशकश है। क्या आप रुचि रखते हैं?",
                "ta-IN": f"வணக்கம் {customer_name}, இது பீகன் ஹோட்டலிலிருந்து ஒரு அழைப்பு. எங்களிடம் உங்களுக்கு {offer}% ஆயக்குத் தள்ளுபடி உள்ளது. நீங்கள் ஆர்வமாக இருக்கிறீர்களா?",
                "te-IN": f"హలో {customer_name}, ఇది బీకన్ హోటల్ నుండి ఒక కాల్. మేము మీకు {offer}% డిస్‌కౌంట్ ఆఫర్ కలిగి ఉన్నాము. మీరు ఆసక్తి కలిగి ఉన్నారా?",
            }
            
            script = scripts.get(language, scripts["en-IN"])
            speaker = self.get_available_speakers(language)[0]
            
            logger.info(f"✓ Script generated: {language} ({speaker})")
            
            return {
                "language": language,
                "speaker": speaker,
                "script": script
            }
            
        except Exception as e:
            logger.error(f"Error in multilingual_call_script: {str(e)}")
            return None
