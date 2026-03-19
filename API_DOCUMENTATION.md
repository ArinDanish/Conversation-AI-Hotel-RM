"""
API Documentation and Integration Guide
"""

# Beacon Hotel Relationship Manager - API Guide

## Overview
This document provides detailed API documentation for the Beacon Hotel Relationship Manager system.

## Base URL
```
http://localhost:5000/api/v1
```

## Authentication
Currently, the API doesn't require authentication (for development).
For production, implement JWT or API key authentication.

---

## Health Check

### GET /health
Check if server is running and healthy.

**Response:**
```json
{
  "status": "healthy",
  "hotel": "Beacon Hotel",
  "environment": "development",
  "timestamp": "2026-03-18T10:30:00"
}
```

---

## Customer Endpoints

### GET /customers
Get all customers (paginated).

**Query Parameters:**
- `limit` (optional): Number of records (default: 50)

**Response:**
```json
{
  "count": 50,
  "customers": [
    {
      "customer_id": "CUST1000",
      "name": "John Smith",
      "email": "john@example.com",
      "phone": "+11234567890",
      "total_visits": 5,
      "loyalty_score": 75.5,
      "is_active": true
    }
  ]
}
```

### GET /customers/{customer_id}
Get specific customer details.

**Response:**
```json
{
  "customer_id": "CUST1000",
  "name": "John Smith",
  "email": "john@example.com",
  "phone": "+11234567890",
  "last_stay_date": "2025-08-15",
  "total_visits": 5,
  "total_spent": 2450.50,
  "loyalty_score": 75.5,
  "preferred_room_type": "Deluxe",
  "is_active": true
}
```

### GET /customers/{customer_id}/analysis
Analyze customer relationship and get insights.

**Response:**
```json
{
  "customer_id": "CUST1000",
  "customer_name": "John Smith",
  "total_visits": 5,
  "total_spent": 2450.50,
  "loyalty_score": 75.5,
  "total_calls": 8,
  "completed_calls": 7,
  "avg_sentiment_score": 0.78,
  "booking_conversion_rate": 0.43,
  "days_since_last_stay": 45,
  "days_since_last_call": 12,
  "churn_risk_score": 0.35,
  "engagement_level": "high",
  "recommended_discount": 15,
  "call_history_summary": "Recent calls: 2\n- 2026-03-10: COMPLETED, Sentiment: positive\n- 2026-02-28: COMPLETED, Sentiment: positive"
}
```

### GET /customers/{customer_id}/call-history
Get customer's historical calls.

**Query Parameters:**
- `limit` (optional): Number of records (default: 20)

**Response:**
```json
{
  "customer_id": "CUST1000",
  "call_count": 8,
  "calls": [
    {
      "call_date": "2026-03-10T14:30:00",
      "duration": 480,
      "status": "completed",
      "sentiment": "positive",
      "discount_offered": "loyalty",
      "booking_made": true,
      "booking_amount": 350.00
    }
  ]
}
```

---

## Call Management Endpoints

### POST /calls/schedule
Schedule calls for high-priority customers.

**Request:**
```json
{}
```

**Response:**
```json
{
  "status": "success",
  "scheduled_count": 12,
  "calls": [
    {
      "customer_id": "CUST1005",
      "customer_name": "Alice Johnson",
      "scheduled_time": "2026-03-19T10:00:00",
      "priority": 10,
      "reason": "Risk Score: 0.78"
    }
  ]
}
```

### POST /calls/make
Initiate a call to a customer.

**Request:**
```json
{
  "customer_id": "CUST1000"
}
```

**Response:**
```json
{
  "status": "call_initiated",
  "call_sid": "CA1234567890abcdef1234567890abcdef",
  "customer_name": "John Smith",
  "phone": "+11234567890",
  "churn_risk": 0.35,
  "recommended_offer": "15% discount"
}
```

### POST /calls/log
Log a completed call.

**Request:**
```json
{
  "customer_id": "CUST1000",
  "call_sid": "CA1234567890abcdef1234567890abcdef",
  "transcript": "Customer conversation transcript...",
  "duration": 300,
  "discount_offered": "loyalty",
  "discount_percentage": 15,
  "booking_made": true,
  "booking_amount": 350.00
}
```

**Response:**
```json
{
  "status": "call_logged"
}
```

---

## Metrics & Reporting

### GET /metrics/summary
Get system metrics summary.

**Response:**
```json
{
  "total_customers": 50,
  "active_customers": 38,
  "total_calls": 247,
  "booking_conversion_rate": 24.5,
  "average_sentiment_score": 0.72,
  "timestamp": "2026-03-18T10:30:00"
}
```

### GET /reports/export
Export call data.

**Query Parameters:**
- `type`: Report format (json, csv) - default: json
- `days`: Number of days to export (default: 30)

**Response:**
Downloads file with call data

---

## Development Endpoints

### POST /init/dummy-data
Initialize dummy data (development only).

**Note:** Only works when ENVIRONMENT=development

**Response:**
```json
{
  "status": "Dummy data initialized successfully"
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "Customer ID required"
}
```

### 404 Not Found
```json
{
  "error": "Customer not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

---

## Example Workflows

### Workflow 1: Analyze and Call Customer

```bash
# 1. Get customer details
GET /api/v1/customers/CUST1000

# 2. Analyze relationship
GET /api/v1/customers/CUST1000/analysis

# 3. Make call
POST /api/v1/calls/make
{
  "customer_id": "CUST1000"
}

# 4. Log result after call completes
POST /api/v1/calls/log
{
  "customer_id": "CUST1000",
  "transcript": "...",
  "duration": 300,
  "booking_made": true,
  "booking_amount": 350.00
}
```

### Workflow 2: Schedule and Execute Calls

```bash
# 1. Schedule calls for all customers
POST /api/v1/calls/schedule

# 2. Get scheduled calls and execute

# 3. Monitor metrics
GET /api/v1/metrics/summary

# 4. Export results
GET /api/v1/reports/export?type=json&days=7
```

---

## Rate Limiting
Currently no rate limiting. Implement for production:
- 100 requests per minute per IP
- 1000 requests per hour per API key

---

## Best Practices

1. **Always check churn_risk_score** before deciding to call
2. **Respect MIN_DAYS_BETWEEN_CALLS** configuration
3. **Use recommended_discount** from analysis
4. **Log all calls** for accurate reporting
5. **Monitor sentiment trends** for campaign effectiveness
6. **Use pagination** for large customer lists

---

## Integration Example (Python)

```python
import requests

BASE_URL = "http://localhost:5000/api/v1"

# Get customer analysis
response = requests.get(f"{BASE_URL}/customers/CUST1000/analysis")
analysis = response.json()

if analysis['churn_risk_score'] > 0.5:
    # Make call
    call_response = requests.post(
        f"{BASE_URL}/calls/make",
        json={"customer_id": "CUST1000"}
    )
    
    call_data = call_response.json()
    print(f"Call initiated: {call_data['call_sid']}")
```

---

## Integration Example (cURL)

```bash
# Get customer analysis
curl -X GET http://localhost:5000/api/v1/customers/CUST1000/analysis

# Make call
curl -X POST http://localhost:5000/api/v1/calls/make \
  -H "Content-Type: application/json" \
  -d '{"customer_id": "CUST1000"}'

# Get metrics
curl -X GET http://localhost:5000/api/v1/metrics/summary
```

---

## Support
For issues or questions, refer to the main README.md or contact support team.
