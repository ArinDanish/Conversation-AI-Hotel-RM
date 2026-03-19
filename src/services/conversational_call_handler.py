"""
Conversational Call Handler - Multi-turn IVR with AI conversation
Uses Sarvam AI for STT, Language Detection, and TTS
Manages conversation flow and engagement
"""
import logging
from datetime import datetime
from typing import Optional, Dict
from enum import Enum
from src.models.database import get_session, CallHistory, Customer
from src.services.servam_service import ServamService
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

class CallStage(Enum):
    """Stages of a conversational call"""
    GREETING = "greeting"
    LISTENING_GREETING_RESPONSE = "listening_greeting"
    ASKING_EXPERIENCE = "asking_experience"
    LISTENING_EXPERIENCE = "listening_experience"
    ASKING_VISIT_PLANS = "asking_visit_plans"
    LISTENING_VISIT_PLANS = "listening_visit_plans"
    OFFERING_LOYALTY = "offering_loyalty"
    COLLECTING_FEEDBACK = "collecting_feedback"
    CLOSING = "closing"

class ConversationalCallManager:
    """Manages conversational multi-turn calls with AI"""
    
    def __init__(self):
        self.sarvam = ServamService()
        self.agent = RelationshipManagerAgent()
        self.session = get_session()
        self.call_context = {}  # Store call state
    
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
    
    def save_call_interaction(self, customer_id: str, stage: CallStage, 
                             user_input: str, agent_response: str, 
                             language: str, sentiment: str = "neutral") -> None:
        """Save conversation turn to database"""
        try:
            call = CallHistory(
                customer_id=customer_id,
                call_date=datetime.utcnow(),
                conversation_transcript=f"[{stage.value}]\nAgent: {agent_response}\nCustomer: {user_input}",
                sentiment=sentiment,
                call_status="in_progress"
            )
            self.session.add(call)
            self.session.commit()
            logger.info(f"Saved interaction for {customer_id} at stage {stage.value}")
        except Exception as e:
            logger.error(f"Error saving interaction: {str(e)}")
            self.session.rollback()
    
    def detect_sentiment(self, text: str, language: str = "en") -> str:
        """
        Detect sentiment from customer response
        
        Args:
            text: Customer response
            language: Language of text
            
        Returns:
            Sentiment: positive, negative, neutral
        """
        positive_words = {
            "en": ["good", "great", "wonderful", "excellent", "amazing", "perfect", "yes", "love", "enjoy"],
            "hi": ["अच्छा", "बहुत अच्छा", "शानदार", "हां", "बहुत बढ़िया"],
            "ta": ["நல்ல", "அருமை", "ஆம்", "சிறந்த"]
        }
        
        negative_words = {
            "en": ["bad", "poor", "terrible", "awful", "no", "hate", "worst", "horrible"],
            "hi": ["बुरा", "गरीब", "भयानक", "नहीं"],
            "ta": ["மோசம்", "மோசமான", "இல்லை"]
        }
        
        text_lower = text.lower()
        lang_pos = positive_words.get(language, positive_words["en"])
        lang_neg = negative_words.get(language, negative_words["en"])
        
        pos_count = sum(1 for word in lang_pos if word in text_lower)
        neg_count = sum(1 for word in lang_neg if word in text_lower)
        
        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"
    
    def generate_next_response(self, customer_id: str, current_stage: CallStage,
                              customer_input: str, language: str) -> tuple:
        """
        AI-driven response generation based on conversation flow
        
        Returns:
            (next_stage, response_text, should_close_call)
        """
        try:
            customer = self.session.query(Customer).filter_by(customer_id=customer_id).first()
            if not customer:
                return CallStage.CLOSING, "Thank you for your time!", True
            
            sentiment = self.detect_sentiment(customer_input, language)
            
            # Conversation flow logic
            if current_stage == CallStage.LISTENING_GREETING_RESPONSE:
                # Move to experience question
                response = self.get_experience_question(customer.name, language)
                return CallStage.ASKING_EXPERIENCE, response, False
            
            elif current_stage == CallStage.LISTENING_EXPERIENCE:
                if sentiment == "positive":
                    response = self.get_visit_plans_question(customer.name, language)
                    return CallStage.ASKING_VISIT_PLANS, response, False
                else:
                    # For negative feedback, offer support
                    response = "I'm sorry to hear that. Would you like me to connect you with our manager to address your concerns?"
                    return CallStage.COLLECTING_FEEDBACK, response, False
            
            elif current_stage == CallStage.LISTENING_VISIT_PLANS:
                if "no" in customer_input.lower() or "not" in customer_input.lower():
                    # Offer loyalty discount
                    analysis = self.agent.analyze_customer_history(customer_id)
                    discount = analysis.get("recommended_discount", 15) if analysis else 15
                    response = self.get_loyalty_offer(customer.name, discount, language)
                    return CallStage.OFFERING_LOYALTY, response, False
                else:
                    closing = {
                        "en": f"That's wonderful {customer.name}! We're excited to welcome you. Our team will send you details shortly. Thank you for choosing Beacon Hotel!",
                        "hi": f"बहुत अच्छा {customer.name}! हमारी टीम आपको विवरण भेजेगी। धन्यवाद!",
                    }
                    return CallStage.CLOSING, closing.get(language, closing["en"]), True
            
            elif current_stage == CallStage.OFFERING_LOYALTY:
                closing = {
                    "en": f"Thank you {customer.name}! We hope to see you soon. Have a wonderful day!",
                    "hi": f"धन्यवाद {customer.name}! आपका दिन शुभ हो!"
                }
                return CallStage.CLOSING, closing.get(language, closing["en"]), True
            
            else:
                return CallStage.CLOSING, "Thank you for your time!", True
        
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return CallStage.CLOSING, "Thank you. Goodbye!", True
    
    def start_conversational_call(self, customer_id: str, customer_phone: str,
                                 initial_language: str = "en") -> str:
        """
        Initiate a conversational call with proper TwiML
        
        Returns:
            TwiML for initial greeting
        """
        try:
            customer = self.session.query(Customer).filter_by(customer_id=customer_id).first()
            if not customer:
                logger.error(f"Customer {customer_id} not found")
                return "<Response><Say>Customer not found.</Say></Response>"
            
            # Generate greeting
            greeting = self.get_greeting_script(customer.name, initial_language)
            
            # Create TwiML that listens for "yes" or "hi"
            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say voice="alice">{greeting}</Say>
                <Gather input="speech" speechTimeout="5" hints="yes, hi, hello, yeah"
                        action="/api/v1/calls/handle-response" method="POST">
                    <Say>Please say yes or hi to continue.</Say>
                </Gather>
            </Response>"""
            
            # Store call context
            self.call_context[customer_id] = {
                "stage": CallStage.LISTENING_GREETING_RESPONSE,
                "language": initial_language,
                "customer_phone": customer_phone,
                "start_time": datetime.utcnow()
            }
            
            logger.info(f"Started conversational call for {customer_id}")
            return twiml
        
        except Exception as e:
            logger.error(f"Error starting conversational call: {str(e)}")
            return "<Response><Say>Error initiating call.</Say></Response>"

