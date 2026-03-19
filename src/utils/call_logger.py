"""
Call logging and management utilities
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict
from src.models.database import get_session, CallHistory
from src.services.servam_service import ServamService

logger = logging.getLogger(__name__)

class CallLogger:
    """Handles call logging and transcript storage"""
    
    def __init__(self):
        self.session = get_session()
        self.servam = ServamService()
    
    def log_call(self, customer_id: str, call_sid: str, 
                 transcript: str, duration: int,
                 discount_offered: Optional[str] = None,
                 discount_percentage: Optional[float] = None,
                 booking_made: bool = False,
                 booking_amount: Optional[float] = None) -> bool:
        """
        Log a completed call to the database
        
        Args:
            customer_id: Customer ID
            call_sid: Twilio call SID
            transcript: Call transcript
            duration: Call duration in seconds
            discount_offered: Discount type offered
            discount_percentage: Discount percentage
            booking_made: Whether booking was made
            booking_amount: Booking amount if made
            
        Returns:
            True if successful
        """
        try:
            # Analyze sentiment of transcript
            sentiment_analysis = self.servam.analyze_sentiment(transcript)
            
            call_log = CallHistory(
                customer_id=customer_id,
                call_date=datetime.utcnow(),
                call_duration=duration,
                call_status="completed",
                conversation_transcript=transcript,
                sentiment=sentiment_analysis.get('sentiment') if sentiment_analysis else 'neutral',
                discount_offered=discount_offered,
                discount_percentage=discount_percentage,
                booking_made=booking_made,
                booking_amount=booking_amount
            )
            
            self.session.add(call_log)
            self.session.commit()
            
            logger.info(f"Call logged for customer {customer_id}, duration: {duration}s")
            return True
            
        except Exception as e:
            logger.error(f"Error logging call: {str(e)}")
            return False
    
    def log_failed_call(self, customer_id: str, reason: str) -> bool:
        """
        Log a failed call attempt
        
        Args:
            customer_id: Customer ID
            reason: Reason for failure
            
        Returns:
            True if successful
        """
        try:
            call_log = CallHistory(
                customer_id=customer_id,
                call_date=datetime.utcnow(),
                call_duration=0,
                call_status="failed",
                agent_notes=f"Call failed: {reason}"
            )
            
            self.session.add(call_log)
            self.session.commit()
            
            logger.warning(f"Failed call logged for {customer_id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error logging failed call: {str(e)}")
            return False
    
    def get_call_history(self, customer_id: str, limit: int = 20) -> list:
        """
        Get call history for a customer
        
        Args:
            customer_id: Customer ID
            limit: Number of records to return
            
        Returns:
            List of call records
        """
        try:
            calls = self.session.query(CallHistory).filter_by(
                customer_id=customer_id
            ).order_by(CallHistory.call_date.desc()).limit(limit).all()
            
            return [
                {
                    'call_date': call.call_date.isoformat(),
                    'duration': call.call_duration,
                    'status': call.call_status,
                    'sentiment': call.sentiment,
                    'booking_made': call.booking_made,
                    'discount_offered': call.discount_offered
                }
                for call in calls
            ]
            
        except Exception as e:
            logger.error(f"Error retrieving call history: {str(e)}")
            return []
    
    def export_call_logs(self, filename: str, days: int = 30) -> bool:
        """
        Export call logs to JSON file
        
        Args:
            filename: Output filename
            days: Number of days to export
            
        Returns:
            True if successful
        """
        try:
            from datetime import timedelta
            
            start_date = datetime.utcnow() - timedelta(days=days)
            
            calls = self.session.query(CallHistory).filter(
                CallHistory.call_date >= start_date
            ).all()
            
            call_data = [
                {
                    'customer_id': call.customer_id,
                    'call_date': call.call_date.isoformat(),
                    'duration': call.call_duration,
                    'status': call.call_status,
                    'sentiment': call.sentiment,
                    'booking_made': call.booking_made,
                    'booking_amount': float(call.booking_amount) if call.booking_amount else None,
                    'discount_offered': call.discount_offered,
                    'discount_percentage': float(call.discount_percentage) if call.discount_percentage else None
                }
                for call in calls
            ]
            
            with open(filename, 'w') as f:
                json.dump(call_data, f, indent=2)
            
            logger.info(f"Call logs exported to {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting call logs: {str(e)}")
            return False
