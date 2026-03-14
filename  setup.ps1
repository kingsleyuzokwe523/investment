# setup.ps1 - Save this in backend folder
Write-Host "🚀 Setting up Backend..." -ForegroundColor Green

# 1. Create virtual environment
Write-Host "1. Creating venv..." -ForegroundColor Yellow
py -m venv venv

# 2. Activate it
Write-Host "2. Activating venv..." -ForegroundColor Yellow
.\venv\Scripts\activate

# 3. Install packages
Write-Host "3. Installing packages..." -ForegroundColor Yellow
pip install Flask Flask-CORS pymongo python-dotenv bcrypt PyJWT

Write-Host "✅ Setup done! Now create .env file" -ForegroundColor Green