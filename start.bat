@echo off
echo Starting Investment Platform Backend...
echo.

cd /d "C:\Users\use\PycharmProjects\PythonProject\plat\backend"

REM Check if venv exists
if not exist "venv\" (
    echo Creating virtual environment...
    py -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt 2>nul || pip install Flask Flask-CORS pymongo python-dotenv bcrypt PyJWT

echo.
echo Starting server...
echo Open: http://localhost:5000
echo.
python app.py

pause