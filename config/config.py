"""
Configuration management for Beacon Hotel Relationship Manager
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    HOTEL_NAME = "Beacon Hotel"
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    DEBUG = os.getenv("DEBUG", "False") == "True"
    
    # Servam Configuration
    SERVAM_API_KEY = os.getenv("SERVAM_API_KEY", "your-api-key")
    SERVAM_API_URL = os.getenv("SERVAM_API_URL", "https://api.servam.com")
    SERVAM_STT_MODEL = os.getenv("SERVAM_STT_MODEL", "default-stt")
    SERVAM_TTS_MODEL = os.getenv("SERVAM_TTS_MODEL", "default-tts")
    SERVAM_LLM_MODEL = os.getenv("SERVAM_LLM_MODEL", "default-llm")
    
    # Twilio Configuration
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "your-account-sid")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "your-auth-token")
    TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+1234567890")
    
    # ngrok Public URL for Twilio Callbacks (REQUIRED for webhook callbacks)
    # Example: https://abc123def456.ngrok.io (no trailing slash)
    NGROK_BASE_URL = os.getenv("NGROK_BASE_URL", "http://localhost:8000")
    
    # Database Configuration
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "sqlite:///beacon_hotel.db"
    )
    
    # Agent Configuration
    DIFY_API_KEY = os.getenv("DIFY_API_KEY", "your-dify-key")
    DIFY_API_URL = os.getenv("DIFY_API_URL", "https://api.dify.ai")
    WORKFLOW_ID = os.getenv("WORKFLOW_ID", "relationship-manager-workflow")
    
    # Call Management
    MAX_CALLS_PER_DAY = int(os.getenv("MAX_CALLS_PER_DAY", "20"))
    MIN_DAYS_BETWEEN_CALLS = int(os.getenv("MIN_DAYS_BETWEEN_CALLS", "7"))
    CALL_TIME_START = os.getenv("CALL_TIME_START", "09:00")
    CALL_TIME_END = os.getenv("CALL_TIME_END", "21:00")
    
    # Discount Configuration
    AVAILABLE_DISCOUNTS = {
        "welcome_back": 10,  # 10% discount
        "loyalty": 15,       # 15% discount
        "seasonal": 20,      # 20% discount
        "special_offer": 25  # 25% discount
    }
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")

class DevelopmentConfig(Config):
    """Development configuration"""
    ENVIRONMENT = "development"
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    ENVIRONMENT = "production"
    DEBUG = False

def get_config():
    """Get configuration based on environment"""
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        return ProductionConfig()
    return DevelopmentConfig()
