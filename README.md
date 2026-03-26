# Beacon Hotel Relationship Manager - AI Voice Agent

## 📋 Project Overview

**Beacon Hotel Relationship Manager** is an AI-powered voice agent that makes outbound phone calls to hotel customers for relationship management. The system uses **LiveKit SIP** for real-time voice communication, **Sarvam AI** for Speech-to-Text, LLM reasoning, and Text-to-Speech, and **Twilio** for PSTN connectivity. The AI agent "Raj" calls customers, checks in on their experience, and offers personalized loyalty discounts.

### 🎯 Key Features

- **Outbound AI Voice Calls**: Automated phone calls via Twilio SIP → LiveKit → AI Agent
- **Real-time STT/TTS Pipeline**: Sarvam saaras:v3 (STT) → sarvam-m (LLM) → bulbul:v3 (TTS)
- **Personalized Conversations**: Agent "Raj" speaks naturally with customer context (visits, loyalty score, preferences)
- **Tiered Discount Strategy**: 20% (5+ visits), 15% (2-4 visits), 10% (new customers)
- **Automatic Call Ending**: Goodbye detection + max turn limit with SIP hangup
- **Audio Recording**: Records both caller and agent audio as WAV files
- **Multilingual Support**: English and Hindi (en-IN / hi-IN)
- **Churn Risk Analysis**: Customer analysis with engagement scoring
- **REST API**: FastAPI with automatic OpenAPI docs
- **Think-Tag Stripping**: Robust handling of LLM reasoning output (sarvam-m always produces `<think>` blocks)

---

## 🏗️ Architecture

```
┌──────────────┐     SIP/PSTN      ┌──────────────┐    WebRTC     ┌──────────────────────┐
│   Customer   │ ◄──────────────── │    Twilio     │ ◄──────────► │   LiveKit Cloud      │
│   Phone      │                   │  SIP Trunk    │              │   (India South)      │
└──────────────┘                   └──────────────┘              └──────────┬───────────┘
                                                                           │
                                                                    WebRTC │ Audio
                                                                           │
                                                                 ┌─────────▼───────────┐
                                                                 │   AI Agent (Python)  │
                                                                 │                      │
                                                                 │  Caller Audio ──►    │
                                                                 │  Sarvam STT ──►     │
                                                                 │  Sarvam LLM ──►     │
                                                                 │  Sarvam TTS ──►     │
                                                                 │  ──► LiveKit Audio   │
                                                                 └──────────────────────┘
```

**Call Flow:**
1. FastAPI endpoint triggers outbound call
2. LiveKit room is created, AI agent dispatched
3. SIP call placed via Twilio to customer's phone
4. Customer audio → Sarvam STT (saaras:v3) → text
5. Text → Sarvam LLM (sarvam-m, `reasoning_effort="low"`) → response (think-tags stripped)
6. Response → Sarvam TTS (bulbul:v3, speaker "aditya") → audio
7. Audio played back to customer via LiveKit → SIP → Twilio → PSTN
8. Goodbye detected → SIP participant removed → call ends

---

## 🛠️ Technology Stack

### Core Technologies
- **Python 3.11**: Main programming language
- **FastAPI 0.104.1**: REST API framework with automatic OpenAPI docs
- **Uvicorn**: ASGI server (port 8000)
- **SQLAlchemy**: ORM for database management
- **SQLite**: Data storage

### Voice & AI Services
- **Sarvam AI** (sarvamai v0.1.27):
  - **STT**: saaras:v3 — Speech-to-Text (REST API, en-IN/hi-IN)
  - **TTS**: bulbul:v3 — Text-to-Speech (speaker "aditya", male Indian voice, linear16, 16kHz)
  - **LLM**: sarvam-m — Reasoning model with `reasoning_effort="low"` and streaming support

### Real-time Communication
- **LiveKit** (livekit v1.1.3, livekit-agents v1.5.1, livekit-api v1.1.0):
  - LiveKit Cloud (India South region)
  - SIP service for PSTN bridging
  - WebRTC rooms for real-time audio
- **Twilio**: Elastic SIP Trunking for PSTN connectivity

### Analysis & Reporting
- **Pandas**: Data analysis
- **NumPy**: Numerical computations

---

## 📁 Project Structure

```
Conversation-AI-Hotel-RM/
├── src/                              # Source code
│   ├── main_fastapi.py               # FastAPI REST API application (port 8000)
│   ├── main.py                       # Legacy Flask application
│   ├── agents/
│   │   └── relationship_manager_agent.py  # Customer analysis & churn scoring
│   ├── services/
│   │   ├── livekit_sip_agent.py      # ★ Main SIP voice agent (STT→LLM→TTS pipeline)
│   │   ├── livekit_streaming_service.py   # LiveKit streaming helpers
│   │   ├── servam_service.py         # Sarvam API wrapper
│   │   ├── twilio_service.py         # Twilio call management
│   │   ├── audio_service.py          # Audio processing utilities
│   │   ├── conversational_call_handler.py # Conversational call flow
│   │   └── dify_agent.py             # Dify agent integration
│   ├── models/
│   │   └── database.py               # SQLAlchemy models (Customer, CallHistory, etc.)
│   └── utils/
│       ├── call_logger.py            # Call logging and tracking
│       └── dummy_data_generator.py   # Generate test customer data
├── config/
│   └── config.py                     # Configuration management (.env loader)
├── run_agent.py                      # LiveKit agent worker launcher
├── audio/                            # Recorded call audio (caller + agent WAV files)
├── logs/
│   └── agent_session.log             # Agent session logs (file-based logging)
├── data/                             # Data storage (SQLite DB, Excel data)
├── scripts/
│   └── generate_excel_data.py        # Excel data generation script
├── examples/
│   └── multilingual_examples.py      # Multilingual usage examples
├── tests/
│   └── test_relationship_manager.py  # Unit tests
├── requirements.txt                  # Python dependencies
├── setup.bat                         # Windows setup script
├── setup.sh                          # Linux/macOS setup script
└── README.md                         # This file
```

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.11+
- pip (Python package manager)
- Twilio account with Elastic SIP Trunking
- Sarvam AI API key
- LiveKit Cloud account (or self-hosted LiveKit server)

### Step 1: Clone and Setup

```bash
# Clone repository
git clone <repository_url>
cd Conversation-AI-Hotel-RM

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
source .venv/bin/activate
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment

Create a `.env` file in the project root:

```bash
# Sarvam AI Configuration
SARVAM_API_KEY=your-sarvam-api-key

# LiveKit Configuration
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-livekit-api-key
LIVEKIT_API_SECRET=your-livekit-api-secret
LIVEKIT_SIP_TRUNK_ID=your-sip-trunk-id

# Twilio Configuration
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# Database
DATABASE_URL=sqlite:///beacon_hotel.db

# Environment
ENVIRONMENT=development
DEBUG=True
```

### Step 4: Initialize Database & Dummy Data

```bash
python -c "from src.models.database import init_db; init_db()"
python -c "from src.utils.dummy_data_generator import initialize_dummy_data; initialize_dummy_data()"
```

Or via API after starting the server:
```bash
curl -X POST http://localhost:8000/api/v1/init/dummy-data
```

---

## 🚀 Running the Application

### 1. Start the FastAPI Server

```bash
python src/main_fastapi.py
```

The API will be available at `http://localhost:8000` with interactive docs at `http://localhost:8000/docs`.

### 2. Start the LiveKit Agent Worker

In a separate terminal:

```bash
python run_agent.py dev
```

This starts the LiveKit agent worker that handles voice calls.

### 3. Make a Test Call

```bash
curl -X POST http://localhost:8000/api/v1/calls/test-livekit-sip \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "CUST1052", "language": "en"}'
```

### 4. Monitor Logs

Agent logs are written to `logs/agent_session.log` (livekit-agents captures child process stdout):

```powershell
# Windows (real-time tail):
Get-Content logs/agent_session.log -Tail 50 -Wait

# Linux/macOS:
tail -f logs/agent_session.log
```

---

## 📡 API Endpoints

### Health & System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API info |
| `GET` | `/health` | Server health check |

### Customer Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/customers` | List all customers |
| `GET` | `/api/v1/customers/{id}` | Get customer details |
| `PUT` | `/api/v1/customers/{id}` | Update customer |
| `GET` | `/api/v1/customers/{id}/analysis` | Analyze customer relationship |
| `GET` | `/api/v1/customers/{id}/call-history` | Get customer call history |
| `POST` | `/api/v1/customers/create` | Create a customer |
| `POST` | `/api/v1/customers/create-bulk` | Bulk create customers |

### Call Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/calls/test-livekit-sip` | **Place outbound AI voice call via LiveKit SIP** |
| `POST` | `/api/v1/calls/schedule` | Schedule calls for high-risk customers |
| `POST` | `/api/v1/calls/make` | Initiate a call to customer |
| `POST` | `/api/v1/calls/log` | Log a completed call |
| `GET` | `/api/v1/calls/conversational-demo` | Conversational call demo |

### Streaming & Audio
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/stream/livekit/session` | Create LiveKit streaming session |
| `WS` | `/api/v1/stream/livekit/ws/{session_id}` | LiveKit WebSocket stream |
| `WS` | `/api/v1/stream/twilio/ws` | Twilio WebSocket stream |
| `GET` | `/api/v1/audio/generate` | Generate TTS audio |

### Reporting & Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/metrics/summary` | System metrics |
| `GET` | `/api/v1/reports/export` | Export call history reports |
| `POST` | `/api/v1/init/dummy-data` | Initialize dummy data |

---

## 🧠 How It Works

### 1. Outbound Call Flow
```
API Request (customer_id) → Create LiveKit Room → Dispatch AI Agent → Place SIP Call via Twilio
                                                                            │
Customer Answers ──► Audio streams to LiveKit Room ──► AI Agent receives audio
                                                                            │
                    Sarvam STT (saaras:v3) ◄──── Buffered audio chunks (1s) │
                            │                                               │
                            ▼                                               │
                    Sarvam LLM (sarvam-m) ◄── Conversation history + system prompt
                            │                                               │
                            ▼                                               │
                    Strip <think> tags ──► Split into sentences             │
                            │                                               │
                            ▼                                               │
                    Sarvam TTS (bulbul:v3) ──► Sentence-level pipelining    │
                            │                                               │
                            ▼                                               │
                    Play audio via LiveKit ──► SIP ──► Twilio ──► Customer phone
```

### 2. Agent Persona — "Raj"
- Warm, friendly male relationship manager at Beacon Hotel
- Uses speaker "aditya" (male Indian voice) for TTS
- Makes outbound calls to check in on customers and offer loyalty discounts
- Responds in English or Hindi based on configuration
- Keeps responses short (1-2 sentences)
- Ends calls gracefully after discount is offered and acknowledged

### 3. LLM Think-Tag Handling
The Sarvam `sarvam-m` model always produces `<think>` reasoning blocks. The agent handles this with:
- `_strip_think_tags()` helper handling 4 cases: complete tags, messy tags, unclosed `<think>`, no tags
- `reasoning_effort="low"` to minimize thinking overhead
- 3-tier fallback chain: streaming LLM → non-streaming LLM → retry with direct prompt → hardcoded fallback

### 4. Discount Strategy
| Customer Visits | Discount Offered |
|----------------|-----------------|
| 5+ visits | 20% loyalty discount |
| 2-4 visits | 15% loyalty discount |
| < 2 visits | 10% welcome discount |
| Bad experience | 30% recovery discount |

### 5. Call Ending
The agent detects call endings through:
- **Agent goodbye keywords**: "goodbye", "take care", "have a great day", etc.
- **User goodbye keywords**: "bye", "thanks bye", "ok bye", etc.
- **Max turn limit**: 8 turns
- Ends call by removing SIP participant via LiveKit API

---

## 📊 Latency Breakdown

Measured from a real test call:

| Stage | Latency |
|-------|---------|
| Greeting TTS | ~4.7s (151 chars → 9.1s audio) |
| STT per chunk | ~300–750ms per 1s audio |
| LLM streaming | ~3.9s (with thinking overhead) |
| TTS per sentence | ~1.2–3.0s per sentence |
| **First audio to user** | **~3.9s** after user stops speaking |
| **Full turn** | **~18s** (user spoke → agent finished playing) |

**Bottlenecks**: LLM thinking overhead (~3.9s), TTS REST API latency (~1-3s/sentence).

---

## 📝 Logging

Agent logs are written to `logs/agent_session.log` with detailed timing information:

```
[TIMING] STT: 753ms for 1000ms audio → 'Right.'
[TIMING] LLM streaming: 3880ms, raw=1818 chars, clean=155 chars
[TIMING] TTS: 1173ms for 19 chars → 1.5s audio
[TIMING] Turn 1 total: 18354ms
```

The LiveKit agent worker spawns child processes, so console output is captured by the framework. Use file-based logging for reliable monitoring.

---

## 🔐 Security Considerations

- Never commit `.env` file with real credentials
- All API keys stored in environment variables
- Use HTTPS in production
- Validate all incoming API requests
- Phone numbers in E.164 format
- Audio recordings stored locally (not transmitted externally)

---

## 🧪 Testing

```bash
# Run unit tests
python -m pytest tests/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=html
```

---

## 🚨 Troubleshooting

### Issue: "livekit-agents SDK not installed"
**Solution**: `pip install livekit livekit-agents livekit-api`

### Issue: "LiveKit SIP not configured"
**Solution**: Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_SIP_TRUNK_ID` in `.env`

### Issue: No console logs from agent
**Solution**: Agent runs in a child process. Check `logs/agent_session.log` instead. Use `Get-Content logs/agent_session.log -Tail 50 -Wait` (Windows) or `tail -f` (Linux).

### Issue: Agent speaks thinking/reasoning text
**Solution**: This is handled by `_strip_think_tags()`. The `sarvam-m` model always produces `<think>` blocks; they are stripped before TTS.

### Issue: "No module named 'src'"
**Solution**: Ensure you're running from the project root and have activated the venv.

### Issue: "Twilio call failed"
**Solution**: Verify phone number format is E.164 (`+1234567890`). Check SIP trunk configuration in Twilio console.

### Issue: LLM returns empty response (think-only)
**Solution**: The agent has a 3-tier fallback: streaming → non-streaming → retry with direct prompt → hardcoded contextual fallback.

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
