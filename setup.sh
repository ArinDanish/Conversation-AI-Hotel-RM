#!/bin/bash
# Quick start script for Beacon Hotel Relationship Manager

echo "🏨 Beacon Hotel Relationship Manager Setup"
echo "==========================================="
echo ""

# Check Python version
python_version=$(python --version 2>&1)
echo "📦 Python version: $python_version"

# Create virtual environment
echo ""
echo "🔧 Creating virtual environment..."
python -m venv venv

# Activate virtual environment
echo "✓ Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Initialize database
echo ""
echo "🗄️  Initializing database..."
python -c "from src.models.database import init_db; init_db()"

# Generate dummy data
echo ""
echo "📊 Generating dummy data..."
python -c "from src.utils.dummy_data_generator import initialize_dummy_data; initialize_dummy_data()"

# Create .env file if it doesn't exist
echo ""
echo "⚙️  Setting up configuration..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✓ Created .env file (update with your credentials)"
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🚀 To start the application, run:"
echo "   python src/main.py"
echo ""
echo "📖 API Documentation: http://localhost:5000/api/v1/health"
echo ""
