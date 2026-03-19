"""
Unit Tests for Beacon Hotel Relationship Manager
"""
import unittest
from datetime import datetime, timedelta
from src.models.database import init_db, get_session, Customer, CallHistory
from src.agents.relationship_manager_agent import RelationshipManagerAgent
from src.services.servam_service import ServamService
from src.utils.call_logger import CallLogger

class TestCustomerModel(unittest.TestCase):
    """Test Customer model"""
    
    def setUp(self):
        """Setup test database"""
        self.session = get_session()
    
    def test_customer_creation(self):
        """Test creating a customer"""
        customer = Customer(
            customer_id="TEST001",
            name="Test Customer",
            email="test@example.com",
            phone="+11234567890",
            total_visits=5,
            loyalty_score=75.0
        )
        
        self.assertEqual(customer.customer_id, "TEST001")
        self.assertEqual(customer.name, "Test Customer")
        self.assertTrue(customer.is_active)

class TestRelationshipAgent(unittest.TestCase):
    """Test RelationshipManagerAgent"""
    
    def setUp(self):
        """Setup for tests"""
        self.agent = RelationshipManagerAgent()
    
    def test_churn_risk_calculation(self):
        """Test churn risk calculation"""
        # High risk scenario
        risk = self.agent._calculate_churn_risk(
            days_since_stay=400,
            days_since_call=100,
            sentiment_score=0.2,
            conversion_rate=0.1,
            loyalty_score=20
        )
        
        self.assertGreater(risk, 0.6)
    
    def test_engagement_level_determination(self):
        """Test engagement level determination"""
        # High engagement
        level = self.agent._determine_engagement_level(
            sentiment_score=0.9,
            conversion_rate=0.5,
            total_calls=10
        )
        
        self.assertEqual(level, "high")
    
    def test_discount_recommendation(self):
        """Test discount recommendation"""
        # High churn risk
        discount = self.agent._recommend_discount(
            churn_risk=0.8,
            loyalty_score=50,
            conversion_rate=0.2
        )
        
        self.assertEqual(discount, 25)  # special_offer

class TestCallLogger(unittest.TestCase):
    """Test CallLogger"""
    
    def setUp(self):
        """Setup for tests"""
        self.logger = CallLogger()
    
    def test_log_call(self):
        """Test logging a call"""
        success = self.logger.log_call(
            customer_id="TEST001",
            call_sid="SID123",
            transcript="Test transcript",
            duration=300,
            discount_offered="welcome_back",
            discount_percentage=10,
            booking_made=True,
            booking_amount=200.0
        )
        
        self.assertTrue(success)

if __name__ == '__main__':
    unittest.main()
