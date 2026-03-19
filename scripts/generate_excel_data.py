"""
Dummy Excel Data Generator for Beacon Hotel
Creates sample customer and call data in Excel format
"""
import pandas as pd
from datetime import datetime, timedelta
import random
import os

def create_dummy_excel_files():
    """Create comprehensive dummy data Excel files"""
    
    print("📊 Creating Beacon Hotel Dummy Data Excel Files...\n")
    
    # 1. Create Customers Excel
    print("Creating customers.xlsx...")
    customers_data = []
    
    first_names = ["John", "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", 
                   "Henry", "Iris", "Jack", "Karen", "Leo", "Mia", "Noah", "Olivia"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", 
                  "Davis", "Rodriguez", "Martinez"]
    room_types = ["Standard", "Deluxe", "Suite", "Penthouse"]
    
    for i in range(50):
        customers_data.append({
            'Customer ID': f'CUST{1000 + i}',
            'Name': f"{random.choice(first_names)} {random.choice(last_names)}",
            'Email': f"customer{i}@example.com",
            'Phone': f"+1{random.randint(2000000000, 9999999999)}",
            'Last Stay Date': (datetime.now() - timedelta(days=random.randint(10, 365))).strftime('%Y-%m-%d'),
            'Total Visits': random.randint(1, 15),
            'Total Spent': f"${random.uniform(500, 10000):.2f}",
            'Loyalty Score': f"{random.uniform(0, 100):.1f}",
            'Preferred Room': random.choice(room_types),
            'Status': 'Active' if random.random() > 0.25 else 'Inactive'
        })
    
    df_customers = pd.DataFrame(customers_data)
    df_customers.to_excel('data/customers.xlsx', index=False)
    print("✓ customers.xlsx created\n")
    
    # 2. Create Call History Excel
    print("Creating call_history.xlsx...")
    call_history_data = []
    
    sentiments = ["Positive", "Neutral", "Negative"]
    statuses = ["Completed", "Completed", "Completed", "Completed", "Missed", "Failed"]
    discounts = ["Welcome Back", "Loyalty", "Seasonal", "Special Offer", None]
    
    customer_ids = [f'CUST{1000 + i}' for i in range(50)]
    
    call_id = 1
    for customer_id in customer_ids:
        num_calls = random.randint(2, 8)
        for _ in range(num_calls):
            call_date = datetime.now() - timedelta(
                days=random.randint(1, 180),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            
            status = random.choice(statuses)
            duration = random.randint(60, 1800) if status == "Completed" else 0
            discount = random.choice(discounts)
            discount_pct = None
            
            if discount:
                discount_map = {
                    "Welcome Back": 10,
                    "Loyalty": 15,
                    "Seasonal": 20,
                    "Special Offer": 25
                }
                discount_pct = discount_map[discount]
            
            booking_made = random.choice([True, False, False, False])
            booking_amount = f"${random.uniform(150, 800):.2f}" if booking_made else "N/A"
            
            call_history_data.append({
                'Call ID': f'CALL{call_id:06d}',
                'Customer ID': customer_id,
                'Call Date': call_date.strftime('%Y-%m-%d %H:%M'),
                'Duration (seconds)': duration,
                'Status': status,
                'Sentiment': sentiments if status == "Completed" else "N/A",
                'Discount Offered': discount if discount else "None",
                'Discount %': discount_pct if discount_pct else 0,
                'Booking Made': 'Yes' if booking_made else 'No',
                'Booking Amount': booking_amount,
                'Notes': f'Sample call on {call_date.strftime("%Y-%m-%d")}'
            })
            call_id += 1
    
    df_calls = pd.DataFrame(call_history_data)
    df_calls.to_excel('data/call_history.xlsx', index=False)
    print("✓ call_history.xlsx created\n")
    
    # 3. Create Customer Analysis Excel
    print("Creating customer_analysis.xlsx...")
    analysis_data = []
    
    for customer in customers_data:
        # Simulate analysis data
        churn_risk = random.uniform(0, 1)
        engagement = "Low" if churn_risk > 0.7 else ("High" if churn_risk < 0.3 else "Medium")
        
        discount_map = {
            0: "Welcome Back (10%)",
            1: "Loyalty (15%)",
            2: "Seasonal (20%)",
            3: "Special Offer (25%)"
        }
        
        analysis_data.append({
            'Customer ID': customer['Customer ID'],
            'Customer Name': customer['Name'],
            'Churn Risk Score': f"{churn_risk:.2f}",
            'Engagement Level': engagement,
            'Recommended Discount': discount_map[random.randint(0, 3)],
            'Last Call Date': (datetime.now() - timedelta(days=random.randint(1, 90))).strftime('%Y-%m-%d'),
            'Next Call Recommended': (datetime.now() + timedelta(days=random.randint(7, 30))).strftime('%Y-%m-%d'),
            'Strategy': f"{'Retention campaign' if churn_risk > 0.6 else 'Maintain contact' if churn_risk > 0.3 else 'Delight customer'}"
        })
    
    df_analysis = pd.DataFrame(analysis_data)
    df_analysis.to_excel('data/customer_analysis.xlsx', index=False)
    print("✓ customer_analysis.xlsx created\n")
    
    # 4. Create Call Schedule Excel
    print("Creating call_schedule.xlsx...")
    schedule_data = []
    
    schedule_id = 1
    for i in range(30):
        customer = random.choice(customers_data)
        scheduled_date = datetime.now() + timedelta(days=random.randint(1, 14))
        
        priority_levels = ["Low (1-3)", "Medium (4-6)", "High (7-9)", "Critical (10)"]
        priority = random.choice(priority_levels)
        
        reasons = [
            "High churn risk - inactive for 6 months",
            "Low engagement - previous calls unsuccessful",
            "Loyalty milestone - 10 visits completed",
            "Seasonal promotion - special offer available",
            "Win-back campaign - former regular guest"
        ]
        
        schedule_data.append({
            'Schedule ID': f'SCH{schedule_id:05d}',
            'Customer ID': customer['Customer ID'],
            'Customer Name': customer['Name'],
            'Scheduled Date': scheduled_date.strftime('%Y-%m-%d'),
            'Scheduled Time': f"{random.randint(9, 21):02d}:00",
            'Priority': priority,
            'Reason': random.choice(reasons),
            'Recommended Offer': f"{random.choice([10, 15, 20, 25])}% discount on next stay",
            'Status': "Pending"
        })
        schedule_id += 1
    
    df_schedule = pd.DataFrame(schedule_data)
    df_schedule.to_excel('data/call_schedule.xlsx', index=False)
    print("✓ call_schedule.xlsx created\n")
    
    # 5. Create Metrics Summary Excel
    print("Creating metrics_summary.xlsx...")
    
    total_customers = len(customers_data)
    active_customers = sum(1 for c in customers_data if c['Status'] == 'Active')
    total_calls = len(call_history_data)
    bookings = sum(1 for c in call_history_data if c['Booking Made'] == 'Yes')
    conversion_rate = (bookings / total_calls * 100) if total_calls > 0 else 0
    
    metrics_data = [
        {'Metric': 'Total Customers', 'Value': total_customers, 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Active Customers', 'Value': active_customers, 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Total Calls Made', 'Value': total_calls, 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Successful Bookings', 'Value': bookings, 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Booking Conversion Rate (%)', 'Value': f"{conversion_rate:.2f}", 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Average Call Duration (min)', 'Value': f"{sum(c['Duration (seconds)'] for c in call_history_data if c['Duration (seconds)'] > 0) / (sum(1 for c in call_history_data if c['Duration (seconds)'] > 0) * 60) if sum(1 for c in call_history_data if c['Duration (seconds)'] > 0) > 0 else 0:.1f}", 'Date': datetime.now().strftime('%Y-%m-%d')},
        {'Metric': 'Calls Pending', 'Value': len(schedule_data), 'Date': datetime.now().strftime('%Y-%m-%d')},
    ]
    
    df_metrics = pd.DataFrame(metrics_data)
    df_metrics.to_excel('data/metrics_summary.xlsx', index=False)
    print("✓ metrics_summary.xlsx created\n")
    
    print("✅ All dummy data Excel files created successfully!\n")
    print("Files created:")
    print("  - data/customers.xlsx")
    print("  - data/call_history.xlsx")
    print("  - data/customer_analysis.xlsx")
    print("  - data/call_schedule.xlsx")
    print("  - data/metrics_summary.xlsx")

if __name__ == "__main__":
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    create_dummy_excel_files()
