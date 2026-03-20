"""
Conversational Call Handler - Dynamic LLM-driven multi-turn conversation

Uses Sarvam AI for:
  - STT (speech_to_text): Convert user speech to text
  - LLM (generate_response): Dynamic dialogue based on conversation history
  - TTS (text_to_speech): Convert responses to natural audio

Flow (repeating loop):
  1. User speaks
  2. STT: Speech → Text
  3. Append user message to conversation history
  4. LLM: Generate next response based on ENTIRE history
  5. TTS: Response → Audio
  6. Play audio to user
  7. Loop back to step 1

CRITICAL: NOT using hardcoded flow (handle-response → handle-response-experience → handle-visit-plans)
Instead: Single webhook handles all steps, LLM drives conversation dynamically
"""
import logging
import json
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from src.models.database import get_session, CallHistory, Customer
from src.services.servam_service import ServamService
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

# Global conversation history storage (in production, use Redis/database)
# Key: call_sid, Value: {customer_id, language, messages: [{role, content}], turn_count, start_time}
CONVERSATION_HISTORY = {}


class ConversationalCallManager:
    """
    Manages LLM-driven multi-turn conversations with dynamic flow
    """
    
    def __init__(self):
        self.sarvam = ServamService()
        self.agent = RelationshipManagerAgent()
        self.session = get_session()
    
    # ==================== LANGUAGE DETECTION (Script-based) ====================
    
    def detect_language_from_script(self, text: str) -> str:
        """
        Detect language based on Unicode script ranges.
        Returns language code: 'en', 'hi', 'ta', 'te', 'ml', etc.
        
        Script ranges:
        - Devanagari (Hindi, Marathi): U+0900–U+097F
        - Tamil: U+0B80–U+0BFF
        - Telugu: U+0C00–U+0C7F
        - Malayalam: U+0D00–U+0D7F
        """
        if not text:
            return "en"
        
        devanagari_count = sum(1 for c in text if 0x0900 <= ord(c) <= 0x097F)
        tamil_count = sum(1 for c in text if 0x0B80 <= ord(c) <= 0x0BFF)
        telugu_count = sum(1 for c in text if 0x0C00 <= ord(c) <= 0x0C7F)
        malayalam_count = sum(1 for c in text if 0x0D00 <= ord(c) <= 0x0D7F)
        
        # Check if text contains Indian scripts
        if devanagari_count > 2:  # At least 3 Devanagari chars = Hindi
            return "hi"
        elif tamil_count > 2:
            return "ta"
        elif telugu_count > 2:
            return "te"
        elif malayalam_count > 2:
            return "ml"
        else:
            return "en"  # Default to English
    
    # ==================== CONVERSATION HISTORY MANAGEMENT ====================
    
    def init_conversation(self, call_sid: str, customer_id: str, language: str = "en") -> Optional[Dict]:
        """
        Initialize conversation history for a new call
        
        Args:
            call_sid: Twilio call ID
            customer_id: Customer ID
            language: Language code (en, hi, ta, etc)
            
        Returns:
            Conversation context dict
        """
        try:
            customer = self.session.query(Customer).filter_by(customer_id=customer_id).first()
            if not customer:
                logger.error(f"Customer {customer_id} not found")
                return None
            
            # System prompt - natural conversational style
            customer_context = f"""
Customer Profile:
- Name: {customer.name}
- Total Visits: {customer.total_visits}
- Loyalty Score: {customer.loyalty_score}
- Last Visit: {customer.last_stay_date.strftime('%B %Y') if customer.last_stay_date else 'Unknown'}
- Preferred Room: {customer.preferred_room_type or 'Not specified'}
"""
            
            system_message = f"""You are a warm, friendly hotel relationship manager having a genuine conversation with {customer.name}.

{customer_context}

HOW TO RESPOND (CRITICAL):
1. LISTEN & RESPOND - Always respond to what they just said, don't ignore their answer
2. ACKNOWLEDGE PREVIOUS ANSWERS - Reference what they told you earlier in the call
3. NATURAL FLOW - If they answered about experience, ask about specific details, not "tell me about experience" again
4. ONE IDEA PER TURN - Keep responses SHORT: 1-2 sentences max
5. CONTINUE CONVERSATION - Build on previous turns, don't ask the same question twice
6. BE WARM & GENUINE - Like talking to a friend, remember details they shared

CONVERSATION GUIDELINES:
- Acknowledge their mood/experience first, then follow up naturally
- If they shared an experience → ask specific follow-ups ("glad/sorry to hear... did you like...")
- If they shared future plans → build on that (timing, preferences, booking)
- If hesitant → understand why before offering discount
- Never jump to new topics - flow naturally from their answer

CRITICAL LANGUAGE RULE:
- Respond ONLY in {language}
- If they speak Hindi → respond in Hindi
- Do NOT translate to English
- Keep Hindi responses natural and friendly (use हाँ, ठीक है, आदि)

Language Context: {language}"""
            
            context = {
                "call_sid": call_sid,
                "customer_id": customer_id,
                "customer_name": customer.name,
                "language": language,
                "messages": [
                    {"role": "system", "content": system_message}
                ],
                "turn_count": 0,
                "start_time": datetime.utcnow(),
                "sentiment_history": []
            }
            
            CONVERSATION_HISTORY[call_sid] = context
            logger.info(f"✓ Conversation initialized: call_sid={call_sid}, customer={customer_id}, lang={language}")
            return context
        
        except Exception as e:
            logger.error(f"Error initializing conversation: {str(e)}")
            return None
    
    def get_conversation_context(self, call_sid: str) -> Optional[Dict]:
        """Get existing conversation context"""
        return CONVERSATION_HISTORY.get(call_sid)
    
    def append_user_message(self, call_sid: str, user_text: str) -> bool:
        """
        Append user message to conversation history & auto-detect language
        
        Args:
            call_sid: Twilio call ID
            user_text: User's spoken text
            
        Returns:
            True if successful
        """
        try:
            context = self.get_conversation_context(call_sid)
            if not context:
                logger.error(f"Conversation context not found: {call_sid}")
                return False
            
            context["messages"].append({
                "role": "user",
                "content": user_text
            })
            
            # 🌍 AUTO-DETECT LANGUAGE from user's text (script-based)
            # Keep current language on silence/empty/noise placeholders.
            normalized_text = (user_text or "").strip().lower()
            is_silence = normalized_text in ["", "[silence]", "silence", "...", "."]

            if not is_silence:
                detected_lang = self.detect_language_from_script(user_text)

                # Guard against abrupt non-English -> English flips for short/ambiguous text.
                if context["language"] != "en" and detected_lang == "en":
                    if len((user_text or "").strip()) < 8:
                        detected_lang = context["language"]

                if detected_lang != context["language"]:
                    logger.info(f"🌍 Language detected: {context['language']} → {detected_lang}")
                    context["language"] = detected_lang
            
            # Analyze sentiment
            sentiment_result = self.sarvam.analyze_sentiment(user_text, context["language"])
            sentiment = sentiment_result.get("sentiment", "neutral") if sentiment_result else "neutral"
            context["sentiment_history"].append(sentiment)
            
            logger.info(f"✓ User: {user_text[:50]}... (lang: {context['language']}, sentiment: {sentiment})")
            return True
        
        except Exception as e:
            logger.error(f"Error appending user message: {str(e)}")
            return False
    
    def append_agent_message(self, call_sid: str, agent_text: str) -> bool:
        """
        Append agent message to conversation history
        
        Args:
            call_sid: Twilio call ID
            agent_text: Agent's response text
            
        Returns:
            True if successful
        """
        try:
            context = self.get_conversation_context(call_sid)
            if not context:
                logger.error(f"Conversation context not found: {call_sid}")
                return False
            
            context["messages"].append({
                "role": "assistant",
                "content": agent_text
            })
            
            context["turn_count"] += 1
            logger.info(f"✓ Agent (turn {context['turn_count']}): {agent_text[:50]}...")
            return True
        
        except Exception as e:
            logger.error(f"Error appending agent message: {str(e)}")
            return False
    
    # ==================== LANGUAGE DETECTION (LLM-Based) ====================
    
    def detect_language_llm(self, text: str, current_language: str = "en") -> str:
        """
        Detect the language of user text using LLM
        
        Much more reliable than keyword matching!
        
        Args:
            text: User's text to analyze
            current_language: Current language (fallback if detection fails)
            
        Returns:
            Language code (en, hi, ta, te, ml) or current_language if detection fails
        """
        try:
            if not text or len(text.strip()) < 2:
                return current_language
            
            # Use LLM to detect language (with short timeout via max_tokens=10)
            detection_prompt = f"""Detect language. Return ONLY code: en/hi/ta/te/ml/mixed

Text: "{text[:100]}"

CODE ONLY:"""
            
            response = self.sarvam.client.chat.completions.create(
                model="sarvam-m",
                messages=[{"role": "user", "content": detection_prompt}],
                max_tokens=5,  # VERY short - just the code
                temperature=0.0  # Deterministic
            )
            
            if response and hasattr(response, 'choices') and len(response.choices) > 0:
                detected = response.choices[0].message.content.strip().lower()
                
                # Check if it's a recognized code
                recognized_langs = ["en", "hi", "ta", "te", "ml", "mixed"]
                if detected in recognized_langs:
                    if detected == "mixed":
                        logger.info(f"✓ LLM: Mixed language → using {current_language}")
                        return current_language
                    else:
                        logger.info(f"✓ LLM: Language detected as {detected}")
                        return detected
                else:
                    logger.debug(f"LLM returned unrecognized: {detected}")
                    return current_language
            
            logger.debug(f"LLM language detection empty, using current: {current_language}")
            return current_language
        
        except Exception as e:
            logger.debug(f"LLM language detection error (using {current_language}): {type(e).__name__}")
            return current_language
    
    # ==================== STT (Speech-to-Text) ====================
    
    def speech_to_text(self, call_sid: str, audio_data: bytes) -> Optional[str]:
        """
        Convert speech to text using Sarvam STT
        
        Args:
            call_sid: Twilio call ID
            audio_data: Audio bytes
            
        Returns:
            Transcribed text or None if failed
        """
        try:
            context = self.get_conversation_context(call_sid)
            if not context:
                logger.error(f"Conversation context not found: {call_sid}")
                return None
            
            language = context["language"]
            
            # STT using Sarvam
            logger.debug(f"Calling STT for audio ({len(audio_data)} bytes)...")
            stt_result = self.sarvam.speech_to_text(audio_data, language=language)
            
            if not stt_result:
                logger.warning("STT failed to transcribe audio")
                return None
            
            text = stt_result.get("text", "").strip()
            detected_lang = stt_result.get("language", language)
            confidence = stt_result.get("confidence", 0)
            
            logger.info(f"✓ STT: '{text}' (confidence: {confidence:.2%})")
            
            # Update language if detected
            if detected_lang and detected_lang != language and len(text) > 3:
                old_lang = context["language"]
                context["language"] = detected_lang
                logger.info(f"   Language updated: {old_lang} → {detected_lang}")
            
            return text
        
        except Exception as e:
            logger.error(f"Error in speech_to_text: {str(e)}")
            return None
    
    # ==================== LLM (Text Generation via Sarvam LLM) ====================
    
    def generate_next_response(self, call_sid: str) -> Optional[str]:
        """
        Generate next response using Sarvam LLM based on conversation history
        
        Smart triggers detect conversation flow without rigid turn logic:
        - Detect if user wants to end call ("bye", "busy", "not interested")
        - Detect if user mentions another visit
        - Detect complaints/concerns
        - Guide LLM to offer discount if engagement is low
        
        Args:
            call_sid: Twilio call ID
            
        Returns:
            Generated response text or None if failed
        """
        try:
            context = self.get_conversation_context(call_sid)
            if not context:
                logger.error(f"Conversation context not found: {call_sid}")
                return None
            
            # Get last user message for trigger detection
            last_user_msg = ""
            for msg in reversed(context["messages"]):
                if msg["role"] == "user":
                    last_user_msg = msg["content"].lower()
                    break
            
            # ============ SMART TRIGGER DETECTION ============
            
            # 1. Conversation end triggers
            end_keywords = ["bye", "goodbye", "thank you", "not interested", "busy right now", "call later", "don't call"]
            if any(word in last_user_msg for word in end_keywords):
                logger.info(f"🔴 END TRIGGER detected: '{last_user_msg[:50]}'")
                lang = context["language"]
                closing_offers = {
                    "en": "I understand! Before we go, we have a special 20% discount waiting for you on your next visit. Hope to see you soon!",
                    "hi": "समझता हूँ! जाने से पहले, हम आपके लिए अगली यात्रा पर 20% छूट दे रहे हैं। जल्दी मिलेंगे!",
                }
                return closing_offers.get(lang, closing_offers["en"])
            
            # 2. Visit intent triggers - offer discount if not willing
            no_visit_keywords = ["won't", "not planning", "don't think", "maybe later", "not soon", "not interested"]
            if any(word in last_user_msg for word in no_visit_keywords):
                logger.info(f"🟠 NO-VISIT TRIGGER detected: '{last_user_msg[:50]}'")
                lang = context["language"]
                discount_offers = {
                    "en": "I totally understand! How about this - we're offering our best guests 25% off their next stay. That might change your mind?",
                    "hi": "बिल्कुल समझता हूँ! लेकिन हमारे पास आपके लिए 25% की विशेष छूट है। क्या यह आपको फिर से आने के लिए प्रेरित करेगी?",
                }
                return discount_offers.get(lang, discount_offers["en"])
            
            # 3. Complaint/concern triggers
            negative_keywords = ["bad", "horrible", "terrible", "never", "wasted", "worst", "rude", "avoid"]
            if any(word in last_user_msg for word in negative_keywords):
                logger.info(f"🟠 COMPLAINT TRIGGER detected: '{last_user_msg[:50]}'")
                lang = context["language"]
                apology_responses = {
                    "en": "I'm truly sorry to hear that. We take feedback very seriously. Let me arrange a special recovery offer - 30% off your next stay to make things right?",
                    "hi": "मुझे खेद है। हम आपके अनुभव को सुधारना चाहते हैं। क्या 30% छूट आपको फिर से मौका देने में मदद करेगी?",
                }
                return apology_responses.get(lang, apology_responses["en"])
            
            # ============ NORMAL CONVERSATION (LLM-DRIVEN) ============
            
            # Check turn limit (safety cutoff)
            if context["turn_count"] >= 8:
                logger.info(f"⏹️ Max turns reached ({context['turn_count']}), gracefully ending call")
                lang = context["language"]
                closing = {
                    "en": "Thank you so much for chatting with us today! We hope to see you again soon. Take care!",
                    "hi": "आपसे बात करने के लिए बहुत-बहुत धन्यवाद! जल्दी मिलेंगे। अलविदा!",
                }
                return closing.get(lang, closing["en"])

            logger.debug(f"🟢 NORMAL FLOW (turn {context['turn_count']}): '{last_user_msg[:50]}'")
            
            # Build messages with system prompt + language instruction
            lang = context["language"]
            system_msg = context["messages"][0]["content"]
            
            # FORCEFUL language instruction (language already auto-detected from script)
            lang_names = {"en": "English", "hi": "हिंदी", "ta": "Tamil", "te": "Telugu", "ml": "Malayalam"}
            lang_instruction = f"""

🔴 MANDATORY - Respond in {lang_names.get(lang, 'English')} ONLY:
- If user speaks Hindi (हिंदी) → Respond in Hindi (हिंदी)
- If user speaks English → Respond in English
- Do NOT translate responses to English
- Do NOT mix languages
- Keep response SHORT: 1-2 sentences
- Keep the conversation focused: quickly ask visit intent, then offer, then close naturally
- Avoid repetitive probing questions or long back-and-forth

Conversation so far: {len(context['messages'])} messages. Reference previous answers when responding."""
            
            system_with_lang = system_msg + lang_instruction
            
            messages = [{"role": "system", "content": system_with_lang}] + context["messages"][1:]
            
            try:
                logger.debug(f"Calling LLM (turn {context['turn_count']}, lang={lang}, msgs={len(messages)})...")
                logger.debug(f"System prompt length: {len(system_with_lang)}")
                logger.debug(f"Last 3 messages: {messages[-3:] if len(messages) >= 3 else messages}")
                
                # Call LLM using safe wrapper (handles SDK version differences)
                agent_text = self.sarvam.call_llm_safe(
                    messages=messages,
                    model="sarvam-m",
                    max_tokens=200,  # Allow fuller responses
                    temperature=0.0  # Deterministic - follow instructions precisely
                )
                
                if not agent_text:
                    logger.error(f"LLM returned None")
                    return None
                
                if len(agent_text.strip()) == 0:
                    logger.error(f"LLM returned empty text")
                    return None
                
                # 🧠 Strip thinking tags if present (some LLMs return reasoning)
                # e.g., <think>reasoning...</think>actual response
                agent_text = re.sub(r'<think>.*?</think>\s*', '', agent_text, flags=re.DOTALL).strip()
                
                if len(agent_text) < 3:
                    logger.warning(f"LLM returned very short response after filtering: '{agent_text}'")
                    return None
                
                logger.info(f"✓ LLM response (turn {context['turn_count']}, lang={lang}): {agent_text[:80]}...")
                return agent_text
            
            except Exception as llm_err:
                logger.error(f"LLM API error: {type(llm_err).__name__}: {str(llm_err)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                return None
        
        except Exception as e:
            logger.error(f"Error in generate_next_response: {str(e)}")
            return None
    
    # ==================== TTS (Text-to-Speech) ====================
    
    def text_to_speech_url(self, agent_text: str, language: str) -> Optional[str]:
        """
        Convert text to speech and return endpoint URL (on-the-fly, no file storage)
        
        Args:
            agent_text: Text to convert
            language: Language code
            
        Returns:
            URL to audio endpoint or None if failed
        """
        try:
            # Validate text is not empty
            if not agent_text or not isinstance(agent_text, str) or len(agent_text.strip()) == 0:
                logger.error(f"❌ TTS error: Empty or invalid text provided")
                return None
            
            import urllib.parse
            
            # URL encode the text
            encoded_text = urllib.parse.quote(agent_text.strip())
            audio_url = f"/api/v1/audio/generate?text={encoded_text}&language={language}"
            
            logger.info(f"✓ TTS URL generated: {language} ({len(agent_text)} chars)")
            return audio_url
        
        except Exception as e:
            logger.error(f"Error in text_to_speech_url: {str(e)}")
            return None
    
    # ==================== CALL MANAGEMENT ====================
    
    def end_conversation(self, call_sid: str) -> Optional[Dict]:
        """
        End conversation and save to database
        
        Args:
            call_sid: Twilio call ID
            
        Returns:
            Conversation summary
        """
        try:
            context = self.get_conversation_context(call_sid)
            if not context:
                logger.warning(f"Conversation context not found: {call_sid}")
                return None
            
            customer_id = context["customer_id"]
            duration = (datetime.utcnow() - context["start_time"]).total_seconds()
            
            # Extract conversation for storage (skip system message)
            conversation_text = "\n".join([
                f"{msg['role'].upper()}: {msg['content']}"
                for msg in context["messages"][1:]  # Skip system message
            ])
            
            # Analyze overall sentiment
            if context["sentiment_history"]:
                positive_count = sum(1 for s in context["sentiment_history"] if s == "positive")
                negative_count = sum(1 for s in context["sentiment_history"] if s == "negative")
                overall_sentiment = "positive" if positive_count > negative_count else ("negative" if negative_count > positive_count else "neutral")
            else:
                overall_sentiment = "neutral"
            
            # Save to database
            call_record = CallHistory(
                customer_id=customer_id,
                call_date=datetime.utcnow(),
                call_duration=int(duration),
                call_status="completed",
                conversation_transcript=conversation_text,
                sentiment=overall_sentiment,
                agent_notes=f"LLM-driven, Turns: {context['turn_count']}, Language: {context['language']}"
            )
            self.session.add(call_record)
            self.session.commit()
            
            # Clean up conversation
            del CONVERSATION_HISTORY[call_sid]
            
            logger.info(f"✓ Call ended: customer={customer_id}, duration={int(duration)}s, turns={context['turn_count']}, sentiment={overall_sentiment}")
            
            return {
                "customer_id": customer_id,
                "duration": int(duration),
                "turns": context["turn_count"],
                "sentiment": overall_sentiment
            }
        
        except Exception as e:
            logger.error(f"Error ending conversation: {str(e)}")
            return None
    
    def get_greeting(self, customer_name: str, language: str = "en") -> str:
        """Get personalized greeting"""
        greetings = {
            "en": f"Hello {customer_name}! This is calling from Beacon Hotel. How are you doing today?",
            "hi": f"नमस्ते {customer_name}! यह बीकन होटल की ओर से कॉल है। आप कैसे हैं?",
            "ta": f"வணக்கம் {customer_name}! பீகன் ஹோட்டலில் இருந்து அழைக்கிறோம்.",
            "te": f"హలో {customer_name}! బీకన్ హోటల్ నుండి కాల్ చేస్తున్నాం.",
            "ml": f"ഹലോ {customer_name}! ബീകൻ ഹോട്ടലിൽ നിന്നുള്ള കോൾ ആണ്.",
        }
        return greetings.get(language, greetings["en"])
    
    def get_next_twiml(self, audio_url: str, webhook_url: str, language: str = "en") -> str:
        """
        Generate TwiML for playing audio and recording user response
        
        Uses Twilio <Record> to capture raw audio → Sarvam STT for transcription
        (NOT Twilio's limited STT)
        
        Args:
            audio_url: URL to audio file to play
            webhook_url: Webhook URL to receive recording URL
            language: Language code (en, hi, ta, te, ml) - passed to webhook
            
        Returns:
            TwiML XML string
        """
        try:
            # Escape URLs for XML
            audio_url_xml = audio_url.replace("&", "&amp;")

            # Add language to callback URL
            separator = "&" if "?" in webhook_url else "?"
            callback_url = f"{webhook_url}{separator}language={language}"
            callback_url_xml = callback_url.replace("&", "&amp;")

            # IMPORTANT:
            # - action: controls call flow and expects TwiML response (used for conversation loop)
            # If action is missing, Twilio can complete the <Record> and then end the call.
            # NOTE: Avoid using recordingStatusCallback here with the same webhook,
            # otherwise the same recording may be processed twice.
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Play>{audio_url_xml}</Play>
                <Record maxLength="30" timeout="5" playBeep="true"
                        action="{callback_url_xml}" method="POST"
                        />
            </Response>"""
            
            logger.debug(f"Generated TwiML with Record (using Sarvam STT for lang={language})")
            return twiml
        
        except Exception as e:
            logger.error(f"Error generating TwiML: {str(e)}")
            return """<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>Thank you for your time.</Say>
            </Response>"""
    
    def get_greeting_script(self, customer_name: str, detected_language: str = "en") -> str:
        """
        Generate warm greeting based on language and customer info
        IMPORTANT: This returns ONLY the greeting, NOT the prompt!
        The prompt "Please say yes or hi to continue" is added separately in TwiML Gather tag.
        
        Args:
            customer_name: Customer's name
            detected_language: Language code (en, hi, etc)
            
        Returns:
            Greeting script in appropriate language (without prompt)
        """
        greetings = {
            "en": f"Hello {customer_name}! This is calling from Beacon Hotel. How are you doing today?",
            "hi": f"नमस्ते {customer_name}! यह बीकन होटल की ओर से कॉल है। आप कैसे हैं?",
            "ta": f"வணக்கம் {customer_name}! பீகன் ஹோட்டலில் இருந்து அழைக்கிறோம். நீங்கள் எப்படி இருக்கிறீர்கள்?",
            "te": f"హలో {customer_name}! బీకన్ హోటల్ నుండి కాల్ చేస్తున్నాం. మీరు ఎలా ఉన్నారు?",
            "ml": f"ഹലോ {customer_name}! ബീകൻ ഹോട്ടലിൽ നിന്നുള്ള കോൾ ആണ്. നിങ്ങൾ എങ്ങനെയുണ്ട്?"
        }
        return greetings.get(detected_language, greetings["en"])
    
    def get_experience_question(self, customer_name: str, language: str) -> str:
        """Ask about customer's experience at hotel"""
        questions = {
            "en": f"That's wonderful {customer_name}! I'm so glad to hear. How was your last experience with us at Beacon Hotel? Was everything good?",
            "hi": f"बहुत अच्छा {customer_name}! मुझे खुशी है। बीकन होटल में आपका अनुभव कैसा रहा? क्या सब कुछ ठीक था?",
            "ta": f"அருமை {customer_name}! என்னுடைய மகிழ்ச்சி. பீகன் ஹோட்டலில் உங்கள் அனுபவம் எப்படி இருந்தது? நல்லிருந்ததா?",
        }
        return questions.get(language, questions["en"])
    
    def get_visit_plans_question(self, customer_name: str, language: str) -> str:
        """Ask about future visit plans"""
        questions = {
            "en": f"Thank you for sharing that {customer_name}! That's wonderful to hear. Are you planning to visit us again soon? We'd love to see you!",
            "hi": f"वह शेयर करने के लिए धन्यवाद {customer_name}! क्या आप जल्द ही हमसे फिर से मिलने की योजना बना रहे हैं?",
            "ta": f"அதை சொல்லியதற்கு நன்றி {customer_name}! நீங்கள் மீண்டும் வர திட்டம் இருக்கிறதா?",
        }
        return questions.get(language, questions["en"])
    
    def get_loyalty_offer(self, customer_name: str, discount: float, language: str) -> str:
        """Present loyalty offer"""
        offers = {
            "en": f"Since you're such a valued guest {customer_name}, we have an exclusive {int(discount)}% loyalty discount waiting for you! We'd love to welcome you back. Shall I transfer you to our booking team?",
            "hi": f"{customer_name}, आप हमारे मूल्यवान अतिथि हैं। हमारे पास आपके लिए {int(discount)}% की विशेष छूट है! क्या आप बुकिंग टीम से बात करना चाहेंगे?",
            "ta": f"{customer_name}, நீங்கள் எங்களின் மূல்யமான விருந்தினர்! உங்களுக்கு {int(discount)}% ছাড் உள்ளது! புককிங் டீமுடன் பேச விரும்புகிறீர்களா?",
        }
        return offers.get(language, offers["en"])
    
    def create_twiml_with_listen(self, text_to_say: str, action_url: str, 
                                 num_digits: int = 0, hint: str = "speech") -> str:
        """
        Create TwiML that plays text AND listens for response
        
        Args:
            text_to_say: Text for TTS
            action_url: Webhook URL for processing response
            num_digits: If >0, expect keypresses; if 0, expect speech
            hint: For speech recognition ("yes no", "currency", "speech" etc)
            
        Returns:
            TwiML XML string
        """
        if num_digits > 0:
            # Listen for keypress
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>{text_to_say}</Say>
                <Gather numDigits="{num_digits}" timeout="5" action="{action_url}" method="POST">
                    <Say>Press 1 for yes, 2 for no, or just speak your response.</Say>
                </Gather>
                <Fallback>
                    <Say>Sorry, I didn't catch that. Let me transfer you to our team.</Say>
                </Fallback>
            </Response>"""
        else:
            # Listen for speech (speech recognition)
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>{text_to_say}</Say>
                <Gather input="speech" speechTimeout="auto" hints="{hint}" 
                        action="{action_url}" method="POST">
                    <Say>Please tell me your response.</Say>
                </Gather>
                <Fallback>
                    <Say>Sorry, I didn't catch that. Please try again.</Say>
                </Fallback>
            </Response>"""
        
        return twiml
