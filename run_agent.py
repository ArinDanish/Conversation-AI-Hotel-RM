"""
Launch the LiveKit SIP agent worker.

Usage:
    python run_agent.py dev       # development mode (auto-reload, verbose)
    python run_agent.py start     # production mode
"""
import sys
import os
import logging

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging so our module logs are visible
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from src.services.livekit_sip_agent import run_agent_worker

if __name__ == "__main__":
    run_agent_worker()
