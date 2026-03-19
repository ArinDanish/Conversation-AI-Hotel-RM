# Beacon Hotel Relationship Manager - README

## 📋 Project Overview

**Beacon Hotel Relationship Manager** is an intelligent AI-powered customer relationship management system designed to retain customers through strategic, personalized outreach. The system analyzes customer call history, predicts churn risk, and orchestrates automated calls with Twilio to offer tailored discounts and booking incentives.

### 🎯 Key Features

- **AI-Powered Analysis**: Analyzes call history and customer engagement using advanced NLP
- **Churn Risk Prediction**: Predictive scoring to identify at-risk customers
- **Intelligent Call Scheduling**: Automatically schedules optimal times to call customers based on historical engagement patterns
- **Personalized Call Scripts**: Generates custom scripts using Servam LLM based on customer history
- **Speech Processing**: STT and TTS integration for natural conversations
- **Twilio Integration**: Make real calls to customers with recorded conversations
- **Call Logging**: Complete call history tracking with sentiment analysis
- **Discount Strategy**: Intelligent discount recommendations based on churn risk and loyalty
- **REST API**: Full-featured API for integration with other systems

---

## 🛠️ Technology Stack

### Core Technologies
- **Python 3.8+**: Main programming language
- **Flask**: REST API framework
- **SQLAlchemy**: ORM for database management
- **SQLite/PostgreSQL**: Data storage

### AI & LLM Services
- **Servam API**: 
  - STT (Speech-to-Text) - Converts customer speech to text
  - TTS (Text-to-Speech) - Generates natural voice responses
  - LLM - Generates personalized call scripts and business logic AI
- **OpenAI/LLM Integration**: For NLP and decision-making

### Communication
- **Twilio**: Voice calls and SMS messaging
- **WebSocket**: Real-time communication

### Analysis & Reporting
- **Pandas**: Data analysis
- **NumPy**: Numerical computations

---

## 📁 Project Structure

```
beacon-hotel-relationship-manager/
├── src/                          # Source code
│   ├── agents/
│   │   └── relationship_manager_agent.py    # Main AI agent for customer analysis
│   ├── services/
│   │   ├── servam_service.py          # Servam API integration (STT/TTS/LLM)
│   │   └── twilio_service.py          # Twilio call management
│   ├── models/
│   │   └── database.py                # SQLAlchemy database models
│   ├── utils/
│   │   ├── call_logger.py             # Call logging and tracking
│   │   └── dummy_data_generator.py    # Generate test data
│   └── main.py                   # Flask REST API application
├── config/
│   └── config.py                 # Configuration management
├── data/                         # Data storage
│   └── dummy_data.xlsx           # Sample customer and call data
├── logs/                         # Application logs
├── tests/                        # Unit tests
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
└── README.md                     # This file

```

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Twilio account (for making calls)
- Servam API credentials (for STT/TTS/LLM)

### Step 1: Clone and Setup

```bash
# Clone repository
git clone <repository_url>
cd beacon-hotel-relationship-manager

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your credentials
# Required:
# - SERVAM_API_KEY
# - SERVAM_API_URL
# - TWILIO_ACCOUNT_SID
# - TWILIO_AUTH_TOKEN
# - TWILIO_PHONE_NUMBER
```

### Step 4: Initialize Database

```bash
python -c "from src.models.database import init_db; init_db()"
```

### Step 5: Generate Dummy Data (Optional)

```bash
python -c "from src.utils.dummy_data_generator import initialize_dummy_data; initialize_dummy_data()"
```

---

## 🚀 Running the Application

### Start Flask API Server

```bash
python src/main.py
```

The API will be available at `http://localhost:5000`

### Run Tests

```bash
python -m pytest tests/ -v
```

---

## 📡 API Endpoints

### Health & System
- `GET /health` - Server health check

### Customer Management
- `GET /api/v1/customers` - Get all customers
- `GET /api/v1/customers/<customer_id>` - Get customer details
- `GET /api/v1/customers/<customer_id>/analysis` - Analyze customer relationship
- `GET /api/v1/customers/<customer_id>/call-history` - Get customer's call history

### Call Management
- `POST /api/v1/calls/schedule` - Schedule calls for high-risk customers
- `POST /api/v1/calls/make` - Initiate a call to customer
- `POST /api/v1/calls/log` - Log a completed call

### Reporting & Metrics
- `GET /api/v1/metrics/summary` - Get system metrics
- `GET /api/v1/reports/export` - Export call history reports

### Development
- `POST /api/v1/init/dummy-data` - Initialize dummy data (dev only)

---

## 📊 Dummy Data

The project includes a dummy data generator with:
- **50 Sample Customers**: Diverse customer profiles with history
- **Call History**: 200+ historical calls with various outcomes
- **Sentiment Analysis**: Positive, neutral, and negative sentiments
- **Booking Data**: Simulated bookings and revenue

### Generate Dummy Data

Via API:
```bash
curl -X POST http://localhost:5000/api/v1/init/dummy-data
```

Via Python:
```python
from src.utils.dummy_data_generator import initialize_dummy_data
initialize_dummy_data()
```

---

## 🧠 How It Works

### 1. **Customer Analysis**
The AI agent analyzes each customer's history:
- Call frequency and recency
- Sentiment in previous conversations
- Booking conversion rates
- Loyalty scores
- Time since last stay

### 2. **Churn Risk Scoring**
Calculates 0-1 churn risk score based on:
- Engagement level
- Sentiment trends
- Booking patterns
- Time since interaction
- Loyalty history

### 3. **Call Scheduling**
Intelligently schedules calls:
- Prioritizes high-risk customers
- Respects call frequency limits
- Schedules during business hours
- Avoids recently contacted customers

### 4. **Call Execution**
When calling a customer:
1. Generate personalized script using LLM
2. Initiate call via Twilio
3. Monitor conversation in real-time
4. Record and transcribe call
5. Analyze sentiment and outcomes

### 5. **Call Logging**
Complete call history tracking:
- Transcript storage
- Sentiment analysis
- Booking outcomes
- Discount offered and accepted
- Follow-up actions needed

---

## 🔌 Integration Points

### Servam API
Used for three key NLP functions:
```python
# Speech to Text
text = servam_service.speech_to_text(audio_bytes)

# Text to Speech
audio = servam_service.text_to_speech("Hello customer")

# LLM for script generation
script = servam_service.generate_response(prompt)

# Sentiment analysis
sentiment = servam_service.analyze_sentiment(transcript)
```

### Twilio
Making and managing calls:
```python
# Make call
call_sid = twilio_service.make_call(phone_number, call_script)

# Get call details
details = twilio_service.get_call_details(call_sid)

# Send SMS
msg_sid = twilio_service.send_sms(phone_number, message)
```

---

## 📈 Example Workflow

```
1. User initiates call scheduling
   ↓
2. System loads all active customers
   ↓
3. For each customer:
   - Analyze call history& engagement
   - Calculate churn risk score
   - Determine if should call
   ↓
4. High-priority customers scheduled
   ↓
5. Generate personalized scripts
   ↓
6. Make calls via Twilio
   ↓
7. Record conversations
   ↓
8. Log results and update customer records
   ↓
9. Generate reports and metrics
```

---

## 📋 Environment Variables

```bash
# Environment
ENVIRONMENT=development  # or "production"
DEBUG=True

# Servam Configuration
SERVAM_API_KEY=your-api-key
SERVAM_API_URL=https://api.servam.com
SERVAM_STT_MODEL=servam-stt-v1
SERVAM_TTS_MODEL=servam-tts-v1
SERVAM_LLM_MODEL=servam-llm-v1

# Twilio Configuration
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token
TWILIO_PHONE_NUMBER=+1234567890

# Database
DATABASE_URL=sqlite:///beacon_hotel.db

# Call Management
MAX_CALLS_PER_DAY=20
MIN_DAYS_BETWEEN_CALLS=7
CALL_TIME_START=09:00
CALL_TIME_END=21:00
```

---

## 🔐 Security Considerations

- Never commit `.env` file with real credentials
- Use strong API keys and tokens
- Validate all incoming API requests
- Use HTTPS in production
- Implement proper authentication/authorization
- Sanitize customer data
- Encrypt sensitive data in database
- Regular security audits

---

## 📝 Logging

Logs are stored in `logs/app.log` with the following levels:
- INFO - General application events
- WARNING - Warnings like failed calls
- ERROR - Errors and exceptions

```python
logger.info("Call initiated")
logger.warning("Failed to reach customer")
logger.error("API error occurred")
```

---

## 🧪 Testing

Run unit tests:
```bash
pytest tests/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

---

## 🚨 Troubleshooting

### Issue: "API Key not recognized"
**Solution**: Check `.env` file has correct credentials

### Issue: "No module named 'src'"
**Solution**: Ensure you're running from project root and have activated venv

### Issue: "Database is locked"
**Solution**: Only one process should access SQLite; use PostgreSQL for production

### Issue: "Twilio call failed"
**Solution**: Verify phone number format is E.164 (+1234567890)

---

## 📊 Metrics & Analytics

The system tracks:
- **Call Volume**: Total calls made per day/week/month
- **Conversion Rate**: % of calls resulting in bookings
- **Average Sentiment**: Customer satisfaction trends
- **Churn Prevention**: Customers saved from churn
- **Revenue Impact**: Bookings attributed to outreach

Access metrics via:
```bash
GET /api/v1/metrics/summary
```

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📄 License

This project is proprietary to Beacon Hotel. All rights reserved.

---

## 👥 Support

For issues or questions:
- Email: support@beaconhotel.com
- Documentation: /docs
- Issues: GitHub Issues

---

## 🎯 Roadmap

- [ ] Implement Dify workflow integration for advanced agent orchestration
- [ ] Add WhatsApp integration for SMS-based outreach
- [ ] Machine learning model for optimal call timing
- [ ] Dashboard UI for call monitoring
- [ ] Advanced analytics and reporting
- [ ] Multi-language support
- [ ] Integration with hotel PMS (Property Management System)

---

**Made with ❤️ for Beacon Hotel**
