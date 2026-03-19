"""
Main Flask Application for Beacon Hotel Relationship Manager
"""
import sys
import os

# Add parent directory to path so imports work from any location
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import logging
import json
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from datetime import datetime
from config.config import get_config
from src.models.database import init_db, get_session, Customer, CallHistory, CallSchedule
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from src.services.twilio_service import TwilioService
from src.services.servam_service import ServamService
from src.utils.call_logger import CallLogger
from src.utils.dummy_data_generator import initialize_dummy_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

config = get_config()

# Initialize services
relationship_agent = RelationshipManagerAgent()
twilio_service = TwilioService()
servam_service = ServamService()
call_logger = CallLogger()
session = get_session()

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "hotel": config.HOTEL_NAME,
        "environment": config.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
    }), 200

@app.route('/api/v1/customers', methods=['GET'])
def get_customers():
    """Get all customers"""
    try:
        limit = request.args.get('limit', 50, type=int)
        customers = session.query(Customer).limit(limit).all()
        
        return jsonify({
            "count": len(customers),
            "customers": [
                {
                    "customer_id": c.customer_id,
                    "name": c.name,
                    "email": c.email,
                    "phone": c.phone,
                    "total_visits": c.total_visits,
                    "loyalty_score": c.loyalty_score,
                    "is_active": c.is_active
                }
                for c in customers
            ]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/customers/<customer_id>', methods=['GET'])
def get_customer(customer_id: str):
    """Get customer details"""
    try:
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        
        if not customer:
            return jsonify({"error": "Customer not found"}), 404
        
        return jsonify({
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
        }), 200
    except Exception as e:
        logger.error(f"Error fetching customer: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/customers/<customer_id>/analysis', methods=['GET'])
def analyze_customer(customer_id: str):
    """Analyze customer and get relationship insights"""
    try:
        analysis = relationship_agent.analyze_customer_history(customer_id)
        
        if not analysis:
            return jsonify({"error": "Customer not found"}), 404
        
        return jsonify(analysis), 200
    except Exception as e:
        logger.error(f"Error analyzing customer: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/customers/<customer_id>/call-history', methods=['GET'])
def get_customer_call_history(customer_id: str):
    """Get customer's call history"""
    try:
        limit = request.args.get('limit', 20, type=int)
        calls = session.query(CallHistory).filter_by(
            customer_id=customer_id
        ).order_by(CallHistory.call_date.desc()).limit(limit).all()
        
        return jsonify({
            "customer_id": customer_id,
            "call_count": len(calls),
            "calls": [
                {
                    "call_date": call.call_date.isoformat(),
                    "duration": call.call_duration,
                    "status": call.call_status,
                    "sentiment": call.sentiment,
                    "discount_offered": call.discount_offered,
                    "booking_made": call.booking_made,
                    "booking_amount": float(call.booking_amount) if call.booking_amount else None
                }
                for call in calls
            ]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching call history: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/calls/schedule', methods=['POST'])
def schedule_calls():
    """Schedule calls for all high-priority customers"""
    try:
        scheduled = relationship_agent.schedule_calls()
        
        return jsonify({
            "status": "success",
            "scheduled_count": len(scheduled),
            "calls": scheduled
        }), 200
    except Exception as e:
        logger.error(f"Error scheduling calls: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/calls/make', methods=['POST'])
def make_call():
    """Make a call to a customer"""
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')
        
        if not customer_id:
            return jsonify({"error": "Customer ID required"}), 400
        
        # Get customer
        customer = session.query(Customer).filter_by(customer_id=customer_id).first()
        if not customer:
            return jsonify({"error": "Customer not found"}), 404
        
        # Analyze customer
        analysis = relationship_agent.analyze_customer_history(customer_id)
        if not analysis:
            return jsonify({"error": "Cannot analyze customer"}), 500
        
        # Generate call script
        call_script = relationship_agent.generate_call_script(customer_id, analysis)
        
        # Make call via Twilio
        call_sid = twilio_service.make_call(customer.phone, call_script)
        
        if not call_sid:
            return jsonify({"error": "Failed to initiate call"}), 500
        
        return jsonify({
            "status": "call_initiated",
            "call_sid": call_sid,
            "customer_name": customer.name,
            "phone": customer.phone,
            "churn_risk": analysis['churn_risk_score'],
            "recommended_offer": f"{analysis['recommended_discount']}% discount"
        }), 200
    except Exception as e:
        logger.error(f"Error making call: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/calls/log', methods=['POST'])
def log_call():
    """Log a completed call"""
    try:
        data = request.get_json()
        
        customer_id = data.get('customer_id')
        transcript = data.get('transcript', '')
        duration = data.get('duration', 0)
        booking_made = data.get('booking_made', False)
        booking_amount = data.get('booking_amount')
        discount_offered = data.get('discount_offered')
        discount_percentage = data.get('discount_percentage')
        
        success = call_logger.log_call(
            customer_id=customer_id,
            call_sid=data.get('call_sid', ''),
            transcript=transcript,
            duration=duration,
            discount_offered=discount_offered,
            discount_percentage=discount_percentage,
            booking_made=booking_made,
            booking_amount=booking_amount
        )
        
        if not success:
            return jsonify({"error": "Failed to log call"}), 500
        
        return jsonify({"status": "call_logged"}), 200
    except Exception as e:
        logger.error(f"Error logging call: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/reports/export', methods=['GET'])
def export_reports():
    """Export call reports"""
    try:
        report_type = request.args.get('type', 'json')
        days = request.args.get('days', 30, type=int)
        
        if report_type == 'json':
            filename = f"logs/call_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            call_logger.export_call_logs(filename, days)
            return send_file(filename, as_attachment=True)
        else:
            return jsonify({"error": "Unsupported report type"}), 400
    except Exception as e:
        logger.error(f"Error exporting reports: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/init/dummy-data', methods=['POST'])
def init_dummy_data():
    """Initialize dummy data (for development only)"""
    try:
        if config.ENVIRONMENT == "production":
            return jsonify({"error": "Not allowed in production"}), 403
        
        initialize_dummy_data()
        
        return jsonify({"status": "Dummy data initialized successfully"}), 200
    except Exception as e:
        logger.error(f"Error initializing dummy data: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/metrics/summary', methods=['GET'])
def get_metrics_summary():
    """Get system metrics summary"""
    try:
        total_customers = session.query(Customer).count()
        active_customers = session.query(Customer).filter_by(is_active=True).count()
        total_calls = session.query(CallHistory).count()
        
        # Calculate conversion rate
        bookings = session.query(CallHistory).filter_by(booking_made=True).count()
        conversion_rate = (bookings / total_calls * 100) if total_calls > 0 else 0
        
        # Calculate average sentiment
        calls_with_sentiment = session.query(CallHistory).filter(
            CallHistory.sentiment != None
        ).all()
        
        sentiment_score = 0
        if calls_with_sentiment:
            sentiment_map = {"positive": 1, "neutral": 0.5, "negative": 0}
            sentiment_score = sum(
                sentiment_map.get(c.sentiment, 0.5) for c in calls_with_sentiment
            ) / len(calls_with_sentiment)
        
        return jsonify({
            "total_customers": total_customers,
            "active_customers": active_customers,
            "total_calls": total_calls,
            "booking_conversion_rate": round(conversion_rate, 2),
            "average_sentiment_score": round(sentiment_score, 2),
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Error fetching metrics: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Initialize database
    init_db()
    logger.info(f"Starting {config.HOTEL_NAME} Relationship Manager")
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=config.DEBUG
    )
