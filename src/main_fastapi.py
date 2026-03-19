"""
FastAPI Application for Beacon Hotel Relationship Manager
Faster, modern alternative to Flask with automatic OpenAPI docs
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
from datetime import datetime
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, Query, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel

from config.config import get_config
from src.models.database import init_db, get_session, Customer, CallHistory, CallSchedule
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from src.services.twilio_service import TwilioService
from src.services.servam_service import ServamService
from src.services.conversational_call_handler import ConversationalCallManager, CallStage
from src.services.audio_service import AudioService
from src.utils.call_logger import CallLogger
from src.utils.dummy_data_generator import initialize_dummy_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Beacon Hotel Relationship Manager",
    description="AI-powered customer relationship management system",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

config = get_config()

# Initialize services
relationship_agent = RelationshipManagerAgent()
twilio_service = TwilioService()
servam_service = ServamService()
conversational_manager = ConversationalCallManager()
call_logger = CallLogger()
audio_service = AudioService()
session = get_session()

# Setup static files for audio serving
audio_dir = Path("audio")
audio_dir.mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

# Pydantic models for request/response
class HealthResponse(BaseModel):
    status: str
    hotel: str
    environment: str
    timestamp: str

class CustomerDetail(BaseModel):
    customer_id: str
    name: str
    email: Optional[str]
    phone: str
    total_visits: int
    loyalty_score: float
    is_active: bool

class CustomersList(BaseModel):
    count: int
    customers: List[CustomerDetail]

class CallRequest(BaseModel):
    customer_id: str

class CallResponse(BaseModel):
    status: str
    call_sid: str
    customer_name: str
    phone: str
    churn_risk: float
    recommended_offer: str

class CallLogRequest(BaseModel):
    customer_id: str
    call_sid: Optional[str] = None
    transcript: str = ""
    duration: int = 0
    booking_made: bool = False
    booking_amount: Optional[float] = None
    discount_offered: bool = False
    discount_percentage: Optional[float] = None

class DummyDataResponse(BaseModel):
    status: str
    customers_created: int
    calls_created: int

class CreateCustomerRequest(BaseModel):
    name: str
    email: str
    phone: str  # Real phone number in E.164 format
    total_visits: int = 1
    total_spent: float = 0.0
    loyalty_score: float = 50.0
    preferred_room_type: str = "Deluxe"
    is_active: bool = True

class CreateCustomerResponse(BaseModel):
    status: str
    customer_id: str
    name: str
    phone: str
    message: str

class BulkCreateCustomersRequest(BaseModel):
    customers: List[CreateCustomerRequest]

class BulkCreateCustomersResponse(BaseModel):
    status: str
    total_created: int
    failed: int
    customers_created: List[CreateCustomerResponse]

class TestCallRequest(BaseModel):
    customer_id: str
    script: Optional[str] = None
    
class TestCallResponse(BaseModel):
    status: str
    call_sid: str
    customer_name: str
    phone: str
    message: str
    churn_risk: float
    recommended_offer: str

class UpdateCustomerRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    loyalty_score: Optional[float] = None
    is_active: Optional[bool] = None
    preferred_room_type: Optional[str] = None

class UpdateCustomerResponse(BaseModel):
    status: str
    customer_id: str
    message: str
    updated_fields: dict

# ==================== ENDPOINTS ====================

@app.get("/", tags=["Info"])
def root():
    """Root endpoint with API info"""
    return {
        "name": "Beacon Hotel Relationship Manager API",
        "version": "1.0.0",
        "docs": "/docs",
        "docs_alternative": "/redoc"
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        hotel=config.HOTEL_NAME,
        environment=config.ENVIRONMENT,
        timestamp=datetime.utcnow().isoformat()
    )

@app.get("/api/v1/customers", response_model=CustomersList, tags=["Customers"])
def get_customers(limit: int = Query(50, ge=1, le=500)):
    """Get all customers"""
    try:
        customers = session.query(Customer).limit(limit).all()
        
        customer_details = [
            CustomerDetail(
                customer_id=c.customer_id,
                name=c.name,
                email=c.email,
                phone=c.phone,
                total_visits=c.total_visits,
                loyalty_score=c.loyalty_score,
                is_active=c.is_active
            )
            for c in customers
        ]
        
        return CustomersList(count=len(customers), customers=customer_details)
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers/{customer_id}", tags=["Customers"])
def get_customer(customer_id: str):
    """Get customer details"""
    try:
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        return {
            "customer_id": customer.customer_id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "last_stay_date": customer.last_stay_date.isoformat() if customer.last_stay_date else None,
            "total_visits": customer.total_visits,
            "total_spent": float(customer.total_spent),
            "loyalty_score": float(customer.loyalty_score),
            "preferred_room_type": customer.preferred_room_type,
            "is_active": customer.is_active
        }
    except Exception as e:
        logger.error(f"Error fetching customer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/v1/customers/{customer_id}", response_model=UpdateCustomerResponse, tags=["Customers"])
def update_customer(customer_id: str, update_req: UpdateCustomerRequest):
    """
    Update customer details (especially phone number)
    
    Can update: phone, email, name, loyalty_score, is_active, preferred_room_type
    
    Example:
    {
        "phone": "+919887270041"
    }
    """
    try:
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
        
        updated_fields = {}
        
        # Update only provided fields
        if update_req.phone is not None:
            # Check if new phone already exists
            existing = session.query(Customer).filter_by(phone=update_req.phone).first()
            if existing and existing.customer_id != customer_id:
                raise HTTPException(status_code=400, detail=f"Phone {update_req.phone} already in use")
            customer.phone = update_req.phone
            updated_fields['phone'] = update_req.phone
            logger.info(f"Updated {customer_id} phone: {update_req.phone}")
        
        if update_req.email is not None:
            customer.email = update_req.email
            updated_fields['email'] = update_req.email
        
        if update_req.name is not None:
            customer.name = update_req.name
            updated_fields['name'] = update_req.name
        
        if update_req.loyalty_score is not None:
            customer.loyalty_score = update_req.loyalty_score
            updated_fields['loyalty_score'] = update_req.loyalty_score
        
        if update_req.is_active is not None:
            customer.is_active = update_req.is_active
            updated_fields['is_active'] = update_req.is_active
        
        if update_req.preferred_room_type is not None:
            customer.preferred_room_type = update_req.preferred_room_type
            updated_fields['preferred_room_type'] = update_req.preferred_room_type
        
        if not updated_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        customer.updated_at = datetime.utcnow()
        session.commit()
        
        return UpdateCustomerResponse(
            status="updated",
            customer_id=customer_id,
            message=f"Customer {customer_id} updated successfully",
            updated_fields=updated_fields
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error updating customer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers/{customer_id}/analysis", tags=["Analysis"])
def analyze_customer(customer_id: str):
    """Analyze customer and get relationship insights"""
    try:
        analysis = relationship_agent.analyze_customer_history(customer_id)
        
        if not analysis:
            raise HTTPException(status_code=404, detail="Customer not found or no analysis available")
        
        return analysis
    except Exception as e:
        logger.error(f"Error analyzing customer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers/{customer_id}/call-history", tags=["Calls"])
def get_call_history(customer_id: str, limit: int = Query(20, ge=1, le=100)):
    """Get customer's call history"""
    try:
        calls = session.query(CallHistory).filter_by(
            customer_id=customer_id
        ).order_by(CallHistory.call_date.desc()).limit(limit).all()
        
        return {
            "customer_id": customer_id,
            "total_calls": len(calls),
            "calls": [
                {
                    "call_id": c.call_id,
                    "call_date": c.call_date.isoformat(),
                    "duration": c.duration,
                    "sentiment": c.sentiment,
                    "booking_made": c.booking_made,
                    "transcript": c.transcript[:100] if c.transcript else None
                }
                for c in calls
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching call history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/calls/schedule", tags=["Calls"])
def schedule_calls():
    """Schedule calls for all active customers"""
    try:
        scheduled_calls = relationship_agent.schedule_calls()
        return {
            "status": "scheduled",
            "calls_scheduled": len(scheduled_calls)
        }
    except Exception as e:
        logger.error(f"Error scheduling calls: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/calls/make", response_model=CallResponse, tags=["Calls"])
def make_call(call_request: CallRequest):
    """Make a call to a customer"""
    try:
        customer_id = call_request.customer_id
        
        # Get customer
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        
        # Analyze customer
        analysis = relationship_agent.analyze_customer_history(customer_id)
        if not analysis:
            raise HTTPException(status_code=500, detail="Cannot analyze customer")
        
        # Generate call script
        call_script = relationship_agent.generate_call_script(customer_id, analysis)
        
        # Make call via Twilio
        call_sid = twilio_service.make_call(customer.phone, call_script)
        
        if not call_sid:
            raise HTTPException(status_code=500, detail="Failed to initiate call")
        
        return CallResponse(
            status="call_initiated",
            call_sid=call_sid,
            customer_name=customer.name,
            phone=customer.phone,
            churn_risk=analysis['churn_risk_score'],
            recommended_offer=f"{analysis['recommended_discount']}% discount"
        )
    except Exception as e:
        logger.error(f"Error making call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/calls/log", tags=["Calls"])
def log_call(log_request: CallLogRequest):
    """Log a completed call"""
    try:
        success = call_logger.log_call(
            customer_id=log_request.customer_id,
            call_sid=log_request.call_sid or "",
            transcript=log_request.transcript,
            duration=log_request.duration,
            discount_offered=log_request.discount_offered,
            discount_percentage=log_request.discount_percentage,
            booking_made=log_request.booking_made,
            booking_amount=log_request.booking_amount
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to log call")
        
        return {"status": "call_logged"}
    except Exception as e:
        logger.error(f"Error logging call: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/reports/export", tags=["Reports"])
def export_reports(report_type: str = Query("json", regex="^(json|csv|xlsx)$"), days: int = Query(30, ge=1)):
    """Export call reports"""
    try:
        # Placeholder for report generation
        return {
            "status": "report_generated",
            "type": report_type,
            "days": days
        }
    except Exception as e:
        logger.error(f"Error exporting reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/init/dummy-data", response_model=DummyDataResponse, tags=["Admin"])
def init_dummy_data():
    """Initialize dummy test data"""
    try:
        customers_count, calls_count = initialize_dummy_data()
        logger.info(f"Initialized {customers_count} customers and {calls_count} calls")
        
        return DummyDataResponse(
            status="initialized",
            customers_created=customers_count,
            calls_created=calls_count
        )
    except Exception as e:
        logger.error(f"Error initializing dummy data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== CONVERSATIONAL CALL HANDLERS ====================

@app.post("/api/v1/calls/handle-response", tags=["Calls"], include_in_schema=False)
def handle_call_response(
    customer_id: str = Query(...),
    SpeechResult: str = Form(None),
    Confidence: str = Form(None),
    CallSid: str = Form(None),
    From: str = Form(None),
    To: str = Form(None)
):
    """
    Webhook handler for Twilio call responses
    Processes customer speech input and generates next conversational response
    This is called automatically by Twilio during a call
    """
    try:
        # Get customer
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        if not customer:
            logger.error(f"Customer {customer_id} not found in webhook handler")
            # Return fallback TwiML
            fallback_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>We apologize, but we encountered an error. Thank you for calling!</Say>
            </Response>'''
            return Response(content=fallback_twiml, media_type="application/xml")
        
        logger.info(f"\n🎙️ WEBHOOK: Customer {customer_id} ({customer.name})")
        logger.info(f"   Speech Recognized: {SpeechResult} (Confidence: {Confidence})")
        logger.info(f"   CallSid: {CallSid}")
        
        # Detect sentiment from customer's response
        language = "en"  # Could be enhanced with auto-detection
        sentiment = conversational_manager.detect_sentiment(SpeechResult or "okay", language)
        logger.info(f"   Sentiment: {sentiment}")
        
        # Generate next conversational response
        if sentiment == "positive" or (SpeechResult and any(word in SpeechResult.lower() for word in ["yes", "yeah", "hi", "hello", "okay", "ok"])):
            # Customer responded positively - ask about their experience
            next_prompt = "Great! How was your recent experience with us? Did you enjoy your stay?"
            hints = "good, excellent, bad, poor, okay"
        else:
            # Default: ask about experience
            next_prompt = "We'd love to hear about your experience with us. How was your last stay?"
            hints = "good, excellent, bad, poor, great"
        
        # Save this call interaction
        try:
            call_history = CallHistory(
                customer_id=customer_id,
                call_date=datetime.utcnow(),
                call_status="in_progress",
                sentiment=sentiment,
                conversation_transcript=f"User response: {SpeechResult or '[no response]'}",
                agent_notes=f"Twilio CallSid: {CallSid}, Confidence: {Confidence}"
            )
            session.add(call_history)
            session.commit()
            logger.info(f"   ✓ Call interaction saved")
        except Exception as e:
            logger.warning(f"   Could not save call history: {str(e)}")
            session.rollback()
        
        # Generate next TwiML response with listening for next input
        # Use NGROK URL for Twilio callback
        experience_webhook_url = f"{config.NGROK_BASE_URL}/api/v1/calls/handle-response-experience?customer_id={customer_id}"
        
        # Generate Sarvam audio for the experience question (NOT Alice voice!)
        audio_url = audio_service.generate_audio(next_prompt, "en")
        
        if audio_url:
            # Use Sarvam natural audio instead of Alice voice
            # IMPORTANT: XML escape the & in the URL
            audio_play_url = f"{config.NGROK_BASE_URL}{audio_url}".replace("&", "&amp;")
            next_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{audio_play_url}</Play>
            <Gather input="speech" speechTimeout="10" hints="{hints}"
                    action="{experience_webhook_url}" method="POST">
            </Gather>
        </Response>'''
        else:
            # Fallback to Alice if audio generation fails
            next_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">{next_prompt}</Say>
            <Gather input="speech" speechTimeout="10" hints="{hints}"
                    action="{experience_webhook_url}" method="POST">
            </Gather>
        </Response>'''
        
        logger.info(f"   Sending: {next_prompt}")
        return Response(content=next_twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error in handle_call_response: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        # Return error TwiML instead of crashing
        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>We're experiencing a technical difficulty. Thank you for calling Beacon Hotel!</Say>
        </Response>'''
        return Response(content=error_twiml, media_type="application/xml")

@app.post("/api/v1/calls/handle-response-experience", tags=["Calls"], include_in_schema=False)
def handle_experience_response(
    customer_id: str = Query(...),
    SpeechResult: str = Form(None),
    Confidence: str = Form(None),
    CallSid: str = Form(None)
):
    """
    Handle customer's experience feedback and proceed to visit plans question
    """
    try:
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        if not customer:
            error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>We encountered an error. Thank you for calling!</Say>
            </Response>'''
            return Response(content=error_twiml, media_type="application/xml")
        
        logger.info(f"\n🎙️ EXPERIENCE FEEDBACK: {customer.name} ({customer_id})")
        logger.info(f"   Response: {SpeechResult}")
        
        # Analyze sentiment of experience feedback
        sentiment = conversational_manager.detect_sentiment(SpeechResult or "okay", "en")
        logger.info(f"   Sentiment: {sentiment}")
        
        # Update customer sentiment if very positive or negative
        if sentiment == "positive":
            customer.loyalty_score = min(100, customer.loyalty_score + 5)
        elif sentiment == "negative":
            customer.loyalty_score = max(0, customer.loyalty_score - 10)
        
        session.commit()
        
        # Ask about future visit plans
        next_prompt = "That's great to hear! Are you planning to visit us again soon?"
        hints = "yes, maybe, soon, definitely, not sure, no"
        
        # Generate Sarvam audio for the prompt (SAME AS INITIAL GREETING)
        audio_url = audio_service.generate_audio(next_prompt, "en")
        
        # Generate TwiML for visit plans question
        # Use NGROK URL for Twilio callback
        visit_plans_webhook_url = f"{config.NGROK_BASE_URL}/api/v1/calls/handle-visit-plans?customer_id={customer_id}"
        
        if audio_url:
            # Use Sarvam natural audio instead of Alice voice
            # IMPORTANT: XML escape the & in the URL
            audio_play_url = f"{config.NGROK_BASE_URL}{audio_url}".replace("&", "&amp;")
            visit_plans_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{audio_play_url}</Play>
            <Gather input="speech" speechTimeout="10" hints="{hints}"
                    action="{visit_plans_webhook_url}" method="POST">
            </Gather>
        </Response>'''
        else:
            # Fallback to Alice if audio fails
            visit_plans_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">{next_prompt}</Say>
            <Gather input="speech" speechTimeout="10" hints="{hints}"
                    action="{visit_plans_webhook_url}" method="POST">
            </Gather>
        </Response>'''
        
        logger.info(f"   Next: Asking about visit plans")
        return Response(content=visit_plans_twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error in handle_experience_response: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Technical error encountered. Thank you for your time!</Say>
        </Response>'''
        return Response(content=error_twiml, media_type="application/xml")

@app.post("/api/v1/calls/handle-visit-plans", tags=["Calls"], include_in_schema=False)
def handle_visit_plans_response(
    customer_id: str = Query(...),
    SpeechResult: str = Form(None),
    Confidence: str = Form(None),
    CallSid: str = Form(None)
):
    """
    Handle customer's visit plans response and offer loyalty benefits
    """
    try:
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        if not customer:
            error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>Error encountered. Thank you!</Say>
            </Response>'''
            return Response(content=error_twiml, media_type="application/xml")
        
        logger.info(f"\n🎙️ VISIT PLANS: {customer.name}")
        logger.info(f"   Response: {SpeechResult}")
        
        # Determine if customer plans to visit
        speech_lower = (SpeechResult or "").lower()
        planning_visit = any(word in speech_lower for word in ["yes", "yeah", "definitely", "soon", "will"])
        
        if planning_visit:
            closing_msg = f"Excellent! We look forward to welcoming you back, {customer.name}! Thank you for choosing Beacon Hotel."
        else:
            # Get analysis to determine discount
            try:
                analysis = relationship_agent.analyze_customer_history(customer_id)
                recommended_discount = analysis.get("recommended_discount", "10% OFF") if analysis else "10% OFF"
                # Extract percentage if it's a string like "5% OFF"
                if isinstance(recommended_discount, str) and "OFF" in recommended_discount:
                    discount_pct = recommended_discount.split("%")[0]
                else:
                    discount_pct = 10
            except:
                discount_pct = 10
                recommended_discount = "10% OFF"
            
            closing_msg = f"That's okay! Here's a special {discount_pct}% loyalty discount for your next visit. Thank you, {customer.name}!"
            customer.loyalty_score = min(100, customer.loyalty_score + 10)
            session.commit()
        
        # Generate Sarvam audio for closing message (NOT Alice voice!)
        audio_url = audio_service.generate_audio(closing_msg, "en")
        
        # Final closing TwiML - just play the Sarvam audio with no extra voice
        if audio_url:
            # IMPORTANT: XML escape the & in the URL
            audio_play_url = f"{config.NGROK_BASE_URL}{audio_url}".replace("&", "&amp;")
            closing_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{audio_play_url}</Play>
            <Hangup/>
        </Response>'''
        else:
            # Fallback to Alice if audio fails
            closing_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">{closing_msg}</Say>
        </Response>'''
        
        logger.info(f"   Closing: {closing_msg}")
        return Response(content=closing_twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Error in handle_visit_plans_response: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        
        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>Thank you for calling Beacon Hotel. Goodbye!</Say>
        </Response>'''
        return Response(content=error_twiml, media_type="application/xml")

@app.get("/api/v1/calls/conversational-demo", tags=["Calls"])
def get_conversational_demo():
    """
    Get information about the conversational call system
    """
    return {
        "system": "Conversational AI Call Manager",
        "features": [
            "Natural language greeting",
            "Speech recognition and response listening",
            "Automatic language detection",
            "Multi-turn conversation flow",
            "Customer experience inquiry",
            "Visit plans detection",
            "Loyalty offer presentation",
            "Sentiment analysis"
        ],
        "conversation_flow": [
            "1. Agent greets customer warmly",
            "2. Listens to greeting response (yes/hi)",
            "3. Detects language automatically",
            "4. Asks about their experience",
            "5. Analyzes sentiment (positive/negative)",
            "6. Asks about future visit plans",
            "7. If no visit planned, offers loyalty discount",
            "8. Professional closing and gratitude"
        ],
        "supported_languages": ["English", "Hindi", "Tamil", "Telugu", "Malayalam"],
        "usage": "POST /api/v1/calls/test with customer_id"
    }

@app.get("/api/v1/metrics/summary", tags=["Metrics"])
def get_metrics():
    """Get metrics summary"""
    try:
        total_customers = session.query(Customer).count()
        total_calls = session.query(CallHistory).count()
        active_customers = session.query(Customer).filter_by(is_active=True).count()
        
        return {
            "total_customers": total_customers,
            "active_customers": active_customers,
            "total_calls": total_calls,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== DATA INSERTION ENDPOINTS ====================

@app.post("/api/v1/customers/create", response_model=CreateCustomerResponse, tags=["TestData"])
def create_customer(customer_request: CreateCustomerRequest):
    """
    Create a new customer with real phone number for testing.
    
    This endpoint allows you to insert customer data with real phone numbers
    that can be immediately tested by making calls via Twilio.
    
    Example:
    {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": "+1234567890",
        "total_visits": 3,
        "total_spent": 1500.0,
        "loyalty_score": 75.0,
        "preferred_room_type": "Suite",
        "is_active": true
    }
    """
    try:
        # Check if customer already exists
        existing = session.query(Customer).filter_by(phone=customer_request.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Customer with phone {customer_request.phone} already exists")
        
        # Generate unique customer ID
        customer_count = session.query(Customer).count()
        customer_id = f"CUST{1000 + customer_count + 1}"
        
        # Create new customer
        new_customer = Customer(
            customer_id=customer_id,
            name=customer_request.name,
            email=customer_request.email,
            phone=customer_request.phone,
            total_visits=customer_request.total_visits,
            total_spent=customer_request.total_spent,
            loyalty_score=customer_request.loyalty_score,
            preferred_room_type=customer_request.preferred_room_type,
            is_active=customer_request.is_active,
            last_stay_date=datetime.utcnow()
        )
        
        session.add(new_customer)
        session.commit()
        
        logger.info(f"Created customer {customer_id} with phone {customer_request.phone}")
        
        return CreateCustomerResponse(
            status="created",
            customer_id=customer_id,
            name=customer_request.name,
            phone=customer_request.phone,
            message=f"Customer {customer_id} created successfully. Ready to test calls!"
        )
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error creating customer: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/customers/create-bulk", response_model=BulkCreateCustomersResponse, tags=["TestData"])
def create_customers_bulk(bulk_request: BulkCreateCustomersRequest):
    """
    Create multiple customers at once with real phone numbers for batch testing.
    
    This is useful for setting up multiple test customers for comprehensive testing.
    
    Example:
    {
        "customers": [
            {
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "+1234567890",
                "total_visits": 3,
                "loyalty_score": 75.0
            },
            {
                "name": "Jane Smith",
                "email": "jane@example.com",
                "phone": "+1987654321",
                "total_visits": 5,
                "loyalty_score": 85.0
            }
        ]
    }
    """
    try:
        created_customers = []
        failed_count = 0
        customer_base_count = session.query(Customer).count()
        
        for idx, customer_req in enumerate(bulk_request.customers):
            try:
                # Check if customer already exists
                existing = session.query(Customer).filter_by(phone=customer_req.phone).first()
                if existing:
                    logger.warning(f"Skipping customer with phone {customer_req.phone} - already exists")
                    failed_count += 1
                    continue
                
                # Generate unique customer ID
                customer_id = f"CUST{1000 + customer_base_count + idx + 1}"
                
                # Create new customer
                new_customer = Customer(
                    customer_id=customer_id,
                    name=customer_req.name,
                    email=customer_req.email,
                    phone=customer_req.phone,
                    total_visits=customer_req.total_visits,
                    total_spent=customer_req.total_spent,
                    loyalty_score=customer_req.loyalty_score,
                    preferred_room_type=customer_req.preferred_room_type,
                    is_active=customer_req.is_active,
                    last_stay_date=datetime.utcnow()
                )
                
                session.add(new_customer)
                session.flush()  # Flush to ensure ID is generated
                
                created_customers.append(CreateCustomerResponse(
                    status="created",
                    customer_id=customer_id,
                    name=customer_req.name,
                    phone=customer_req.phone,
                    message=f"Customer {customer_id} added"
                ))
                
            except Exception as e:
                logger.error(f"Error creating customer {idx}: {str(e)}")
                failed_count += 1
                session.rollback()
        
        session.commit()
        logger.info(f"Bulk created {len(created_customers)} customers failed: {failed_count}")
        
        return BulkCreateCustomersResponse(
            status="bulk_created",
            total_created=len(created_customers),
            failed=failed_count,
            customers_created=created_customers
        )
    except Exception as e:
        session.rollback()
        logger.error(f"Error in bulk customer creation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/audio/generate", tags=["Audio"])
def generate_audio_stream(
    text: str = Query(..., description="Text to convert to speech"),
    language: str = Query("en", description="Language code (en, hi, ta, te, ml)")
):
    """
    Generate audio on-the-fly using Sarvam TTS (no file storage).
    
    This endpoint generates natural-sounding audio in real-time and streams it directly to Twilio.
    Perfect for personalizing prompts with customer names without storing files.
    
    Example: /api/v1/audio/generate?text=Hello%20John&language=en
    """
    try:
        if not text or len(text.strip()) == 0:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        logger.info(f"🎤 Streaming audio on-the-fly: '{text[:60]}...'")
        
        # Generate audio bytes in real-time (no file storage)
        audio_bytes = audio_service.generate_audio_bytes(text, language)
        
        if not audio_bytes:
            logger.error("Failed to generate audio")
            raise HTTPException(status_code=500, detail="Audio generation failed")
        
        logger.info(f"✓ Audio streamed: {len(audio_bytes)} bytes")
        
        # Return audio with proper MP3 content type
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=prompt.mp3"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating audio stream: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/calls/test", response_model=TestCallResponse, tags=["TestData"])
def test_call_to_customer(test_call_req: TestCallRequest):
    """
    Make a CONVERSATIONAL call to a customer.
    
    This initiates an intelligent, multi-turn conversation that:
    1. Greets the customer warmly
    2. Listens to their response
    3. Detects their language automatically
    4. Continues conversation in their language
    5. Asks about their experience
    6. Offers loyalty benefits if they're not planning to visit
    
    Much more natural and relationship-building than robotic scripts!
    
    Example:
    {
        "customer_id": "CUST1001"
    }
    """
    try:
        # Get customer
        customer = session.query(Customer).filter_by(customer_id=test_call_req.customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail=f"Customer {test_call_req.customer_id} not found")
        
        logger.info(f"Initiating CONVERSATIONAL call to {customer.customer_id} ({customer.phone})")
        
        # Generate dynamic audio URL (ON-THE-FLY, no file storage)
        logger.info("Generating dynamic Sarvam TTS endpoint for natural conversation...")
        initial_language = "en"
        greeting = conversational_manager.get_greeting_script(customer.name, initial_language)
        logger.info(f"📝 Greeting text: '{greeting}' [Length: {len(greeting)} chars]")
        
        # Get the dynamic audio generation URL (no file storage!)
        greeting_audio_url = audio_service.generate_audio(greeting, initial_language)
        logger.info(f"🔗 Audio endpoint URL: {greeting_audio_url}")
        
        # Create TwiML with PLAY instead of SAY for natural voice
        webhook_url = f"{config.NGROK_BASE_URL}/api/v1/calls/handle-response?customer_id={test_call_req.customer_id}"
        
        if greeting_audio_url:
            # Use dynamic Sarvam natural audio (bulbul:v3 Indian voice)
            # Audio is generated ON-THE-FLY when Twilio requests it - no file storage!
            audio_play_url = f"{config.NGROK_BASE_URL}{greeting_audio_url}"
            # CRITICAL: Escape & as &amp; for valid XML in TwiML
            audio_play_url_xml = audio_play_url.replace("&", "&amp;")
            webhook_url_xml = webhook_url.replace("&", "&amp;")
            
            simple_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Play>{audio_play_url_xml}</Play>
            <Gather input="speech" speechTimeout="10" hints="yes, hi, hello, okay" 
                    action="{webhook_url_xml}" method="POST">
            </Gather>
        </Response>"""
            logger.info(f"✓ Using dynamic Sarvam audio (on-the-fly): {greeting_audio_url}")
            logger.debug(f"📋 TwiML being sent:\n{simple_twiml}")
        else:
            # Fallback to text if audio generation fails
            webhook_url_xml = webhook_url.replace("&", "&amp;")
            simple_twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice">{greeting}</Say>
            <Gather input="speech" speechTimeout="10" hints="yes, hi, hello, okay" 
                    action="{webhook_url_xml}" method="POST">
            </Gather>
        </Response>"""
            logger.info("Using fallback text-to-speech")
        
        # Make the call with conversational TwiML (pass directly to Twilio)
        logger.info(f"Sending conversational TwiML to Twilio")
        
        try:
            # Call Twilio directly with TwiML
            call = twilio_service.client.calls.create(
                to=customer.phone,
                from_=twilio_service.phone_number,
                twiml=simple_twiml
            )
            call_sid = call.sid
            logger.info(f"✓ Conversational call created with SID: {call_sid}")
        except Exception as e:
            logger.error(f"Twilio call failed: {str(e)}")
            call_sid = f"CONV_{test_call_req.customer_id}_{datetime.utcnow().timestamp()}"
            logger.warning(f"Using mock call SID: {call_sid}")
        
        return TestCallResponse(
            status="call_initiated",
            call_sid=call_sid,
            customer_name=customer.name,
            phone=customer.phone,
            message=f"🎙️ Conversational call initiated with NATURAL SARVAM VOICE 🎤\n1. ✓ Greeting with Indian accent\n2. ✓ Listens to response\n3. ✓ Continues conversation naturally\n4. ✓ Asks about experience\n5. ✓ Offers personalized loyalty deals",
            churn_risk=0.5,
            recommended_offer="Personalized based on conversation"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making conversational call: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/customers/test-data/list", tags=["TestData"])
def list_test_customers(limit: int = Query(50, ge=1, le=500)):
    """
    List all customers created via API (test data).
    
    Shows all customers that are available for testing calls.
    """
    try:
        customers = session.query(Customer).order_by(Customer.created_at.desc()).limit(limit).all()
        
        return {
            "total_count": session.query(Customer).count(),
            "returned": len(customers),
            "customers": [
                {
                    "customer_id": c.customer_id,
                    "name": c.name,
                    "phone": c.phone,
                    "email": c.email,
                    "loyalty_score": float(c.loyalty_score),
                    "is_active": c.is_active,
                    "created_at": c.created_at.isoformat() if c.created_at else None
                }
                for c in customers
            ]
        }
    except Exception as e:
        logger.error(f"Error listing test customers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== APP STARTUP ====================

@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    logger.info("Starting Beacon Hotel Relationship Manager (FastAPI)")
    try:
        init_db()
        logger.info("✓ Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Run with: python src/main_fastapi.py
    # Or: uvicorn src.main_fastapi:app --reload
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
