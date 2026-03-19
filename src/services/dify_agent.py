"""
Dify/Workflow Agent Integration for Beacon Hotel
This module integrates with Dify for advanced workflow automation
"""
import requests
import logging
from typing import Optional, Dict
from config.config import get_config

logger = logging.getLogger(__name__)
config = get_config()

class DifyAgentClient:
    """Client for Dify workflow automation platform"""
    
    def __init__(self):
        self.api_key = config.DIFY_API_KEY
        self.base_url = config.DIFY_API_URL
        self.workflow_id = config.WORKFLOW_ID
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def analyze_customer(self, customer_data: Dict) -> Optional[Dict]:
        """
        Send customer data to Dify workflow for advanced analysis
        
        Args:
            customer_data: Customer information dictionary
            
        Returns:
            Analysis result from workflow
        """
        try:
            url = f"{self.base_url}/workflows/{self.workflow_id}/run"
            
            payload = {
                "inputs": customer_data,
                "user": "relationship-manager-ai"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info(f"Dify analysis completed for customer")
                return result
            else:
                logger.error(f"Dify workflow failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling Dify workflow: {str(e)}")
            return None
    
    def generate_call_strategy(self, customer_analysis: Dict) -> Optional[Dict]:
        """
        Use Dify to generate optimal calling strategy
        
        Args:
            customer_analysis: Customer analysis data
            
        Returns:
            Recommended strategy
        """
        try:
            url = f"{self.base_url}/workflows/{self.workflow_id}/run"
            
            payload = {
                "inputs": {
                    "action": "generate_strategy",
                    "analysis": customer_analysis
                },
                "user": "relationship-manager-ai"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info("Strategy generated via Dify")
                return result
            else:
                logger.error(f"Strategy generation failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error generating strategy: {str(e)}")
            return None
    
    def process_call_result(self, call_data: Dict) -> Optional[Dict]:
        """
        Process call result through Dify workflow
        
        Args:
            call_data: Call information and transcript
            
        Returns:
            Processing result
        """
        try:
            url = f"{self.base_url}/workflows/{self.workflow_id}/run"
            
            payload = {
                "inputs": {
                    "action": "process_call",
                    "call_data": call_data
                },
                "user": "relationship-manager-ai"
            }
            
            response = requests.post(
                url,
                headers=self.headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code in [200, 201]:
                result = response.json()
                logger.info("Call result processed via Dify")
                return result
            else:
                logger.error(f"Call processing failed: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error processing call result: {str(e)}")
            return None
