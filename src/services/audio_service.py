"""
Audio generation service using Sarvam TTS
Generates natural-sounding audio ON-THE-FLY for IVR prompts (no file storage)
"""
import logging
import urllib.parse
from src.services.servam_service import ServamService

logger = logging.getLogger(__name__)

class AudioService:
    """Service for generating TTS audio dynamically without file storage"""
    
    def __init__(self):
        self.servam = ServamService()
        logger.info("✓ Audio service initialized (streaming mode - no file storage)")
    
    def generate_audio_bytes(self, text: str, language: str = "en") -> bytes:
        """
        Generate audio bytes in real-time using Sarvam TTS (NO FILE STORAGE)
        
        Args:
            text: Text to convert to speech
            language: Language code (en, hi, ta, te, ml)
            
        Returns:
            Audio bytes (MP3 format) or None if failed
        """
        try:
            logger.info(f"🎤 Generating audio on-the-fly: '{text[:50]}...' (lang: {language})")
            
            # Map language codes to Sarvam speaker names and proper language codes
            # Available speakers: anushka, abhilash, manisha, vidya, arya, karun, etc.
            config_map = {
                "en": {"speaker": "anushka", "target_lang": "en-IN"},      # Female Indian English
                "hi": {"speaker": "abhilash", "target_lang": "hi-IN"},     # Male Hindi
                "ta": {"speaker": "manisha", "target_lang": "ta-IN"},      # Female Tamil
                "te": {"speaker": "vidya", "target_lang": "te-IN"},        # Female Telugu
                "ml": {"speaker": "arya", "target_lang": "ml-IN"},         # Female Malayalam
            }
            config = config_map.get(language, {"speaker": "anushka", "target_lang": "en-IN"})
            
            # Generate audio using Sarvam TTS with specified speaker and language
            audio_data = self.servam.text_to_speech(
                text, 
                target_language=config["target_lang"], 
                speaker=config["speaker"]
            )
            
            if not audio_data:
                logger.error(f"Failed to generate audio for: {text}")
                return None
            
            logger.info(f"✓ Audio generated on-the-fly: {len(audio_data)} bytes ({language}, speaker: {config['speaker']})")
            return audio_data
            
        except Exception as e:
            logger.error(f"Error generating audio: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    def generate_audio(self, text: str, language: str = "en") -> str:
        """
        Generate audio endpoint URL (ON-THE-FLY, no file storage).
        
        Returns a URL that will generate audio dynamically when called by Twilio.
        Audio is generated fresh for each customer - personalizable and up-to-date!
        
        Args:
            text: Text to convert to speech
            language: Language code (en, hi, ta, te, ml)
            
        Returns:
            Endpoint URL that will stream the audio
        """
        # Return URL of the dynamic audio generation endpoint
        # The endpoint will accept text and language params, generate audio on-the-fly
        encoded_text = urllib.parse.quote(text)
        return f"/api/v1/audio/generate?text={encoded_text}&language={language}"

