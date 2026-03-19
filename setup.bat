@echo off
REM Quick start script for Beacon Hotel Relationship Manager (Windows)

echo 🏨 Beacon Hotel Relationship Manager Setup
echo ===========================================
echo.

REM Check Python version
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set python_version=%%i
echo 📦 Python version: %python_version%

REM Create virtual environment
echo.
echo 🔧 Creating virtual environment...
python -m venv venv

REM Activate virtual environment
echo ✓ Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo.
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Initialize database
echo.
echo 🗄️  Initializing database...
python -c "from src.models.database import init_db; init_db()"

REM Generate dummy data
echo.
echo 📊 Generating dummy data...
python -c "from src.utils.dummy_data_generator import initialize_dummy_data; initialize_dummy_data()"

REM Create .env file if it doesn't exist
echo.
echo ⚙️  Setting up configuration...
if not exist .env (
    copy .env.example .env
    echo ✓ Created .env file (update with your credentials)
)

echo.
echo ✅ Setup complete!
echo.
echo 🚀 To start the application, run:
echo    python src/main.py
echo.
echo 📖 API Documentation: http://localhost:5000/api/v1/health
echo.
pause
