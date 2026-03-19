"""
Relationship Manager AI Agent using Dify/Workflow
Analyzes call history and determines optimal calling strategy
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from src.models.database import (
    get_session, Customer, CallHistory, 
    RelationshipAnalysis, CallSchedule
)
from src.services.servam_service import ServamService
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

class RelationshipManagerAgent:
    """AI Agent for managing customer relationships"""
    
    def __init__(self):
        self.servam = ServamService()
        self.session = get_session()
    
    def analyze_customer_history(self, customer_id: str) -> Optional[Dict]:
        """
        Analyze customer's call history and engagement
        
        Args:
            customer_id: Customer ID
            
        Returns:
            Analysis results dictionary
        """
        try:
            customer = self.session.query(Customer).filter_by(
                customer_id=customer_id
            ).first()
            
            if not customer:
                logger.warning(f"Customer {customer_id} not found")
                return None
            
            # Get call history
            call_history = self.session.query(CallHistory).filter_by(
                customer_id=customer_id
            ).order_by(CallHistory.call_date.desc()).limit(20).all()
            
            # Calculate engagement metrics
            total_calls = len(call_history)
            completed_calls = len([c for c in call_history if c.call_status == "completed"])
            
            if total_calls == 0:
                avg_sentiment_score = 0
                booking_conversion_rate = 0
            else:
                sentiments = [c.sentiment for c in call_history if c.sentiment]
                sentiment_map = {"positive": 1, "neutral": 0.5, "negative": 0}
                avg_sentiment_score = sum(
                    sentiment_map.get(s, 0.5) for s in sentiments
                ) / len(sentiments) if sentiments else 0.5
                
                bookings = len([c for c in call_history if c.booking_made])
                booking_conversion_rate = bookings / completed_calls if completed_calls > 0 else 0
            
            # Determine churn risk
            last_call = call_history[0] if call_history else None
            last_stay = customer.last_stay_date
            
            days_since_stay = (datetime.utcnow() - last_stay).days if last_stay else 365
            days_since_call = (
                (datetime.utcnow() - last_call.call_date).days 
                if last_call else 365
            )
            
            # Churn risk scoring
            churn_risk = self._calculate_churn_risk(
                days_since_stay,
                days_since_call,
                avg_sentiment_score,
                booking_conversion_rate,
                customer.loyalty_score
            )
            
            # Determine engagement level
            engagement_level = self._determine_engagement_level(
                avg_sentiment_score,
                booking_conversion_rate,
                total_calls
            )
            
            # Recommend discount
            recommended_discount = self._recommend_discount(
                churn_risk,
                customer.loyalty_score,
                booking_conversion_rate
            )
            
            analysis_result = {
                "customer_id": customer_id,
                "customer_name": customer.name,
                "total_visits": customer.total_visits,
                "total_spent": customer.total_spent,
                "loyalty_score": customer.loyalty_score,
                "total_calls": total_calls,
                "completed_calls": completed_calls,
                "avg_sentiment_score": avg_sentiment_score,
                "booking_conversion_rate": booking_conversion_rate,
                "days_since_last_stay": days_since_stay,
                "days_since_last_call": days_since_call,
                "churn_risk_score": churn_risk,
                "engagement_level": engagement_level,
                "recommended_discount": recommended_discount,
                "call_history_summary": self._summarize_call_history(call_history)
            }
            
            # Save analysis
            analysis = self.session.query(RelationshipAnalysis).filter_by(
                customer_id=customer_id
            ).first()
            
            if not analysis:
                analysis = RelationshipAnalysis(customer_id=customer_id)
            
            analysis.churn_risk_score = churn_risk
            analysis.engagement_level = engagement_level
            analysis.recommended_discount = recommended_discount
            analysis.last_analyzed = datetime.utcnow()
            
            self.session.add(analysis)
            self.session.commit()
            
            logger.info(f"Analysis completed for customer {customer_id}")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analyzing customer {customer_id}: {str(e)}")
            return None
    
    def generate_call_script(self, customer_id: str, analysis: Dict) -> str:
        """
        Generate personalized call script using LLM
        
        Args:
            customer_id: Customer ID
            analysis: Customer analysis dictionary
            
        Returns:
            Generated call script
        """
        try:
            prompt = f"""
            Generate a professional and warm calling script for a hotel relationship manager 
            calling a customer for {config.HOTEL_NAME}.
            
            Customer Name: {analysis['customer_name']}
            Total Visits: {analysis['total_visits']}
            Last Stay: {analysis['days_since_last_stay']} days ago
            Engagement Level: {analysis['engagement_level']}
            Churn Risk: {'High' if analysis['churn_risk_score'] > 0.7 else 'Medium' if analysis['churn_risk_score'] > 0.4 else 'Low'}
            Recommended Offer: {analysis['recommended_discount']}% discount
            
            The script should:
            1. Be warm and personal
            2. Reference their history with us
            3. Offer a targeted discount if appropriate
            4. Invite them to book a stay
            5. Keep it under 2 minutes of speaking time
            
            Generate the script now:
            """
            
            response = self.servam.generate_response(prompt)
            
            if response:
                logger.info(f"Call script generated for {customer_id}")
                return response
            else:
                # Fallback script
                return self._get_fallback_script(analysis)
            
        except Exception as e:
            logger.error(f"Error generating call script: {str(e)}")
            return self._get_fallback_script(analysis)
    
    def schedule_calls(self) -> List[Dict]:
        """
        Analyze all customers and schedule optimal calls
        
        Returns:
            List of scheduled calls
        """
        try:
            scheduled_calls = []
            
            # Get all active customers
            customers = self.session.query(Customer).filter_by(
                is_active=True
            ).all()
            
            for customer in customers:
                # Analyze customer
                analysis = self.analyze_customer_history(customer.customer_id)
                
                if not analysis:
                    continue
                
                # Check if should call
                if self._should_call(customer.customer_id, analysis):
                    # Generate call script
                    call_script = self.generate_call_script(
                        customer.customer_id,
                        analysis
                    )
                    
                    # Schedule call
                    scheduled_time = self._determine_call_time(
                        customer.customer_id,
                        analysis
                    )
                    
                    call_schedule = CallSchedule(
                        customer_id=customer.customer_id,
                        scheduled_call_time=scheduled_time,
                        priority=self._calculate_priority(analysis),
                        reason=f"Churn Risk: {analysis['churn_risk_score']:.2f}, "
                               f"Engagement: {analysis['engagement_level']}",
                        call_script=call_script,
                        recommended_offer=f"{analysis['recommended_discount']}% discount",
                        status="pending"
                    )
                    
                    self.session.add(call_schedule)
                    scheduled_calls.append({
                        'customer_id': customer.customer_id,
                        'customer_name': customer.name,
                        'scheduled_time': scheduled_time,
                        'priority': self._calculate_priority(analysis),
                        'reason': f"Risk Score: {analysis['churn_risk_score']:.2f}"
                    })
            
            self.session.commit()
            logger.info(f"Scheduled {len(scheduled_calls)} calls")
            return scheduled_calls
            
        except Exception as e:
            logger.error(f"Error scheduling calls: {str(e)}")
            return []
    
    # Helper methods
    
    def _calculate_churn_risk(self, days_since_stay: int, days_since_call: int,
                             sentiment_score: float, conversion_rate: float,
                             loyalty_score: float) -> float:
        """Calculate churn risk score (0-1)"""
        risk = 0.0
        
        # Factor: time since last stay
        if days_since_stay > 365:
            risk += 0.4
        elif days_since_stay > 180:
            risk += 0.2
        
        # Factor: time since last call
        if days_since_call > 90:
            risk += 0.2
        elif days_since_call > 30:
            risk += 0.1
        
        # Factor: sentiment (negative sentiment = higher risk)
        risk += (1 - sentiment_score) * 0.2
        
        # Factor: booking conversion
        if conversion_rate < 0.2:
            risk += 0.1
        
        # Factor: loyalty score (lower = higher risk)
        risk += (1 - min(loyalty_score / 100, 1)) * 0.1
        
        return min(risk, 1.0)
    
    def _determine_engagement_level(self, sentiment_score: float,
                                   conversion_rate: float,
                                   total_calls: int) -> str:
        """Determine engagement level"""
        if total_calls == 0:
            return "new"
        elif sentiment_score > 0.7 and conversion_rate > 0.3:
            return "high"
        elif sentiment_score > 0.5 or conversion_rate > 0.15:
            return "medium"
        else:
            return "low"
    
    def _recommend_discount(self, churn_risk: float,
                           loyalty_score: float,
                           conversion_rate: float) -> int:
        """Recommend discount percentage"""
        if churn_risk > 0.7:
            return config.AVAILABLE_DISCOUNTS["special_offer"]
        elif conversion_rate < 0.2 and loyalty_score > 50:
            return config.AVAILABLE_DISCOUNTS["loyalty"]
        elif churn_risk > 0.5:
            return config.AVAILABLE_DISCOUNTS["seasonal"]
        else:
            return config.AVAILABLE_DISCOUNTS["welcome_back"]
    
    def _summarize_call_history(self, call_history: List[CallHistory]) -> str:
        """Summarize call history"""
        if not call_history:
            return "No previous calls"
        
        recent_calls = call_history[:5]
        summary = f"Recent calls: {len(recent_calls)}\n"
        
        for call in recent_calls:
            summary += f"- {call.call_date.strftime('%Y-%m-%d')}: "
            summary += f"{call.call_status.upper()}, Sentiment: {call.sentiment}\n"
        
        return summary
    
    def _should_call(self, customer_id: str, analysis: Dict) -> bool:
        """Determine if should call this customer"""
        # Don't call if called recently
        last_call = self.session.query(CallHistory).filter_by(
            customer_id=customer_id
        ).order_by(CallHistory.call_date.desc()).first()
        
        if last_call:
            days_since_call = (datetime.utcnow() - last_call.call_date).days
            if days_since_call < config.MIN_DAYS_BETWEEN_CALLS:
                return False
        
        # Call if high churn risk or no calls yet
        return analysis['churn_risk_score'] > 0.3 or analysis['total_calls'] == 0
    
    def _determine_call_time(self, customer_id: str, analysis: Dict) -> datetime:
        """Determine optimal call time"""
        # Simple scheduling - next available time during business hours
        now = datetime.utcnow()
        call_time = now + timedelta(hours=24)
        
        # Adjust to business hours
        start_hour = int(config.CALL_TIME_START.split(':')[0])
        end_hour = int(config.CALL_TIME_END.split(':')[0])
        
        if call_time.hour < start_hour:
            call_time = call_time.replace(hour=start_hour, minute=0, second=0)
        elif call_time.hour >= end_hour:
            call_time = call_time + timedelta(days=1)
            call_time = call_time.replace(hour=start_hour, minute=0, second=0)
        
        return call_time
    
    def _calculate_priority(self, analysis: Dict) -> int:
        """Calculate call priority (1-10)"""
        priority = 5
        
        if analysis['churn_risk_score'] > 0.7:
            priority = 10
        elif analysis['churn_risk_score'] > 0.5:
            priority = 8
        elif analysis['engagement_level'] == 'high':
            priority = 7
        elif analysis['engagement_level'] == 'low':
            priority = 3
        
        return priority
    
    def _get_fallback_script(self, analysis: Dict) -> str:
        """Fallback script if LLM generation fails"""
        discount = analysis['recommended_discount']
        name = analysis['customer_name'].split()[0]
        visits = analysis['total_visits']
        
        return f"""
        Hi {name}, this is Sarah calling from {config.HOTEL_NAME}. 
        We really value your business and the {visits} wonderful visits you've had with us. 
        We'd love to welcome you back! In fact, we're offering our valued guests like you 
        an exclusive {discount}% discount on your next stay. 
        Would you be interested in booking a room with us soon?
        """
