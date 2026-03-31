"""
FastAPI Application for Beacon Hotel Relationship Manager
Faster, modern alternative to Flask with automatic OpenAPI docs
"""
from src.utils.dummy_data_generator import initialize_dummy_data
from src.utils.call_logger import CallLogger
from src.services.livekit_sip_agent import LiveKitSIPAgentService, LIVEKIT_AGENTS_AVAILABLE
from src.services.livekit_streaming_service import LiveKitStreamingService
from src.services.audio_service import AudioService
from src.services.conversational_call_handler import ConversationalCallManager
from src.services.servam_service import ServamService
from src.services.twilio_service import TwilioService
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from src.models.database import init_db, get_session, Customer, CallHistory, CallSchedule
from config.config import get_config
from pydantic import BaseModel
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query, Form, WebSocket, WebSocketDisconnect
import wave
import io
import audioop
import json
import base64
import uuid
import asyncio
from typing import List, Optional, Dict
from datetime import datetime
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))


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
livekit_streaming_service = LiveKitStreamingService()
livekit_sip_service = LiveKitSIPAgentService()
session = get_session()

# Track processed Twilio recordings to avoid duplicate processing from retries/callback races
PROCESSED_RECORDING_SIDS = set()
PROCESSED_STREAM_UTTERANCES = set()

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
    streaming_mode: bool = True
    language: str = "unknown"
    stream_call: bool = True


class TestCallResponse(BaseModel):
    status: str
    call_sid: str
    customer_name: str
    phone: str
    message: str
    churn_risk: float
    recommended_offer: str
    websocket_url: Optional[str] = None
    workflow: Optional[str] = None
    input_format: Optional[str] = None
    output_format: Optional[str] = None


class LiveKitSIPCallRequest(BaseModel):
    customer_id: str
    language: str = "en"
    custom_prompt: str = None


class LiveKitSIPCallResponse(BaseModel):
    status: str
    room_name: str
    customer_name: str
    phone: str
    message: str
    workflow: str


def _build_twilio_stream_twiml(say_text: str, stream_url: str, customer_id: str, conv_id: str) -> str:
    safe_text = (say_text or "").replace(
        "&", "and").replace("<", " ").replace(">", " ")
    safe_stream_url = stream_url.replace("&", "&amp;")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say>{safe_text}</Say>
        <Connect>
            <Stream url="{safe_stream_url}">
                <Parameter name="customer_id" value="{customer_id}" />
                <Parameter name="conv_id" value="{conv_id}" />
            </Stream>
        </Connect>
        <Pause length="120"/>
    </Response>'''


def _build_twilio_stream_play_twiml(audio_url: str, stream_url: str, customer_id: str, conv_id: str) -> str:
    safe_audio_url = audio_url.replace("&", "&amp;")
    safe_stream_url = stream_url.replace("&", "&amp;")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play>{safe_audio_url}</Play>
        <Connect>
            <Stream url="{safe_stream_url}">
                <Parameter name="customer_id" value="{customer_id}" />
                <Parameter name="conv_id" value="{conv_id}" />
            </Stream>
        </Connect>
        <Pause length="120"/>
    </Response>'''


def _build_twilio_hangup_play_twiml(audio_url: str) -> str:
    """Play closing audio and hang up — no new stream opened."""
    safe_audio_url = audio_url.replace("&", "&amp;")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Play>{safe_audio_url}</Play>
        <Pause length="2"/>
        <Hangup/>
    </Response>'''


def _build_twilio_hangup_say_twiml(text: str) -> str:
    """Say closing text and hang up — no new stream opened."""
    safe_text = (text or "").replace(
        "&", "and").replace("<", " ").replace(">", " ")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say>{safe_text}</Say>
        <Pause length="2"/>
        <Hangup/>
    </Response>'''


def _http_to_ws_url(url: str) -> str:
    return url.replace("https://", "wss://").replace("http://", "ws://")


def _pcm16_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 8000, channels: int = 1) -> bytes:
    """Wrap raw PCM16 mono audio into a valid WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


class LiveKitStreamingSessionRequest(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = "Guest"
    language: str = "unknown"


class LiveKitStreamingSessionResponse(BaseModel):
    status: str
    session_id: str
    websocket_url: str
    workflow: str
    input_format: str
    output_format: str


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
        customer = session.query(Customer).filter_by(
            customer_id=customer_id).first()

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
        customer = session.query(Customer).filter_by(
            customer_id=customer_id).first()

        if not customer:
            raise HTTPException(
                status_code=404, detail=f"Customer {customer_id} not found")

        updated_fields = {}

        # Update only provided fields
        if update_req.phone is not None:
            # Check if new phone already exists
            existing = session.query(Customer).filter_by(
                phone=update_req.phone).first()
            if existing and existing.customer_id != customer_id:
                raise HTTPException(
                    status_code=400, detail=f"Phone {update_req.phone} already in use")
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
            raise HTTPException(
                status_code=404, detail="Customer not found or no analysis available")

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
                    "id": c.id,
                    "call_date": c.call_date.isoformat() if c.call_date else None,
                    "duration": c.call_duration,
                    "status": c.call_status,
                    "sentiment": c.sentiment,
                    "transcript": c.conversation_transcript[:100] if c.conversation_transcript else None,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "recording_url": f"http://localhost:8000/audio/call_{c.id}.wav" if c.conversation_transcript else None
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
        customer = session.query(Customer).filter_by(
            customer_id=customer_id).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        # Analyze customer
        analysis = relationship_agent.analyze_customer_history(customer_id)
        if not analysis:
            raise HTTPException(
                status_code=500, detail="Cannot analyze customer")

        # Generate call script
        call_script = relationship_agent.generate_call_script(
            customer_id, analysis)

        # Make call via Twilio
        call_sid = twilio_service.make_call(customer.phone, call_script)

        if not call_sid:
            raise HTTPException(
                status_code=500, detail="Failed to initiate call")

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
        logger.info(
            f"Initialized {customers_count} customers and {calls_count} calls")

        return DummyDataResponse(
            status="initialized",
            customers_created=customers_count,
            calls_created=calls_count
        )
    except Exception as e:
        logger.error(f"Error initializing dummy data: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== CONVERSATIONAL CALL HANDLERS ====================


@app.post("/api/v1/calls/handle-conversational-response", tags=["Calls"], include_in_schema=False)
def handle_conversational_response(
    call_sid: str = Query(None),
    customer_id: str = Query(None),
    SpeechResult: str = Form(None),
    Confidence: str = Form(None),
    CallSid: str = Form(None),
    RecordingUrl: str = Form(None),
    RecordingSid: str = Form(None),
    RecordingDuration: str = Form(None),
    language: str = Query("en")
):
    """
    Dynamic LLM-driven webhook for conversational calls

    Handles BOTH:
    - RecordingUrl (from <Record> + recordingStatusCallback) → Send to Sarvam STT
    - SpeechResult (from legacy <Gather>) → Use directly

    Flow:
    1. Get recording audio (if RecordingUrl) → Send to Sarvam STT for transcription
    2. Get conversation context
    3. Append user message to history + auto-detect language
    4. Generate LLM response (using full history)
    5. Generate TTS audio URL (on-the-fly)
    6. Append agent response to history
    7. Return TwiML to Record + play (loop)

    Called by Twilio when:
    - Recording completes (recordingStatusCallback)
    - User hangs up or timeout
    """
    try:
        # ======== STEP 1: Get user's speech transcription ========

        # Handle BOTH scenarios:
        # 1. New approach: <Record> with recordingStatusCallback sends RecordingUrl
        # 2. Old approach: <Gather> with speechResult sends SpeechResult

        user_speech = None

        if RecordingUrl:
            logger.info(
                f"\n🎙️ RECORDING RECEIVED: {RecordingUrl} (duration: {RecordingDuration}s)")
            logger.info(f"   Sending to Sarvam STT (language: {language})...")

            try:
                # Extract Recording SID from URL
                # Format: https://api.twilio.com/.../Recordings/RE{SID}
                recording_sid = RecordingSid or RecordingUrl.split("/")[-1]
                if "." in recording_sid:
                    recording_sid = recording_sid.split(".")[0]
                logger.debug(f"   Extracted Recording SID: {recording_sid}")

                # Dedupe duplicate callbacks for same recording
                if recording_sid in PROCESSED_RECORDING_SIDS:
                    logger.info(
                        f"   ↩️ Duplicate recording callback ignored: {recording_sid}")
                    noop_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
                    <Response></Response>'''
                    return Response(content=noop_twiml, media_type="application/xml")
                PROCESSED_RECORDING_SIDS.add(recording_sid)

                # Construct the proper WAV download URL
                # Twilio requires the full URI for authenticated download
                wav_url = f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Recordings/{recording_sid}.wav"
                logger.debug(f"   WAV URL: {wav_url}")

                # Use requests with Twilio basic auth
                import requests
                from requests.auth import HTTPBasicAuth

                auth = HTTPBasicAuth(
                    config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
                response = requests.get(wav_url, auth=auth, timeout=10)

                if response.status_code == 200:
                    audio_bytes = response.content
                    logger.debug(
                        f"   ✅ Downloaded {len(audio_bytes)} bytes from Twilio")

                    # Send to Sarvam STT
                    stt_language = "unknown"
                    if language and language.lower() not in ["en", "unknown"]:
                        stt_language = conversational_manager.sarvam.get_language_code(
                            language)
                    # Sarvam STT accepts en-IN, not en-US
                    if stt_language == "en-US":
                        stt_language = "en-IN"

                    stt_result = conversational_manager.sarvam.speech_to_text(
                        audio_data=audio_bytes,
                        language=stt_language
                    )

                    if stt_result and stt_result.get('text'):
                        user_speech = stt_result['text']
                        detected_lang = stt_result.get('language', language)
                        logger.info(
                            f"   ✓ Sarvam STT: '{user_speech}' (detected_lang={detected_lang})")
                    else:
                        logger.warning(
                            "   Sarvam STT returned empty transcription")
                        user_speech = "[silence]"
                else:
                    logger.error(
                        f"   ❌ Failed to download recording: HTTP {response.status_code}")
                    logger.error(f"   Response: {response.text[:200]}")
                    user_speech = "[silence]"

            except Exception as stt_err:
                logger.error(
                    f"   Error processing recording: {type(stt_err).__name__}: {str(stt_err)}")
                import traceback
                logger.error(traceback.format_exc())
                user_speech = "[silence]"

        elif SpeechResult:
            # Fallback to Twilio's transcription if available
            user_speech = SpeechResult
            logger.info(
                f"\n🎙️ TWILIO TRANSCRIPTION: '{user_speech}' (confidence: {Confidence})")

        else:
            logger.warning("No speech or recording received")
            user_speech = "[silence]"

        # ======== STEP 2: Get conversation context ========
        logger.info(
            f"   call_sid={call_sid}, customer_id={customer_id}, CallSid={CallSid}")

        context = conversational_manager.get_conversation_context(call_sid)
        if not context and CallSid:
            context = conversational_manager.get_conversation_context(CallSid)
            if context:
                logger.info(
                    f"   Found context using Twilio CallSid: {CallSid}")
                call_sid = CallSid

        if not context:
            logger.error(
                f"Conversation context not found: call_sid={call_sid}, CallSid={CallSid}")
            error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>Your session has expired. Thank you for calling.</Say>
                <Hangup/>
            </Response>'''
            return Response(content=error_twiml, media_type="application/xml")

        # ======== STEP 3: Append user message to history ========
        if not conversational_manager.append_user_message(call_sid, user_speech or "[silence]"):
            logger.error("Failed to append user message")
            error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>Error processing your response. Please try again.</Say>
            </Response>'''
            return Response(content=error_twiml, media_type="application/xml")

        # ⚠️ END CALL TRIGGERS: Detect if user wants to end call
        end_keywords = ["bye", "goodbye", "thank you",
                        "not interested", "busy", "call later", "later", "thanks"]
        is_end_trigger = any(word in (user_speech or "").lower()
                             for word in end_keywords)

        logger.info(
            f"   Language: {context['language']} | End trigger: {is_end_trigger}")

        # Keep conversations concise (greeting, plan question, offer, close)
        if context["turn_count"] >= 4:
            logger.info("Max conversation turns reached. Ending call.")
            summary = conversational_manager.end_conversation(call_sid)
            if summary:
                logger.info(f"Call summary saved: {summary}")

            lang = context.get("language", "en")
            closing_messages = {
                "en": "Thank you so much! As a special token of appreciation, we offer you a 20% discount on your next stay. We really hope to see you again soon. Goodbye!",
                "hi": "बहुत धन्यवाद! आभार स्वरूप आपकी अगली यात्रा पर 20% की विशेष छूट है। हम आपको फिर से जल्द देखना चाहेंगे। अलविदा!",
            }
            closing_msg = closing_messages.get(lang, closing_messages["en"])

            # Generate TTS for closing message (NEVER use <Say> - that's Alice voice!)
            audio_url = conversational_manager.text_to_speech_url(
                closing_msg, lang)
            if audio_url:
                full_audio_url = f"{config.NGROK_BASE_URL}{audio_url}" if not audio_url.startswith(
                    "http") else audio_url
                audio_url_xml = full_audio_url.replace("&", "&amp;")
                close_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Play>{audio_url_xml}</Play>
                <Hangup/>
            </Response>'''
            else:
                # Fallback: silently hang up if TTS fails
                close_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Hangup/>
            </Response>'''

            return Response(content=close_twiml, media_type="application/xml")

        # Step 2: Generate LLM response (uses full conversation history)
        logger.debug(
            "Generating LLM response with full conversation history...")
        agent_response = conversational_manager.generate_next_response(
            call_sid)

        # Log response status for debugging
        if agent_response:
            logger.info(
                f"✓ LLM Response (len={len(agent_response)}): {agent_response[:80]}...")
        else:
            logger.warning(
                f"⚠️ LLM returned None | lang={context.get('language')} turn={context.get('turn_count')}")

        if not agent_response:
            logger.warning("LLM generation failed, using contextual fallback")
            lang = context.get("language", "en")
            turn = context.get("turn_count", 0)

            # Contextual fallback: Don't force questions, acknowledge and move forward
            fallback_responses = {
                "en": [
                    "Thank you for sharing that. I appreciate your feedback.",
                    "That's helpful to know. Is there anything else about your stay?",
                    "I understand. When might you be able to visit us again?",
                    "Thank you for your time today. We have a special offer for you.",
                ],
                "hi": [
                    "धन्यवाद! आपकी बात सुनकर खुशी हुई।",
                    "समझ गया। और कुछ बताना चाहेंगे?",
                    "ठीक है। आप दोबारा कब आ सकते हैं?",
                    "आपके समय के लिए धन्यवाद! हमारे पास एक विशेष ऑफर है।",
                ]
            }

            responses = fallback_responses.get(lang, fallback_responses["en"])
            agent_response = responses[turn % len(responses)]
            logger.info(
                f"⚠️ Using contextual fallback (turn {turn}, lang={lang}): {agent_response[:60]}")

        # Step 3: Append agent response to history
        if not conversational_manager.append_agent_message(call_sid, agent_response):
            logger.error("Failed to append agent message")
            agent_response = "Thank you for your response."

        # ✅ VALIDATION: Ensure agent_response is never empty (safeguard)
        if not agent_response or not isinstance(agent_response, str) or len(agent_response.strip()) == 0:
            logger.error(
                f"❌ CRITICAL: agent_response is empty or invalid! Type: {type(agent_response)}, Value: '{agent_response}'")
            agent_response = "I'm sorry, could you please repeat that?"
            logger.info(f"Using emergency fallback: {agent_response}")

        # Step 4: Generate TTS audio endpoint URL (on-the-fly, no file storage)
        logger.debug(f"Generating TTS audio URL for: {agent_response[:50]}...")
        audio_url = conversational_manager.text_to_speech_url(
            agent_response, context["language"])

        # Step 5: Generate TwiML to play audio + listen (loop)
        if not audio_url:
            logger.warning(
                "TTS generation failed, cannot continue without audio")
            error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Say>Audio generation failed. Ending call.</Say>
                <Hangup/>
            </Response>'''
            return Response(content=error_twiml, media_type="application/xml")

        full_audio_url = f"{config.NGROK_BASE_URL}{audio_url}" if not audio_url.startswith(
            "http") else audio_url
        audio_url_xml = full_audio_url.replace("&", "&amp;")

        # 🛑 IF END TRIGGER WAS DETECTED → Hangup instead of Gather
        if is_end_trigger:
            logger.info(
                f"🛑 END TRIGGER DETECTED - Hanging up after discount response")
            close_twiml = f'''<?xml version="1.0" encoding="UTF-8"?>
            <Response>
                <Play>{audio_url_xml}</Play>
                <Hangup/>
            </Response>'''
            return Response(content=close_twiml, media_type="application/xml")

        # 🔄 NORMAL FLOW - Continue gathering user input
        next_webhook = f"{config.NGROK_BASE_URL}/api/v1/calls/handle-conversational-response?call_sid={call_sid}&customer_id={customer_id}"
        lang = context.get("language", "en")
        twiml = conversational_manager.get_next_twiml(
            full_audio_url, next_webhook, lang)

        logger.info(f"   Agent: {agent_response[:50]}...")
        logger.info(f"   Turn: {context['turn_count']}/4")

        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Error in handle_conversational_response: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        error_twiml = '''<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say>We encountered a technical difficulty. Thank you for calling Beacon Hotel.</Say>
            <Hangup/>
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
        active_customers = session.query(
            Customer).filter_by(is_active=True).count()

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
        existing = session.query(Customer).filter_by(
            phone=customer_request.phone).first()
        if existing:
            raise HTTPException(
                status_code=400, detail=f"Customer with phone {customer_request.phone} already exists")

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

        logger.info(
            f"Created customer {customer_id} with phone {customer_request.phone}")

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
                existing = session.query(Customer).filter_by(
                    phone=customer_req.phone).first()
                if existing:
                    logger.warning(
                        f"Skipping customer with phone {customer_req.phone} - already exists")
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
        logger.info(
            f"Bulk created {len(created_customers)} customers failed: {failed_count}")

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
    language: str = Query(
        "en", description="Language code (en, hi, ta, te, ml)")
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
            raise HTTPException(
                status_code=500, detail="Audio generation failed")

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


@app.post("/api/v1/stream/livekit/session", response_model=LiveKitStreamingSessionResponse, tags=["Streaming"])
def create_livekit_streaming_session(req: LiveKitStreamingSessionRequest):
    """
    Create a LiveKit streaming bridge session.

    Use returned websocket URL to stream audio chunks from LiveKit.
    """
    try:
        session_id = f"lk_{uuid.uuid4().hex[:12]}"

        base_url = (
            config.NGROK_BASE_URL or "http://localhost:8000").strip().rstrip("/")
        ws_base = base_url.replace(
            "https://", "wss://").replace("http://", "ws://")
        websocket_url = (
            f"{ws_base}/api/v1/stream/livekit/ws/{session_id}"
            f"?language={req.language}&customer_name={req.customer_name or 'Guest'}"
        )

        return LiveKitStreamingSessionResponse(
            status="ready",
            session_id=session_id,
            websocket_url=websocket_url,
            workflow="LiveKit streaming -> Sarvam streaming STT -> LLM -> Sarvam streaming TTS",
            input_format='{"type":"audio_chunk","audio":"<base64_pcm_s16le>","sample_rate":16000,"encoding":"audio/pcm"}',
            output_format='{"type":"tts_audio_chunk","audio":"<base64_audio>","content_type":"audio/mpeg"}',
        )
    except Exception as e:
        logger.error(f"Error creating LiveKit streaming session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/api/v1/stream/livekit/ws/{session_id}")
async def livekit_streaming_bridge_ws(
    websocket: WebSocket,
    session_id: str,
    language: str = Query("unknown"),
    customer_name: str = Query("Guest"),
):
    """
    WebSocket bridge endpoint for LiveKit streaming pipeline.

    Client sends `audio_chunk` messages with base64 PCM audio.
    Server streams back STT/LLM/TTS events and audio chunks.
    """
    await websocket.accept()
    logger.info(
        f"🎧 LiveKit streaming session connected: {session_id}, lang={language}, customer={customer_name}")
    try:
        await livekit_streaming_service.run_bridge_session(
            websocket=websocket,
            customer_name=customer_name,
            language=language,
        )
    except WebSocketDisconnect:
        logger.info(f"LiveKit streaming session disconnected: {session_id}")
    except Exception as e:
        logger.error(
            f"LiveKit streaming websocket error ({session_id}): {str(e)}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@app.websocket("/api/v1/stream/twilio/ws")
async def twilio_media_stream_ws(
    websocket: WebSocket,
    customer_id: Optional[str] = Query(None),
    conv_id: Optional[str] = Query(None),
):
    """
    Twilio Media Streams websocket endpoint.

    Receives real-time call audio (no recording), runs STT -> LLM,
    then updates the call with a spoken response and reconnects stream.
    """
    await websocket.accept()
    logger.info(
        f"🎧 Twilio media stream connected: conv_id={conv_id}, customer_id={customer_id}")

    stream_sid = None
    call_sid = None
    audio_buffer = bytearray()
    response_sent = False
    empty_stt_events = 0
    # cap audio length sent to STT
    max_stt_buffer_bytes = int(config.STT_MAX_AUDIO_SECS * 8000 * 2)
    stream_start_time = None      # set when stream 'start' event arrives
    last_voice_time = None         # set when audio exceeds RMS threshold
    silence_timeout_secs = 20      # reprompt/close after this many seconds of silence

    # Chunked voice-activity detection (VAD) settings
    _CHUNK_SIZE = 3200            # 0.2s at 8kHz 16-bit mono
    # chunk-level RMS above this = speech (Twilio phone audio is quieter)
    _VOICE_RMS_THRESHOLD = 10
    # 1.6s of consecutive silence after voice → end of utterance
    _EOU_SILENCE_CHUNKS = 8
    _MIN_VOICE_CHUNKS = 2         # need ≥0.4s of voice to bother with STT
    # absolute minimum audio to send to STT (~0.5s)
    _MIN_STT_BYTES = 8000
    # send to STT after this many seconds of continuous voice (no EOU needed)
    _MAX_VOICE_SECS = 5.0
    _voice_active = False
    _voice_chunk_count = 0
    _silence_after_voice = 0
    _last_analyzed = 0            # byte offset into audio_buffer for next chunk analysis
    _voice_start_mono = None      # monotonic time when voice onset was detected

    def _get_stt_language() -> str:
        """Return the Sarvam-compatible language code for STT from the conversation context."""
        ctx = conversational_manager.get_conversation_context(
            conv_id) if conv_id else None
        lang = ctx.get("language", "en") if ctx else "en"
        # Sarvam STT expects codes like 'en-IN', 'hi-IN', 'ta-IN', etc.
        lang_map = {"en": "en-IN", "hi": "hi-IN",
                    "ta": "ta-IN", "te": "te-IN", "ml": "ml-IN"}
        return lang_map.get(lang, "en-IN")

    def _is_stt_hallucination(text: str) -> bool:
        """Detect STT hallucination patterns like repeated words/phrases."""
        if not text:
            return False
        words = text.strip().split()
        if len(words) < 4:
            return False
        # If the most common word accounts for >60% of words, it's a hallucination
        from collections import Counter
        counts = Counter(words)
        most_common_word, most_common_count = counts.most_common(1)[0]
        if most_common_count / len(words) > 0.6:
            logger.info(
                f"🚫 STT hallucination detected: '{most_common_word}' repeated {most_common_count}/{len(words)} times")
            return True
        return False

    def _handle_user_text(user_text: str) -> None:
        nonlocal response_sent, empty_stt_events

        text_value = (user_text or "").strip()
        if not text_value:
            return

        empty_stt_events = 0
        logger.info(f"🎙️ Twilio stream STT: {text_value}")

        if not conversational_manager.get_conversation_context(conv_id):
            conversational_manager.init_conversation(
                conv_id, customer_id, "en")

        conversational_manager.append_user_message(conv_id, text_value)

        context = conversational_manager.get_conversation_context(conv_id)
        current_lang = context.get("language", "en") if context else "en"
        current_turn = context.get("turn_count", 0) if context else 0
        customer_name = context.get(
            "customer_name", "Guest") if context else "Guest"

        agent_text = conversational_manager.generate_next_response(conv_id)
        is_closing_turn = False
        if not agent_text:
            user_text_l = text_value.lower()

            if current_turn <= 0:
                # Turn 0: User responded to greeting → ask about visit plans
                agent_text = conversational_manager.get_visit_plans_question(
                    customer_name, current_lang)
            elif current_turn == 1:
                # Turn 1: User responded to "planning to visit again?" → yes/no handling
                yes_markers = ["yes", "yeah", "yep", "sure", "plan", "definitely", "of course",
                               "हां", "हाँ", "जी", "बिल्कुल", "ज़रूर", "ಹೂ", "ಹ್ಞೂ", "aha", "haan"]
                no_markers = ["no", "nope", "not sure", "maybe", "not plan", "don't think",
                              "नहीं", "pata nahi", "ಇಲ್ಲ", "not right now"]
                if any(m in user_text_l for m in yes_markers):
                    agent_text = (
                        f"That's wonderful to hear {customer_name}! As a valued guest, we have an exclusive "
                        f"20% loyalty discount for your next stay. We'd love to welcome you back. "
                        f"See you soon and take care!"
                    ) if current_lang == "en" else (
                        f"बहुत अच्छा {customer_name}! आपके लिए अगली यात्रा पर 20% की विशेष छूट है। "
                        f"जल्दी मिलेंगे, अपना ख्याल रखिए!"
                    )
                elif any(m in user_text_l for m in no_markers):
                    agent_text = (
                        f"No worries at all {customer_name}! Whenever you plan in the future, "
                        f"we have a special 20% discount waiting just for you. "
                        f"Hope to see you soon! Take care."
                    ) if current_lang == "en" else (
                        f"कोई बात नहीं {customer_name}! जब भी आप भविष्य में आना चाहें, "
                        f"आपके लिए 20% की विशेष छूट तैयार है। जल्दी मिलेंगे!"
                    )
                else:
                    # Ambiguous → offer discount and close
                    agent_text = conversational_manager.get_loyalty_offer(
                        customer_name, 20, current_lang)
                is_closing_turn = True
            elif current_turn == 2:
                # Turn 2: Already offered discount, now close
                agent_text = (
                    f"Thank you so much for your time {customer_name}! "
                    f"We truly value you as our guest. Have a wonderful day!"
                ) if current_lang == "en" else (
                    f"आपके समय के लिए बहुत धन्यवाद {customer_name}! "
                    f"आपका दिन शुभ हो!"
                )
                is_closing_turn = True
            else:
                # Turn 3+: Graceful close
                agent_text = (
                    f"Thank you for chatting with us {customer_name}! Take care and see you soon!"
                ) if current_lang == "en" else (
                    f"बात करने के लिए धन्यवाद {customer_name}! अलविदा!"
                )
                is_closing_turn = True

        conversational_manager.append_agent_message(conv_id, agent_text)

        # Check if the LLM response itself signals a closing turn
        if not is_closing_turn:
            closing_signals = ["see you soon", "take care", "goodbye", "bye", "have a wonderful",
                               "have a great", "अलविदा", "जल्दी मिलेंगे", "ख्याल रखिए"]
            if any(sig in agent_text.lower() for sig in closing_signals):
                is_closing_turn = True

        context = conversational_manager.get_conversation_context(conv_id)
        response_lang = context.get("language", "en") if context else "en"
        response_audio_url = conversational_manager.text_to_speech_url(
            agent_text, response_lang)

        if is_closing_turn:
            # Closing turn: play audio and hang up, don't open new stream
            logger.info(
                f"📞 Closing turn detected — will hang up after playing response")
            if response_audio_url:
                full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                    "http") else response_audio_url
                twiml = _build_twilio_hangup_play_twiml(full_audio_url)
            else:
                twiml = _build_twilio_hangup_say_twiml(agent_text)
        else:
            stream_http_url = f"{config.NGROK_BASE_URL}/api/v1/stream/twilio/ws"
            stream_url = _http_to_ws_url(stream_http_url)
            if response_audio_url:
                full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                    "http") else response_audio_url
                twiml = _build_twilio_stream_play_twiml(
                    full_audio_url, stream_url, customer_id, conv_id)
            else:
                twiml = _build_twilio_stream_twiml(
                    agent_text, stream_url, customer_id, conv_id)

        try:
            twilio_service.client.calls(call_sid).update(twiml=twiml)
            logger.info(
                f"✅ Twilio call updated with stream response: call_sid={call_sid}")
            response_sent = True
        except Exception as update_err:
            logger.error(
                f"Failed updating Twilio call with response: {str(update_err)}")
            response_sent = True

    def _flush_buffered_audio(reason: str) -> None:
        nonlocal audio_buffer
        if len(audio_buffer) == 0 or response_sent:
            return

        buffered_rms = audioop.rms(bytes(audio_buffer), 2)
        if buffered_rms < _VOICE_RMS_THRESHOLD:
            logger.info(
                f"Skipping buffered STT on {reason}: low audio energy rms={buffered_rms}, bytes={len(audio_buffer)}"
            )
            audio_buffer.clear()
            return

        logger.info(
            f"Twilio stream buffered audio flush ({reason}): {len(audio_buffer)} bytes "
            f"({len(audio_buffer) / (8000 * 2):.1f}s, rms={buffered_rms})"
        )

        if not (call_sid and conv_id and customer_id):
            audio_buffer.clear()
            return

        try:
            stt_result = conversational_manager.sarvam.speech_to_text(
                audio_data=_pcm16_to_wav_bytes(
                    bytes(audio_buffer), sample_rate=8000),
                language=_get_stt_language(),
            )
            flush_text = (stt_result or {}).get("text", "").strip()
            if flush_text and not _is_stt_hallucination(flush_text):
                logger.info(f"Processing buffered utterance on {reason}")
                _handle_user_text(flush_text)
            else:
                logger.info(
                    f"Buffered utterance produced empty transcript on {reason}")
        except Exception as flush_err:
            logger.error(
                f"Failed buffered STT processing on {reason}: {str(flush_err)}")
        finally:
            audio_buffer.clear()

    try:
        while True:
            raw_text = await websocket.receive_text()
            payload = json.loads(raw_text)
            event_type = payload.get("event")

            if event_type == "start":
                start = payload.get("start", {})
                stream_sid = start.get("streamSid")
                call_sid = start.get("callSid")

                # Twilio custom params from <Stream><Parameter .../></Stream>
                custom_params = start.get("customParameters") or start.get(
                    "custom_parameters") or {}
                if not customer_id:
                    customer_id = custom_params.get("customer_id")
                if not conv_id:
                    conv_id = custom_params.get("conv_id")

                logger.info(
                    f"Twilio stream start: stream_sid={stream_sid}, call_sid={call_sid}")
                logger.info(
                    f"Twilio stream params: customer_id={customer_id}, conv_id={conv_id}")

                import time as _time
                stream_start_time = _time.monotonic()
                last_voice_time = stream_start_time

                if not customer_id or not conv_id:
                    logger.error(
                        "Twilio stream missing customer_id/conv_id; closing websocket")
                    await websocket.close(code=1008)
                    break
                continue

            if event_type == "media":
                if response_sent:
                    continue

                media = payload.get("media", {})
                b64_audio = media.get("payload")
                if not b64_audio:
                    continue

                try:
                    ulaw_bytes = base64.b64decode(b64_audio)
                    # 8k ulaw -> 16-bit PCM
                    pcm16 = audioop.ulaw2lin(ulaw_bytes, 2)
                    audio_buffer.extend(pcm16)
                except Exception:
                    continue

                # --- Silence timeout (checked every media event) ---
                import time as _time
                _now = _time.monotonic()
                if (
                    last_voice_time
                    and not _voice_active
                    and not response_sent
                    and call_sid and conv_id and customer_id
                    and (_now - last_voice_time) > silence_timeout_secs
                ):
                    logger.info(
                        f"⏰ Silence timeout ({silence_timeout_secs}s, "
                        f"elapsed={_now - last_voice_time:.1f}s) — triggering reprompt/close"
                    )
                    audio_buffer.clear()
                    _last_analyzed = 0

                    context = conversational_manager.get_conversation_context(
                        conv_id)
                    current_lang = context.get(
                        "language", "en") if context else "en"
                    current_turn = context.get(
                        "turn_count", 0) if context else 0
                    customer_name = context.get(
                        "customer_name", "Guest") if context else "Guest"

                    if current_turn >= 2:
                        closing = {
                            "en": f"Thank you for your time {customer_name}! We hope to see you again. Have a wonderful day!",
                            "hi": f"\u0906\u092a\u0915\u0947 \u0938\u092e\u092f \u0915\u0947 \u0932\u093f\u090f \u092c\u0939\u0941\u0924 \u0927\u0928\u094d\u092f\u0935\u093e\u0926 {customer_name}! \u0906\u092a\u0915\u093e \u0926\u093f\u0928 \u0936\u0941\u092d \u0939\u094b!",
                        }
                        closing_text = closing.get(current_lang, closing["en"])
                        response_audio_url = conversational_manager.text_to_speech_url(
                            closing_text, current_lang)
                        if response_audio_url:
                            full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                                "http") else response_audio_url
                            twiml = _build_twilio_hangup_play_twiml(
                                full_audio_url)
                        else:
                            twiml = _build_twilio_hangup_say_twiml(
                                closing_text)
                    else:
                        reprompts = {
                            "en": f"Are you still there {customer_name}? Are you planning to visit us again soon?",
                            "hi": f"{customer_name}, \u0915\u094d\u092f\u093e \u0906\u092a \u0935\u0939\u093e\u0901 \u0939\u0948\u0902? \u0915\u094d\u092f\u093e \u0906\u092a \u091c\u0932\u094d\u0926\u0940 \u092b\u093f\u0930 \u0938\u0947 \u0906\u0928\u0947 \u0915\u0940 \u092f\u094b\u091c\u0928\u093e \u092c\u0928\u093e \u0930\u0939\u0947 \u0939\u0948\u0902?",
                        }
                        reprompt_text = reprompts.get(
                            current_lang, reprompts["en"])
                        stream_http_url = f"{config.NGROK_BASE_URL}/api/v1/stream/twilio/ws"
                        stream_url = _http_to_ws_url(stream_http_url)
                        response_audio_url = conversational_manager.text_to_speech_url(
                            reprompt_text, current_lang)
                        if response_audio_url:
                            full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                                "http") else response_audio_url
                            twiml = _build_twilio_stream_play_twiml(
                                full_audio_url, stream_url, customer_id, conv_id)
                        else:
                            twiml = _build_twilio_stream_twiml(
                                reprompt_text, stream_url, customer_id, conv_id)

                    try:
                        twilio_service.client.calls(
                            call_sid).update(twiml=twiml)
                        logger.info(
                            f"\u2705 Twilio call updated after silence timeout (turn={current_turn})")
                        response_sent = True
                    except Exception as timeout_err:
                        logger.error(
                            f"Failed to update call after silence timeout: {str(timeout_err)}")
                        response_sent = True
                    continue

                # --- Chunked voice-activity detection ---
                _trigger_stt = False

                while (len(audio_buffer) - _last_analyzed) >= _CHUNK_SIZE:
                    chunk = bytes(
                        audio_buffer[_last_analyzed:_last_analyzed + _CHUNK_SIZE])
                    chunk_rms = audioop.rms(chunk, 2)
                    _last_analyzed += _CHUNK_SIZE

                    if chunk_rms >= _VOICE_RMS_THRESHOLD:
                        if not _voice_active:
                            logger.info(
                                f"🔊 Voice onset detected: rms={chunk_rms}, buffer={len(audio_buffer)} bytes")
                            _voice_start_mono = _now
                        _voice_active = True
                        _voice_chunk_count += 1
                        _silence_after_voice = 0
                        last_voice_time = _now
                    elif _voice_active:
                        _silence_after_voice += 1

                # End-of-utterance: enough silence after voice
                if _voice_active and _silence_after_voice >= _EOU_SILENCE_CHUNKS:
                    if _voice_chunk_count >= _MIN_VOICE_CHUNKS and len(audio_buffer) >= _MIN_STT_BYTES and call_sid:
                        logger.info(
                            f"🛑 End-of-utterance detected: {_voice_chunk_count} voice chunks, "
                            f"{_silence_after_voice} silence chunks"
                        )
                        _trigger_stt = True
                    else:
                        logger.info(
                            f"Discarding short voice segment: chunks={_voice_chunk_count}, "
                            f"bytes={len(audio_buffer)}"
                        )
                        audio_buffer.clear()
                    _voice_active = False
                    _voice_chunk_count = 0
                    _silence_after_voice = 0
                    _last_analyzed = 0
                    _voice_start_mono = None

                # Voice duration trigger: send to STT after N seconds of continuous voice
                # even without a clear end-of-utterance silence pause
                if (
                    _voice_active
                    and _voice_start_mono
                    and (_now - _voice_start_mono) >= _MAX_VOICE_SECS
                    and len(audio_buffer) >= _MIN_STT_BYTES
                    and call_sid
                ):
                    logger.info(
                        f"⏱️ Voice duration trigger ({_now - _voice_start_mono:.1f}s): "
                        f"{_voice_chunk_count} voice chunks, {len(audio_buffer)} bytes"
                    )
                    _trigger_stt = True
                    _voice_active = False
                    _voice_chunk_count = 0
                    _silence_after_voice = 0
                    _last_analyzed = 0
                    _voice_start_mono = None

                # Long continuous speech — send what we have so the caller isn't waiting
                if _voice_active and len(audio_buffer) >= max_stt_buffer_bytes and call_sid:
                    logger.info(
                        f"📦 Buffer cap trigger: {len(audio_buffer)} bytes"
                    )
                    _trigger_stt = True
                    _voice_active = False
                    _voice_chunk_count = 0
                    _silence_after_voice = 0
                    _last_analyzed = 0
                    _voice_start_mono = None

                # Drop prolonged silence (no voice detected at all)
                if not _voice_active and not _trigger_stt and len(audio_buffer) >= max_stt_buffer_bytes:
                    logger.info(
                        f"Dropping silence-only buffer: bytes={len(audio_buffer)}"
                    )
                    audio_buffer.clear()
                    _last_analyzed = 0
                    continue

                if not _trigger_stt:
                    continue

                # --- Send voiced audio to STT ---
                if not call_sid:
                    audio_buffer.clear()
                    _last_analyzed = 0
                    continue

                # Cap buffer
                if len(audio_buffer) > max_stt_buffer_bytes:
                    audio_buffer = bytearray(
                        bytes(audio_buffer)[-max_stt_buffer_bytes:])

                logger.info(
                    f"🎯 Sending utterance to STT: {len(audio_buffer)} bytes "
                    f"({len(audio_buffer) / (8000 * 2):.1f}s)"
                )

                utterance_key = f"{call_sid}:{len(audio_buffer)}"
                if utterance_key in PROCESSED_STREAM_UTTERANCES:
                    audio_buffer.clear()
                    _last_analyzed = 0
                    continue
                PROCESSED_STREAM_UTTERANCES.add(utterance_key)

                wav_data = _pcm16_to_wav_bytes(
                    bytes(audio_buffer), sample_rate=8000)
                stt_lang = _get_stt_language()
                loop = asyncio.get_running_loop()
                stt_result = await loop.run_in_executor(
                    None,
                    lambda: conversational_manager.sarvam.speech_to_text(
                        audio_data=wav_data, language=stt_lang,
                    ),
                )
                audio_buffer.clear()
                _last_analyzed = 0

                user_text = (stt_result or {}).get("text", "").strip()
                # Treat hallucinated repeated-word output as empty
                if user_text and _is_stt_hallucination(user_text):
                    user_text = ""
                if not user_text:
                    empty_stt_events += 1
                    logger.info(
                        f"Twilio stream STT returned empty transcript (count={empty_stt_events})")

                    # If STT repeatedly returns empty, reprompt or close based on turn.
                    if empty_stt_events >= 2 and call_sid and conv_id and customer_id:
                        context = conversational_manager.get_conversation_context(
                            conv_id)
                        current_lang = context.get(
                            "language", "en") if context else "en"
                        current_turn = context.get(
                            "turn_count", 0) if context else 0
                        customer_name = context.get(
                            "customer_name", "Guest") if context else "Guest"

                        if current_turn >= 2:
                            # Conversation already advanced past offer — close gracefully
                            closing = {
                                "en": f"Thank you for your time {customer_name}! We hope to see you again. Have a wonderful day!",
                                "hi": f"आपके समय के लिए धन्यवाद {customer_name}! जल्दी मिलेंगे, अपना ख्याल रखिए!",
                            }
                            closing_text = closing.get(
                                current_lang, closing["en"])
                            response_audio_url = conversational_manager.text_to_speech_url(
                                closing_text, current_lang)
                            if response_audio_url:
                                full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                                    "http") else response_audio_url
                                twiml = _build_twilio_hangup_play_twiml(
                                    full_audio_url)
                            else:
                                twiml = _build_twilio_hangup_say_twiml(
                                    closing_text)
                        else:
                            reprompts = {
                                "en": f"I couldn't catch that {customer_name}. Are you planning to visit us again soon?",
                                "hi": f"माफ़ कीजिए {customer_name}, आपकी बात साफ़ नहीं सुन पाया। क्या आप जल्द ही फिर से आने की योजना बना रहे हैं?",
                            }
                            reprompt_text = reprompts.get(
                                current_lang, reprompts["en"])
                            stream_http_url = f"{config.NGROK_BASE_URL}/api/v1/stream/twilio/ws"
                            stream_url = _http_to_ws_url(stream_http_url)
                            response_audio_url = conversational_manager.text_to_speech_url(
                                reprompt_text, current_lang)
                            if response_audio_url:
                                full_audio_url = f"{config.NGROK_BASE_URL}{response_audio_url}" if not response_audio_url.startswith(
                                    "http") else response_audio_url
                                twiml = _build_twilio_stream_play_twiml(
                                    full_audio_url, stream_url, customer_id, conv_id)
                            else:
                                twiml = _build_twilio_stream_twiml(
                                    reprompt_text, stream_url, customer_id, conv_id)

                        try:
                            twilio_service.client.calls(
                                call_sid).update(twiml=twiml)
                            logger.info(
                                f"✅ Twilio call updated after empty STT (turn={current_turn}): call_sid={call_sid}")
                            response_sent = True
                        except Exception as update_err:
                            logger.error(
                                f"Failed to update Twilio call after empty STT: {str(update_err)}")
                            response_sent = True  # prevent further attempts

                    continue

                _handle_user_text(user_text)

            if event_type == "stop":
                if len(audio_buffer) > 0 and not response_sent:
                    _flush_buffered_audio("stream stop")

                logger.info(
                    f"Twilio stream stop: stream_sid={stream_sid}, call_sid={call_sid}")
                break

    except WebSocketDisconnect:
        _flush_buffered_audio("websocket disconnect")
        logger.info("Twilio media websocket disconnected")
    except Exception as e:
        logger.error(f"Twilio media stream error: {str(e)}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass


@app.post("/api/v1/calls/test", response_model=TestCallResponse, tags=["TestData"])
def test_call_to_customer(test_call_req: TestCallRequest):
    """
    Make a test conversational call.

    Modes:
    - Twilio call mode (default): Twilio Media Streams live call flow (no recording)
    - Streaming mode: Returns LiveKit streaming websocket bridge details

    Flow:
    1. Initialize conversation with system prompt
    2. Generate personalized greeting with TTS
    3. Twilio makes call and plays greeting
    4. Twilio Gather captures speech → handle-conversational-response webhook
    5. Webhook processes with LLM (full history) → generates response
    6. TTS + Play + Gather loop continues for up to 5 turns
    7. Call ends after 5 turns or customer says goodbye

    Example:
    {
        "customer_id": "CUST1001"
    }
    """
    try:
        # Get customer
        customer = session.query(Customer).filter_by(
            customer_id=test_call_req.customer_id).first()
        if not customer:
            raise HTTPException(
                status_code=404, detail=f"Customer {test_call_req.customer_id} not found")

        logger.info(
            f"🎙️ Initiating test call for {customer.customer_id} ({customer.phone})")

        # Treat stream_call as an explicit signal to use streaming mode even if streaming_mode is omitted

        effective_streaming_mode = test_call_req.streaming_mode or test_call_req.stream_call
        # Use requested language, fallback to 'en' if not provided
        requested_language = test_call_req.language or "en"

        # Streaming mode with live call: place Twilio call and stream audio directly (no recording)
        if effective_streaming_mode and test_call_req.stream_call:
            call_sid = f"CONV_{uuid.uuid4().hex[:12]}"

            context = conversational_manager.init_conversation(
                call_sid, test_call_req.customer_id, requested_language)
            if not context:
                raise HTTPException(
                    status_code=500, detail="Failed to initialize conversation")

            greeting = conversational_manager.get_greeting(
                customer.name, requested_language)
            stream_http_url = f"{config.NGROK_BASE_URL}/api/v1/stream/twilio/ws"
            stream_url = _http_to_ws_url(stream_http_url)

            greeting_audio_url = conversational_manager.text_to_speech_url(
                greeting, requested_language)
            if greeting_audio_url:
                full_audio_url = f"{config.NGROK_BASE_URL}{greeting_audio_url}" if not greeting_audio_url.startswith(
                    "http") else greeting_audio_url
                twiml = _build_twilio_stream_play_twiml(
                    full_audio_url, stream_url, test_call_req.customer_id, call_sid)
            else:
                twiml = _build_twilio_stream_twiml(
                    greeting, stream_url, test_call_req.customer_id, call_sid)

            twilio_sid = None
            try:
                call = twilio_service.client.calls.create(
                    to=customer.phone,
                    from_=twilio_service.phone_number,
                    twiml=twiml,
                )
                twilio_sid = call.sid
                logger.info(
                    f"✅ Stream call placed: conv_id={call_sid}, twilio_sid={twilio_sid}")
            except Exception as call_err:
                logger.error(f"Stream call placement failed: {str(call_err)}")
                raise HTTPException(
                    status_code=500, detail=f"Failed to place stream call: {str(call_err)}")

            return TestCallResponse(
                status="stream_call_initiated",
                call_sid=call_sid,
                customer_name=customer.name,
                phone=customer.phone,
                message=(
                    "📞 STREAMING CALL STARTED (NO RECORDING)\n"
                    "✓ Twilio live media stream connected\n"
                    "✓ Sarvam STT + LLM response loop\n"
                    "✓ Twilio speaks generated response and reconnects stream"
                ),
                churn_risk=0.5,
                recommended_offer="Dynamic based on LLM conversation",
                websocket_url=f"{stream_url}?customer_id={test_call_req.customer_id}&conv_id={call_sid}",
                workflow="Twilio live stream -> Sarvam STT -> LLM -> Twilio spoken response",
                input_format='Twilio Media Streams JSON events (start/media/stop)',
                output_format='Twilio call update with TwiML <Play(Sarvam TTS)> + <Connect><Stream>',
            )

        # Streaming test mode: return websocket session details for LiveKit bridge

        if effective_streaming_mode:
            session_id = f"lk_{uuid.uuid4().hex[:12]}"
            base_url = (
                config.NGROK_BASE_URL or "http://localhost:8000").strip().rstrip("/")
            ws_base = base_url.replace(
                "https://", "wss://").replace("http://", "ws://")
            # Use requested_language for the websocket URL
            websocket_url = (
                f"{ws_base}/api/v1/stream/livekit/ws/{session_id}"
                f"?language={requested_language}&customer_name={customer.name}"
            )

            logger.info(f"✓ Streaming test session ready: {session_id}")
            return TestCallResponse(
                status="streaming_ready",
                call_sid=session_id,
                customer_name=customer.name,
                phone=customer.phone,
                message=(
                    "🎧 LIVEKIT STREAMING TEST READY\n"
                    "✓ Sarvam streaming STT\n"
                    "✓ LLM response generation\n"
                    "✓ Sarvam streaming TTS\n"
                    "Send audio_chunk messages to websocket_url"
                ),
                churn_risk=0.5,
                recommended_offer="Dynamic based on LLM conversation",
                websocket_url=websocket_url,
                workflow="LiveKit streaming -> Sarvam streaming STT -> LLM -> Sarvam streaming TTS",
                input_format='{"type":"audio_chunk","audio":"<base64_pcm_s16le>","sample_rate":16000,"encoding":"audio/pcm"}',
                output_format='{"type":"tts_audio_chunk","audio":"<base64_audio>","content_type":"audio/mpeg"}',
            )

        # Twilio call mode: Generate call SID for conversation tracking
        call_sid = f"CONV_{uuid.uuid4().hex[:12]}"

        # Step 1: Initialize conversation with LLM system prompt
        logger.info("Initializing conversation context with system prompt...")
        context = conversational_manager.init_conversation(
            call_sid, test_call_req.customer_id, requested_language)
        if not context:
            raise HTTPException(
                status_code=500, detail="Failed to initialize conversation")

        # Step 2: Generate greeting
        logger.info("Generating personalized greeting...")
        greeting = conversational_manager.get_greeting(
            customer.name, requested_language)
        logger.info(f"📝 Greeting: {greeting}")

        # Step 3: Generate TTS audio URL (on-the-fly, no file storage)
        audio_url = conversational_manager.text_to_speech_url(
            greeting, requested_language)
        if not audio_url:
            logger.warning(
                "TTS generation failed, cannot make call without audio")
            raise HTTPException(
                status_code=500, detail="TTS service unavailable")

        # Generate initial TwiML with greeting
        full_audio_url = f"{config.NGROK_BASE_URL}{audio_url}" if not audio_url.startswith(
            "http") else audio_url
        webhook_url = f"{config.NGROK_BASE_URL}/api/v1/calls/handle-conversational-response?call_sid={call_sid}&customer_id={test_call_req.customer_id}"
        initial_twiml = conversational_manager.get_next_twiml(
            full_audio_url, webhook_url, requested_language)

        # Step 4: Make the call with initial TwiML
        logger.info(f"Making call via Twilio...")
        try:
            call = twilio_service.client.calls.create(
                to=customer.phone,
                from_=twilio_service.phone_number,
                twiml=initial_twiml
            )
            actual_call_sid = call.sid
            # NOTE: We DO NOT migrate to Twilio's SID because the TwiML URL already contains our call_sid (CONV_xxx)
            # Twilio will call back with our call_sid embedded in the URL, so we keep conversation history under CONV_xxx
            logger.info(
                f"✓ Call created: Generated SID={call_sid}, Twilio SID={actual_call_sid}")
        except Exception as e:
            logger.error(f"Twilio call failed: {str(e)}")
            # Use mock SID for testing
            logger.warning("Using mock call SID for demo")

        return TestCallResponse(
            status="call_initiated",
            call_sid=call_sid,
            customer_name=customer.name,
            phone=customer.phone,
            message=f"🎙️ LLM-DRIVEN CONVERSATIONAL CALL STARTED 🎤\n✓ Dynamic greeting with TTS\n✓ Full conversation history tracking\n✓ LLM generates responses (not scripted)\n✓ Natural multi-turn dialogue\n✓ Sentiment & loyalty analysis\n✓ Max 5 turns per call",
            churn_risk=0.5,
            recommended_offer="Dynamic based on LLM conversation"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making conversational call: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/calls/test-livekit-sip", response_model=LiveKitSIPCallResponse, tags=["Streaming"])
async def test_livekit_sip_call(req: LiveKitSIPCallRequest):
    """
    Place an outbound call via LiveKit SIP trunk.

    Architecture:
      Twilio (PSTN) ← SIP trunk ← LiveKit room ← AI Agent (Sarvam STT → LLM → TTS)

    Prerequisites:
      - LiveKit Cloud/self-hosted with SIP service enabled
      - Outbound SIP trunk configured (Twilio SIP trunk → LiveKit)
      - LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_SIP_TRUNK_ID env vars set
      - Agent worker running: python -m livekit.agents start src.services.livekit_sip_agent

    Example:
      {"customer_id": "CUST1001", "language": "en"}
    """
    if not LIVEKIT_AGENTS_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="livekit-agents SDK not installed. Run: pip install livekit-agents livekit-api livekit",
        )

    if not livekit_sip_service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="LiveKit SIP not configured. Set LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_SIP_TRUNK_ID.",
        )

    customer = session.query(Customer).filter_by(
        customer_id=req.customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=404, detail=f"Customer {req.customer_id} not found")

    logger.info(
        f"Placing LiveKit SIP call to {customer.name} ({customer.phone})")

    try:
        result = await livekit_sip_service.create_outbound_call(
            phone_number=customer.phone,
            customer_name=customer.name,
            customer_id=req.customer_id,
            language=req.language,
            custom_prompt=req.custom_prompt,
            total_visits=customer.total_visits or 0,
            loyalty_score=float(customer.loyalty_score or 0),
            last_stay_date=customer.last_stay_date.strftime(
                '%B %Y') if customer.last_stay_date else None,
            preferred_room_type=customer.preferred_room_type,
        )
    except Exception as e:
        logger.error(f"LiveKit SIP call failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return LiveKitSIPCallResponse(
        status=result.get("status", "call_placed"),
        room_name=result.get("room_name", ""),
        customer_name=customer.name,
        phone=customer.phone,
        message=(
            "LIVEKIT SIP CALL PLACED\n"
            f"Room: {result.get('room_name', '')}\n"
            "Flow: Twilio PSTN <- SIP <- LiveKit room <- AI Agent\n"
            "Agent handles: Sarvam STT -> LLM -> Sarvam TTS -> LiveKit playback"
        ),
        workflow="Twilio (PSTN) <- SIP trunk <- LiveKit WebRTC room <- AI Agent (Sarvam STT -> LLM -> TTS)",
    )


@app.get("/api/v1/customers/test-data/list", tags=["TestData"])
def list_test_customers(limit: int = Query(50, ge=1, le=500)):
    """
    List all customers created via API (test data).

    Shows all customers that are available for testing calls.
    """
    try:
        customers = session.query(Customer).order_by(
            Customer.created_at.desc()).limit(limit).all()

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
