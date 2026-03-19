"""
Dummy data generator for testing and demonstration
"""
import random
from datetime import datetime, timedelta
from src.models.database import (
    get_session, Customer, CallHistory, 
    RelationshipAnalysis, init_db
)

def generate_dummy_customers(count: int = 50):
    """Generate dummy customer records"""
    session = get_session()
    
    first_names = ["John", "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", 
                   "Henry", "Iris", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", 
                  "Davis", "Rodriguez", "Martinez"]
    
    room_types = ["Standard", "Deluxe", "Suite", "Penthouse"]
    
    for i in range(count):
        customer = Customer(
            customer_id=f"CUST{1000 + i}",
            name=f"{random.choice(first_names)} {random.choice(last_names)}",
            email=f"customer{i}@example.com",
            phone=f"+1{random.randint(2000000000, 9999999999)}",
            last_stay_date=datetime.utcnow() - timedelta(days=random.randint(10, 365)),
            total_visits=random.randint(1, 15),
            total_spent=random.uniform(500, 10000),
            loyalty_score=random.uniform(0, 100),
            preferred_room_type=random.choice(room_types),
            is_active=random.choice([True, True, True, False])  # 75% active
        )
        session.add(customer)
    
    session.commit()
    print(f"✓ Generated {count} dummy customers")

def generate_dummy_call_history(customers_count: int = 50):
    """Generate dummy call history records"""
    session = get_session()
    
    sentiments = ["positive", "neutral", "negative"]
    statuses = ["completed", "completed", "completed", "completed", "missed", "failed"]
    
    customers = session.query(Customer).limit(customers_count).all()
    
    for customer in customers:
        # Generate 2-8 calls per customer
        num_calls = random.randint(2, 8)
        
        for j in range(num_calls):
            call_date = datetime.utcnow() - timedelta(
                days=random.randint(1, 180),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            
            status = random.choice(statuses)
            duration = random.randint(60, 1800) if status == "completed" else 0
            
            booking_made = random.choice([True, False, False, False])  # 25% booking rate
            discount_offered = None
            discount_percentage = None
            
            if random.random() > 0.6:
                discount_offered = random.choice(["welcome_back", "loyalty", "seasonal"])
                discounts = {"welcome_back": 10, "loyalty": 15, "seasonal": 20}
                discount_percentage = discounts[discount_offered]
            
            call = CallHistory(
                customer_id=customer.customer_id,
                call_date=call_date,
                call_duration=duration,
                call_status=status,
                sentiment=random.choice(sentiments) if status == "completed" else None,
                discount_offered=discount_offered,
                discount_percentage=discount_percentage,
                booking_made=booking_made,
                booking_amount=random.uniform(150, 800) if booking_made else None,
                conversation_transcript=f"Sample transcript for call on {call_date.strftime('%Y-%m-%d')}"
            )
            session.add(call)
    
    session.commit()
    print(f"✓ Generated call history for {customers_count} customers")

def generate_dummy_analysis():
    """Generate dummy relationship analysis records"""
    session = get_session()
    
    customers = session.query(Customer).all()
    
    for customer in customers:
        # Get customer's calls
        calls = session.query(CallHistory).filter_by(
            customer_id=customer.customer_id
        ).all()
        
        if not calls:
            continue
        
        # Calculate metrics
        churn_risk = random.uniform(0, 1)
        engagement_levels = ["low", "medium", "high"]
        discount_types = ["welcome_back", "loyalty", "seasonal", "special_offer"]
        
        analysis = RelationshipAnalysis(
            customer_id=customer.customer_id,
            churn_risk_score=churn_risk,
            engagement_level=random.choice(engagement_levels),
            recommended_discount=random.choice(discount_types),
            strategy=f"Focus on retention strategy for {customer.name}",
            analysis_notes="Generated analysis for demo purposes"
        )
        session.add(analysis)
    
    session.commit()
    print(f"✓ Generated relationship analysis for {len(customers)} customers")

def initialize_dummy_data():
    """Initialize all dummy data"""
    print("\n📊 Generating Beacon Hotel Dummy Data...\n")
    
    # Initialize database
    init_db()
    print("✓ Database initialized")
    
    # Generate data
    generate_dummy_customers(50)
    generate_dummy_call_history(50)
    generate_dummy_analysis()
    
    print("\n✅ Dummy data generation complete!\n")

if __name__ == "__main__":
    initialize_dummy_data()
