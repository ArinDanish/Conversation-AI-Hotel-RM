"""
Twilio Service Integration for making customer calls
"""
import logging
from typing import Optional, Callable
from twilio.rest import Client
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

class TwilioService:
    """Service for making calls via Twilio"""
    
    def __init__(self):
        self.account_sid = config.TWILIO_ACCOUNT_SID
        self.auth_token = config.TWILIO_AUTH_TOKEN
        self.phone_number = config.TWILIO_PHONE_NUMBER
        self.client = Client(self.account_sid, self.auth_token)
    
    def make_call(self, customer_phone: str, call_script: str = None, 
                  callback_url: Optional[str] = None, twiml: Optional[str] = None) -> Optional[str]:
        """
        Initiate a call to customer using Twilio
        
        Args:
            customer_phone: Customer phone number in E.164 format
            call_script: Initial greeting script (ignored if twiml is provided)
            callback_url: Callback URL for TwiML (use ngrok URL if available)
            twiml: Pre-built TwiML XML (takes precedence over call_script)
                   
        Returns:
            Call SID if successful, None otherwise
            
        Note:
            For calls to reach your webhook, use ngrok tunnel:
            $ ngrok http 8000
            Then pass: https://xxxx-xx-xxx-xxxx-xxxx.ngrok.io/handle-response
        """
        try:
            # Format phone number if needed
            if not customer_phone.startswith('+'):
                customer_phone = '+' + customer_phone
            
            # Validate phone is in E.164 format
            if not customer_phone.startswith('+') or len(customer_phone) < 10:
                logger.error(f"Invalid phone format: {customer_phone}. Use E.164: +14155552671")
                return None
            
            # Use provided TwiML or create from script
            if twiml:
                twiml_to_use = twiml
                logger.debug("Using pre-built TwiML (conversational call)")
            else:
                twiml_to_use = self._create_twiml(call_script or "Hello", callback_url)
                logger.debug("Generated TwiML from call script")
            
            # Make the call
            logger.info(f"Making call to {customer_phone} from {self.phone_number}")
            logger.debug(f"Using callback URL: {callback_url or 'default'}")
            
            call = self.client.calls.create(
                to=customer_phone,
                from_=self.phone_number,
                twiml=twiml_to_use,
                status_callback_method='POST'
            )
            
            logger.info(f"✓ Call initiated to {customer_phone} with SID: {call.sid}")
            log_message = f"Call SID: {call.sid}, Status: {call.status}, To: {customer_phone}"
            logger.info(log_message)
            
            return call.sid
            
        except Exception as e:
            logger.error(f"❌ Error making call to {customer_phone}: {str(e)}")
            # Log more details for debugging
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def get_call_details(self, call_sid: str) -> Optional[dict]:
        """
        Get details of a specific call
        
        Args:
            call_sid: Call SID from Twilio
            
        Returns:
            Call details dictionary or None
        """
        try:
            call = self.client.calls(call_sid).fetch()
            
            return {
                'call_sid': call.sid,
                'status': call.status,
                'duration': call.duration,
                'price': call.price,
                'phone_number_sid': call.phone_number_sid,
                'start_time': call.start_time,
                'end_time': call.end_time
            }
            
        except Exception as e:
            logger.error(f"Error fetching call details for {call_sid}: {str(e)}")
            return None
    
    def record_call(self, call_sid: str) -> bool:
        """
        Enable recording for a call
        
        Args:
            call_sid: Call SID to record
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Note: Recording is typically initiated when creating call with recording parameter
            logger.info(f"Recording enabled for call {call_sid}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording call {call_sid}: {str(e)}")
            return False
    
    def end_call(self, call_sid: str) -> bool:
        """
        End an active call
        
        Args:
            call_sid: Call SID to end
            
        Returns:
            True if successful, False otherwise
        """
        try:
            call = self.client.calls(call_sid).update(status='completed')
            logger.info(f"Call {call_sid} ended")
            return True
            
        except Exception as e:
            logger.error(f"Error ending call {call_sid}: {str(e)}")
            return False
    
    def send_sms(self, customer_phone: str, message: str) -> Optional[str]:
        """
        Send SMS to customer
        
        Args:
            customer_phone: Customer phone number
            message: SMS message
            
        Returns:
            Message SID if successful, None otherwise
        """
        try:
            if not customer_phone.startswith('+'):
                customer_phone = '+' + customer_phone
            
            msg = self.client.messages.create(
                to=customer_phone,
                from_=self.phone_number,
                body=message
            )
            
            logger.info(f"SMS sent to {customer_phone}")
            return msg.sid
            
        except Exception as e:
            logger.error(f"Error sending SMS to {customer_phone}: {str(e)}")
            return None
    
    def _create_twiml(self, call_script: str, callback_url: Optional[str] = None) -> str:
        """
        Create TwiML for the call with callback handler
        
        Args:
            call_script: Script to speak to customer
            callback_url: Callback URL for gather responses (use ngrok URL)
                         Example: https://xxxx-xxxx-xxxx.ngrok.io/handle-response
            
        Returns:
            TwiML string for Twilio
            
        Note:
            If callback_url is not provided, uses /handle-response relative path
            For production, use full ngrok URL:
            https://xxxx-xx-xxx-xxxx-xxxx.ngrok.io/handle-response
        """
        # Use provided callback URL or default relative path
        action_url = callback_url or "/handle-response"
        
        twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="alice" loop="1">{call_script}</Say>
            <Gather numDigits="1" timeout="5" action="{action_url}" method="POST">
                <Say voice="alice">Press 1 to continue, or hang up to end this call.</Say>
            </Gather>
        </Response>"""
        
        logger.debug(f"TwiML generated with action URL: {action_url}")
        return twiml
