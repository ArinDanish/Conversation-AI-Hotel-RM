"""
Database models for Beacon Hotel Relationship Manager
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config.config import get_config

Base = declarative_base()
config = get_config()

class Customer(Base):
    """Customer model"""
    __tablename__ = "customers"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    last_stay_date = Column(DateTime, nullable=True)
    total_visits = Column(Integer, default=0)
    total_spent = Column(Float, default=0.0)
    loyalty_score = Column(Float, default=0.0)
    preferred_room_type = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class CallHistory(Base):
    """Call history model"""
    __tablename__ = "call_history"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(String(50), nullable=False)
    call_date = Column(DateTime, nullable=False)
    call_duration = Column(Integer, default=0)  # in seconds
    call_status = Column(String(20), default="completed")  # completed, missed, failed
    agent_notes = Column(Text, nullable=True)
    conversation_transcript = Column(Text, nullable=True)
    tone_score = Column(Float, nullable=True)  # 0-1 scale
    sentiment = Column(String(20), nullable=True)  # positive, neutral, negative
    discount_offered = Column(String(50), nullable=True)
    discount_percentage = Column(Float, nullable=True)
    booking_made = Column(Boolean, default=False)
    booking_amount = Column(Float, nullable=True)
    follow_up_required = Column(Boolean, default=False)
    follow_up_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class RelationshipAnalysis(Base):
    """Relationship analysis and recommendations"""
    __tablename__ = "relationship_analysis"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(String(50), nullable=False)
    last_analyzed = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    churn_risk_score = Column(Float, default=0.0)  # 0-1 scale
    engagement_level = Column(String(20), default="medium")  # low, medium, high
    recommended_discount = Column(String(50), nullable=True)
    next_call_recommendation = Column(DateTime, nullable=True)
    strategy = Column(Text, nullable=True)
    analysis_notes = Column(Text, nullable=True)

class CallSchedule(Base):
    """Call schedule for AI agent"""
    __tablename__ = "call_schedule"
    
    id = Column(Integer, primary_key=True)
    customer_id = Column(String(50), nullable=False)
    scheduled_call_time = Column(DateTime, nullable=False)
    priority = Column(Integer, default=5)  # 1-10 scale
    reason = Column(String(255), nullable=True)
    call_script = Column(Text, nullable=True)
    recommended_offer = Column(String(255), nullable=True)
    status = Column(String(20), default="pending")  # pending, completed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def init_db():
    """Initialize database"""
    engine = create_engine(config.DATABASE_URL)
    Base.metadata.create_all(engine)
    return engine

def get_session():
    """Get database session"""
    engine = create_engine(config.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    return Session()
