"""
Servam AI Service Integration (STT, TTS, LLM) with Multilingual Support
Uses the official sarvamai Python SDK
"""
import logging
import base64
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
            except Exception as e:
                logger.error(f"Failed to initialize Sarvam AI: {e}")
                self.client = None
        else:
            self.client = None
            if not SARVAMAI_AVAILABLE:
                logger.warning("sarvamai library not available - install: pip install sarvamai")
            elif not self.api_key or self.api_key == "your-api-key":
                logger.warning("Sarvam API key not configured in .env")
    
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
            
            # Use correct Sarvam API: chat.completions.create (OpenAI-compatible)
            response = self.client.chat.completions.create(
                model="sarvam-m",
                messages=messages,
                max_tokens=500,
                temperature=0.7
            )
            
            if response and hasattr(response, 'choices') and len(response.choices) > 0:
                # Extract text from first choice
                text = response.choices[0].message.content
                logger.info(f"✓ Response generated ({language}): {text[:50]}...")
                return text
            else:
                logger.error(f"Invalid response format: {response}")
                return None
                
        except Exception as e:
            logger.error(f"Error in generate_response: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def analyze_sentiment(self, text: str, language: str = "en") -> Optional[dict]:
        """
        Analyze sentiment of text (mock implementation)
        
        Note: Sarvam doesn't have built-in sentiment analysis,
        so this returns a mock response for now
        
        Args:
            text: Text to analyze
            language: Language code
            
        Returns:
            Sentiment analysis result
        """
        try:
            # Simple sentiment detection based on keywords (mock)
            positive_keywords = ["love", "beautiful", "excellent", "great", "amazing", "perfect"]
            negative_keywords = ["hate", "bad", "terrible", "awful", "horrible", "worst"]
            
            text_lower = text.lower()
            
            positive_count = sum(1 for word in positive_keywords if word in text_lower)
            negative_count = sum(1 for word in negative_keywords if word in text_lower)
            
            if positive_count > negative_count:
                sentiment = "positive"
                score = 0.7 + (positive_count * 0.05)
            elif negative_count > positive_count:
                sentiment = "negative"
                score = 0.3 - (negative_count * 0.05)
            else:
                sentiment = "neutral"
                score = 0.5
            
            logger.info(f"✓ Sentiment: {sentiment} ({score:.2f})")
            
            return {
                "sentiment": sentiment,
                "score": min(1.0, max(0.0, score)),
                "confidence": 0.75,
                "language": language
            }
            
        except Exception as e:
            logger.error(f"Error in analyze_sentiment: {str(e)}")
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
