"""
Multilingual Servam Service Examples
Demonstrates STT auto-detection, language-specific TTS, and multilingual support
"""

import sys
import os
import io

# Force UTF-8 output on Windows
if sys.platform == 'win32':
    import glob
    # Set console encoding to UTF-8
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path to import src module
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.services.servam_service import ServamService

# Initialize the service
servam = ServamService()

# ============================================================================
# EXAMPLE 1: AUTO-DETECT LANGUAGE FROM SPEECH (STT with language="unknown")
# ============================================================================

def example_auto_detect_stt():
    """
    Auto-detect language from audio without specifying language
    Uses language="unknown" for automatic language detection
    """
    print("\n📱 EXAMPLE 1: Auto-Detect Language from Speech\n")
    
    # Check if audio file exists
    audio_file = 'audio_sample.wav'
    if not os.path.exists(audio_file):
        print(f"⚠️  Audio file '{audio_file}' not found")
        print("\nTo test this example:")
        print("1. Record a sample audio file (WAV format)")
        print("2. Save it as 'audio_sample.wav' in this directory")
        print("3. Valid languages: Hi (Hindi), Ta (Tamil), En (English), etc.")
        print("\nExample (for testing without actual audio):")
        print("  result = servam.speech_to_text(")
        print("      audio_data=b'<audio bytes>',")
        print("      language='unknown',      # Auto-detect")
        print("      mode='transcribe'")
        print("  )")
        print("  # Would return:")
        print("  # {")
        print("  #     'text': 'Transcribed text in detected language',")
        print("  #     'language': 'hi-IN',")
        print("  #     'confidence': 0.95,")
        print("  #     'mode': 'transcribe'")
        print("  # }")
        return
    
    # Load audio file (Hindi, Tamil, English, etc.)
    with open(audio_file, 'rb') as f:
        audio_data = f.read()
    
    # STT with auto-detection (model="saaras:v3", language="unknown")
    result = servam.speech_to_text(
        audio_data=audio_data,
        language="unknown",      # Auto-detect
        mode="transcribe"        # Or "translate"
    )
    
    if result:
        print(f"✓ Transcription: {result['text']}")
        print(f"✓ Detected Language: {result['language']}")
        print(f"✓ Confidence: {result['confidence']:.2f}")
    else:
        print("✗ STT failed")


# ============================================================================
# EXAMPLE 2: LANGUAGE-SPECIFIC TTS WITH SPEAKER SELECTION
# ============================================================================

def example_language_specific_tts():
    """
    Use TTS with specific language and speaker
    Supports multiple languages with regional speakers
    """
    print("\n🔊 EXAMPLE 2: Language-Specific TTS with Speaker Selection\n")
    
    # English (India) with Aditya speaker
    print("Testing English (India) with Aditya speaker...")
    audio_en = servam.text_to_speech(
        text="namaste, welcome to Beacon Hotel",
        target_language="en-IN",
        speaker="aditya",
        model="bulbul:v3"
    )
    if audio_en:
        output_file = 'output_en_aditya.wav'
        with open(output_file, 'wb') as f:
            f.write(audio_en)
        print(f"✓ English (India) - Aditya speaker: {output_file}")
    else:
        print("⚠️  API call skipped (requires valid Servam credentials in .env)")
        print("     Expected output: WAV audio file with English greeting in Aditya's voice")
    
    # Hindi with Indian speaker
    print("\nTesting Hindi with default speaker...")
    audio_hi = servam.text_to_speech(
        text="नमस्ते, बीकन होटल में स्वागत है",
        target_language="hi-IN",
        speaker="default",
        model="bulbul:v3"
    )
    if audio_hi:
        output_file = 'output_hi_default.wav'
        with open(output_file, 'wb') as f:
            f.write(audio_hi)
        print(f"✓ Hindi - Default speaker: {output_file}")
    else:
        print("⚠️  API call skipped (requires valid Servam credentials in .env)")
        print("     Expected output: WAV audio file with Hindi greeting")
    
    # Tamil with Indian speaker
    print("\nTesting Tamil with female speaker...")
    audio_ta = servam.text_to_speech(
        text="வணக்கம், பீகன் ஹோட்டலுக்கு வருக",
        target_language="ta-IN",
        speaker="female",
        model="bulbul:v3"
    )
    if audio_ta:
        output_file = 'output_ta_female.wav'
        with open(output_file, 'wb') as f:
            f.write(audio_ta)
        print(f"✓ Tamil - Female speaker: {output_file}")
    else:
        print("⚠️  API call skipped (requires valid Servam credentials in .env)")
        print("     Expected output: WAV audio file with Tamil greeting in female voice")


# ============================================================================
# EXAMPLE 3: AUTO-DETECT THEN RESPOND IN SAME LANGUAGE
# ============================================================================

def example_detect_and_respond():
    """
    Detect customer's language from their speech,
    then respond in the same language
    """
    print("\n🔄 EXAMPLE 3: Detect Language & Respond in Same Language\n")
    
    # Check if audio file exists
    audio_file = 'customer_audio.wav'
    if not os.path.exists(audio_file):
        print(f"⚠️  Audio file '{audio_file}' not found")
        print("\nExample workflow (without actual audio):")
        print("  Step 1: Detect language from customer's speech")
        print("  stt_result = servam.speech_to_text(audio_data, language='unknown')")
        print("  # Returns: {'text': '...', 'language': 'hi-IN', 'confidence': 0.95}")
        print("\n  Step 2: Analyze sentiment in detected language")
        print("  sentiment = servam.analyze_sentiment(text, language=detected_lang)")
        print("\n  Step 3: Generate response in same language")
        print("  response = servam.generate_response(prompt, language=detected_lang)")
        print("\n  Step 4: Convert to speech with appropriate speaker")
        print("  audio = servam.text_to_speech(response, target_language=detected_lang)")
        return
    
    # Load customer's audio
    with open(audio_file, 'rb') as f:
        audio_data = f.read()
    
    # Step 1: Detect language
    stt_result = servam.speech_to_text(
        audio_data=audio_data,
        language="unknown"  # Auto-detect
    )
    
    if stt_result:
        customer_text = stt_result['text']
        detected_lang = stt_result['language']
        
        print(f"Customer said: {customer_text}")
        print(f"Language detected: {detected_lang}")
        
        # Step 2: Generate response in same language
        response_text = servam.generate_response(
            prompt=f"Customer said: {customer_text}. Provide a helpful response.",
            language=detected_lang
        )
        
        if response_text:
            print(f"Response generated: {response_text}")
            
            # Step 3: Speak response in same language
            speakers = servam.get_available_speakers(detected_lang)
            audio_response = servam.text_to_speech(
                text=response_text,
                target_language=detected_lang,
                speaker=speakers[0]  # Use first available speaker
            )
            
            if audio_response:
                with open(f'response_{detected_lang}.wav', 'wb') as f:
                    f.write(audio_response)
                print(f"✓ Response audio saved: response_{detected_lang}.wav")
    else:
        print("✗ STT failed")


# ============================================================================
# EXAMPLE 4: MULTILINGUAL CALL SCRIPT GENERATION
# ============================================================================

def example_multilingual_call_script():
    """
    Generate personalized call script in customer's detected language
    """
    print("\n📞 EXAMPLE 4: Multilingual Call Script Generation\n")
    
    customer_name = "Rajesh"
    discount_offer = 20
    
    # Option 1: Use detected language
    servam.detected_language = "hi-IN"  # Set from previous detection
    
    script_data = servam.multilingual_call_script(
        customer_name=customer_name,
        offer=discount_offer,
        language="detected"  # Uses detected language
    )
    
    print(f"Script Language: {script_data['language']}")
    print(f"Speaker: {script_data['speaker']}")
    print(f"Script:\n{script_data['script']}")
    
    # Option 2: Specify language directly
    script_data_en = servam.multilingual_call_script(
        customer_name=customer_name,
        offer=discount_offer,
        language="en-IN"
    )
    
    print(f"\nEnglish Version:\n{script_data_en['script']}")


# ============================================================================
# EXAMPLE 5: MULTILINGUAL SENTIMENT ANALYSIS
# ============================================================================

def example_multilingual_sentiment():
    """
    Analyze sentiment of text in different languages
    """
    print("\n😊 EXAMPLE 5: Multilingual Sentiment Analysis\n")
    
    # English sentiment
    en_text = "I absolutely loved my stay at Beacon Hotel! The service was excellent."
    sentiment_en = servam.analyze_sentiment(en_text, language="en-IN")
    if sentiment_en:
        print(f"English text: {en_text}")
        print(f"Sentiment: {sentiment_en['sentiment']}, Score: {sentiment_en['score']:.2f}\n")
    
    # Hindi sentiment
    hi_text = "बीकन होटल में मेरा ठहरना बहुत अच्छा रहा। सेवा शानदार थी।"
    sentiment_hi = servam.analyze_sentiment(hi_text, language="hi-IN")
    if sentiment_hi:
        print(f"Hindi text: {hi_text}")
        print(f"Sentiment: {sentiment_hi['sentiment']}, Score: {sentiment_hi['score']:.2f}\n")
    
    # Tamil sentiment
    ta_text = "பீகன் ஹோட்டலில் என் தங்குவது அற்புதமாக இருந்தது. சேவை சிறந்தது."
    sentiment_ta = servam.analyze_sentiment(ta_text, language="ta-IN")
    if sentiment_ta:
        print(f"Tamil text: {ta_text}")
        print(f"Sentiment: {sentiment_ta['sentiment']}, Score: {sentiment_ta['score']:.2f}")


# ============================================================================
# EXAMPLE 6: LANGUAGE TRANSLATION
# ============================================================================

def example_translation():
    """
    Translate text between languages
    """
    print("\n🌐 EXAMPLE 6: Multilingual Translation\n")
    
    # English to Hindi
    en_text = "We have a special discount offer for you"
    translation = servam.translate_text(
        text=en_text,
        source_language="en",
        target_language="hi"
    )
    
    if translation:
        print(f"Original (English): {en_text}")
        print(f"Hindi: {translation['translated_text']}\n")
    
    # Hindi to English
    hi_text = "आपके लिए विशेष छूट की पेशकश है"
    translation = servam.translate_text(
        text=hi_text,
        source_language="hi",
        target_language="en"
    )
    
    if translation:
        print(f"Original (Hindi): {hi_text}")
        print(f"English: {translation['translated_text']}")


# ============================================================================
# EXAMPLE 7: COMPLETE CALL FLOW WITH LANGUAGE DETECTION
# ============================================================================

def example_complete_call_flow():
    """
    Complete multilingual call flow:
    1. Customer calls in any language
    2. Auto-detect language
    3. Generate response in that language
    4. Analyze sentiment
    5. Store language preference
    """
    print("\n🔄 EXAMPLE 7: Complete Multilingual Call Flow\n")
    
    # Check if audio file exists
    audio_file = 'customer_call.wav'
    if not os.path.exists(audio_file):
        print(f"⚠️  Audio file '{audio_file}' not found")
        print("\nComplete call flow workflow:")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ INCOMING CUSTOMER CALL                  │")
        print("  └─────────────────────────────────────────┘")
        print("           ↓")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ Step 1: AUTO-DETECT LANGUAGE            │")
        print("  │ stt = speech_to_text(audio, 'unknown')  │")
        print("  │ Returns: text + language + confidence   │")
        print("  └─────────────────────────────────────────┘")
        print("           ↓")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ Step 2: ANALYZE SENTIMENT               │")
        print("  │ sentiment = analyze_sentiment(text)     │")
        print("  │ Returns: sentiment type + score         │")
        print("  └─────────────────────────────────────────┘")
        print("           ↓")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ Step 3: GENERATE RESPONSE               │")
        print("  │ response = generate_response(prompt)    │")
        print("  │ Returns: text in customer's language    │")
        print("  └─────────────────────────────────────────┘")
        print("           ↓")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ Step 4: CONVERT TO SPEECH               │")
        print("  │ audio = text_to_speech(response)        │")
        print("  │ Returns: audio bytes                    │")
        print("  └─────────────────────────────────────────┘")
        print("           ↓")
        print("  ┌─────────────────────────────────────────┐")
        print("  │ Step 5: STORE PREFERENCES               │")
        print("  │ Save language for future calls          │")
        print("  │ Update customer profile                 │")
        print("  └─────────────────────────────────────────┘")
        print("\nTo test this flow, record a customer call and save as 'customer_call.wav'\n")
        return
    
    print("Step 1: Receive customer call (auto-detect language)...")
    
    # Load customer audio
    with open(audio_file, 'rb') as f:
        customer_audio = f.read()
    
    # Auto-detect language from speech
    stt_result = servam.speech_to_text(
        audio_data=customer_audio,
        language="unknown"
    )
    
    if not stt_result:
        return
    
    customer_text = stt_result['text']
    detected_language = stt_result['language']
    
    print(f"✓ Customer message: {customer_text}")
    print(f"✓ Detected language: {detected_language}")
    
    print("\nStep 2: Analyze sentiment...")
    sentiment = servam.analyze_sentiment(customer_text, language=detected_language)
    
    if sentiment:
        print(f"✓ Sentiment: {sentiment['sentiment']} (confidence: {sentiment['confidence']:.2f})")
    
    print("\nStep 3: Generate response in same language...")
    response = servam.generate_response(
        prompt=f"Customer inquiry: {customer_text}. Provide a helpful response.",
        language=detected_language
    )
    
    if response:
        print(f"✓ Response: {response}")
    
    print("\nStep 4: Convert response to speech with appropriate speaker...")
    speakers = servam.get_available_speakers(detected_language)
    audio_response = servam.text_to_speech(
        text=response,
        target_language=detected_language,
        speaker=speakers[0]
    )
    
    if audio_response:
        print(f"✓ Audio response generated ({len(audio_response)} bytes)")
    
    print("\nStep 5: Store language preference for future calls...")
    print(f"✓ Customer language preference: {detected_language}")
    print("✓ Profile updated - will use this language for future calls")


# ============================================================================
# EXAMPLE 8: UTILITY METHODS
# ============================================================================

def example_utility_methods():
    """
    Demonstrate utility methods for language handling
    """
    print("\n🛠️ EXAMPLE 8: Utility Methods\n")
    
    # Get full language code from short code
    lang_code = servam.get_language_code("hi")
    print(f"Language code for 'hi': {lang_code}")
    
    # Get available speakers for a language
    speakers = servam.get_available_speakers("en-IN")
    print(f"Available speakers for en-IN: {speakers}")
    
    # Get detected language
    servam.detected_language = "ta-IN"
    detected = servam.get_detected_language()
    print(f"Last detected language: {detected}")
    
    # List all supported languages
    print(f"\nSupported languages ({len(servam.SUPPORTED_LANGUAGES)}):")
    for short_code, full_code in list(servam.SUPPORTED_LANGUAGES.items())[:5]:
        print(f"  {short_code} → {full_code}")
    print("  ...")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("🌍 MULTILINGUAL SERVAM SERVICE EXAMPLES")
    print("=" * 70)
    
    print("\n📋 Available Examples:")
    print("1. example_auto_detect_stt() - Auto-detect language from speech")
    print("2. example_language_specific_tts() - Language-specific TTS")
    print("3. example_detect_and_respond() - Detect and respond in same language")
    print("4. example_multilingual_call_script() - Generate scripts in multiple languages")
    print("5. example_multilingual_sentiment() - Analyze sentiment in multiple languages")
    print("6. example_translation() - Translate between languages")
    print("7. example_complete_call_flow() - Complete call flow with auto-detection")
    print("8. example_utility_methods() - Utility methods for language handling")
    
    print("\n" + "=" * 70)
    print("✨ To use these examples, uncomment the example functions below:")
    print("=" * 70)
    
    # Uncomment to run examples:
    example_auto_detect_stt()
    example_language_specific_tts()
    example_detect_and_respond()
    example_multilingual_call_script()
    example_multilingual_sentiment()
    example_translation()
    example_complete_call_flow()
    example_utility_methods()
