import os
import bcrypt
import jwt
import random
import string
import hmac
import hashlib
import requests
import mimetypes
import smtplib
import logging
import traceback
import atexit
import html
import time
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__, static_folder='static', template_folder='static')

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')
app.config['JWT_EXPIRATION_DAYS'] = 30

# NOWPayments Configuration
app.config['NOWPAYMENTS_API_KEY'] = os.getenv('NOWPAYMENTS_API_KEY', 'T25301Z-4WJMKC1-G41XRH2-DNA8HRZ')
app.config['NOWPAYMENTS_IPN_SECRET'] = os.getenv('NOWPAYMENTS_IPN_SECRET', 'bb6805f6-dbbb-442d-b31c-255dd3078628')
app.config['NOWPAYMENTS_API_URL'] = 'https://api.nowpayments.io/v1'

# ==================== URL CONFIGURATION ====================
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://www.veloxtrades.com.ng')
FRONTEND_URL_NON_WWW = 'https://veloxtrades.com.ng'
BACKEND_URL = os.getenv('BACKEND_URL', 'https://investment-gto3.onrender.com')

# Admin reset secret - CHANGE THIS IN PRODUCTION!
ADMIN_RESET_SECRET = os.getenv('ADMIN_RESET_SECRET', 'veloxtrades-admin-reset-2025')

# ==================== CORS CONFIGURATION ====================

# Define allowed origins
ALLOWED_ORIGINS = [
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "http://localhost:3000",
    "http://localhost:5500",
    "https://frontend-ugb2.onrender.com",
    "https://elite-eky6.onrender.com",
    "https://veloxtrades.com.ng",
    "https://www.veloxtrades.com.ng",
    "https://velox-wnn4.onrender.com",
    "https://investment-gto3.onrender.com"
]

# Configure CORS properly
CORS(app, 
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken", "Origin"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=86400)

@app.after_request
def after_request(response):
    """Add security headers"""
    response.headers.add('X-Content-Type-Options', 'nosniff')
    response.headers.add('X-Frame-Options', 'DENY')
    response.headers.add('X-XSS-Protection', '1; mode=block')
    return response

@app.before_request
def handle_preflight():
    """Handle preflight requests"""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = FRONTEND_URL
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'
        return response

def add_cors_headers(response):
    """Helper to ensure CORS headers"""
    origin = request.headers.get('Origin', '')
    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = FRONTEND_URL
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

# Mime types
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('text/html', '.html')

# ==================== EMAIL CONFIGURATION ====================
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USER = 'kingsleyuzokwe523@gmail.com'
EMAIL_PASSWORD = 'aonjmqllcpuwlwkp'
EMAIL_FROM = 'admin@veloxtrades.ltd'
ADMIN_EMAIL = 'kingsleyuzokwe523@gmail.com'

# ==================== ENHANCED EMAIL FUNCTION ====================
def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email to user with retry logic and proper error handling"""
    for attempt in range(max_retries):
        try:
            # Validate email format
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
                logger.error(f"❌ Invalid email format: {to_email}")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['From'] = EMAIL_FROM
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add plain text version
            part1 = MIMEText(body, 'plain')
            msg.attach(part1)
            
            # Add HTML version if provided
            if html_body:
                part2 = MIMEText(html_body, 'html')
                msg.attach(part2)
            
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {to_email}: {subject}")
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ Email authentication error: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return False
        except Exception as e:
            logger.error(f"❌ Email error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return False
    
    return False

# ==================== EMAIL FUNCTIONS ====================
def send_deposit_approved_email(user, amount, crypto, transaction_id):
    subject = f"✅ Deposit Approved - ${amount} added to your Veloxtrades account"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour deposit of ${amount:,.2f} via {crypto.upper()} has been approved and added to your wallet.\n\nTransaction ID: {transaction_id or 'N/A'}\n\nThank you for investing with Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{subject}</title></head>
<body style="font-family: Arial, sans-serif;">
<div style="max-width: 600px; margin: 0 auto; padding: 20px;">
<div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
<h2>✅ Deposit Approved</h2>
</div>
<div style="padding: 20px; background: #f9fafb;">
<p>Dear <strong>{html.escape(user.get('full_name', user['username']))}</strong>,</p>
<p>Your deposit of <strong>${amount:,.2f}</strong> via <strong>{crypto.upper()}</strong> has been approved and added to your wallet.</p>
<p><strong>Transaction ID:</strong> {transaction_id or 'N/A'}</p>
<p>Thank you for investing with Veloxtrades!</p>
</div>
<div style="text-align: center; padding: 20px; font-size: 12px; color: #6b7280;">
<p>© 2025 Veloxtrades. All rights reserved.</p>
</div>
</div>
</body>
</html>
"""
    return send_email(user['email'], subject, body, html_body)

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount} - Veloxtrades"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour deposit of ${amount:,.2f} via {crypto.upper()} has been REJECTED.\n\nReason: {reason}\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount} sent to your wallet"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour withdrawal of ${amount:,.2f} to {currency.upper()} has been APPROVED and processed.\n\nWallet Address: {wallet_address}\n\nThank you for trading with Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount} - Veloxtrades"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour withdrawal request of ${amount:,.2f} to {currency.upper()} has been REJECTED.\n\nReason: {reason}\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_investment_created_email(user, amount, plan_name, expected_profit):
    subject = f"🚀 Investment Created - ${amount:,.2f} in {plan_name}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nCongratulations! Your investment of ${amount:,.2f} in {plan_name} has been successfully created.\n\nExpected Profit: ${expected_profit:,.2f}\nTotal Return: ${amount + expected_profit:,.2f}\n\nTrack your investment in your dashboard.\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_investment_completed_email(user, amount, plan_name, profit):
    subject = f"🎉 Investment Completed - You earned ${profit:,.2f}!"
    body = f"Dear {user.get('full_name', user['username'])},\n\nGreat news! Your investment of ${amount:,.2f} in {plan_name} has been completed.\n\nProfit Earned: ${profit:,.2f}\nTotal Returned: ${amount + profit:,.2f}\n\nThank you for investing with Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_investment_paid_email(user, investment_amount, profit, plan_name):
    subject = f"💰 Investment Profit Paid - ${profit:,.2f} credited!"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour investment profit has been paid!\n\nInvestment: {plan_name}\nOriginal Amount: ${investment_amount:,.2f}\nProfit Earned: ${profit:,.2f}\nTotal Received: ${investment_amount + profit:,.2f}\n\nThank you for choosing Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

def send_transaction_confirmation_email(user, transaction_type, amount, description, new_balance):
    subject = f"💰 Transaction Confirmation - ${amount:,.2f} {transaction_type.capitalize()}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nA {transaction_type} transaction of ${amount:,.2f} has been completed on your account.\n\nDescription: {description}\nNew Balance: ${new_balance:,.2f}\n\nThank you for using Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{subject}</title></head>
<body style="font-family: Arial, sans-serif;">
<div style="max-width: 600px; margin: 0 auto; padding: 20px;">
<div style="background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
<h2>💰 Transaction Confirmation</h2>
</div>
<div style="padding: 20px; background: #f9fafb;">
<p>Dear <strong>{html.escape(user.get('full_name', user['username']))}</strong>,</p>
<p>A <strong>{transaction_type}</strong> transaction of <strong>${amount:,.2f}</strong> has been completed on your account.</p>
<p><strong>Description:</strong> {html.escape(description)}</p>
<p><strong>New Balance:</strong> ${new_balance:,.2f}</p>
<p>Thank you for using Veloxtrades!</p>
</div>
<div style="text-align: center; padding: 20px; font-size: 12px; color: #6b7280;">
<p>© 2025 Veloxtrades. All rights reserved.</p>
</div>
</div>
</body>
</html>
"""
    return send_email(user['email'], subject, body, html_body)

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Investment Plans
INVESTMENT_PLANS = {
    'standard': {'name': 'Standard Plan', 'roi': 8, 'duration_hours': 20, 'min_deposit': 50, 'max_deposit': 999},
    'advanced': {'name': 'Advanced Plan', 'roi': 18, 'duration_hours': 48, 'min_deposit': 1000, 'max_deposit': 5000},
    'professional': {'name': 'Professional Plan', 'roi': 35, 'duration_hours': 96, 'min_deposit': 5001, 'max_deposit': 10000},
    'classic': {'name': 'Classic Plan', 'roi': 50, 'duration_hours': 144, 'min_deposit': 10001, 'max_deposit': float('inf')}
}

def utc_now():
    return datetime.now(timezone.utc)

# MongoDB Connection with retry logic
def get_db_connection():
    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
            # Test connection
            client.admin.command('ping')
            db = client['veloxtrades_db']
            return client, db
        except Exception as e:
            logger.error(f"MongoDB connection attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

try:
    client, db = get_db_connection()
    users_collection = db['users']
    investments_collection = db['investments']
    transactions_collection = db['transactions']
    deposits_collection = db['deposits']
    withdrawals_collection = db['withdrawals']
    notifications_collection = db['notifications']
    payments_collection = db['payments']
    admin_logs_collection = db['admin_logs']
    logger.info("✅ MongoDB Connected Successfully!")
except Exception as e:
    logger.error(f"❌ MongoDB Connection Error: {e}")
    # Don't crash, but log error
    client = None
    db = None
    users_collection = None
    investments_collection = None
    transactions_collection = None
    deposits_collection = None
    withdrawals_collection = None
    notifications_collection = None
    payments_collection = None
    admin_logs_collection = None

# ==================== HELPER FUNCTIONS ====================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(hashed_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_jwt_token(user_id, username, is_admin=False):
    payload = {
        'user_id': str(user_id), 'username': username, 'is_admin': is_admin,
        'exp': datetime.now(timezone.utc) + timedelta(days=app.config['JWT_EXPIRATION_DAYS']),
        'iat': datetime.now(timezone.utc)
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def verify_jwt_token(token):
    try:
        return jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
    except jwt.ExpiredSignatureError:
        logger.warning("⚠️ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"⚠️ Invalid token: {e}")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Token verification error: {e}")
        return None

def get_user_from_request():
    """Improved user extraction with better error handling"""
    token = None
    
    # Try to get token from cookies (multiple names)
    token = request.cookies.get('veloxtrades_token')
    if not token:
        token = request.cookies.get('elite_token')
    
    # Try Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
    
    if not token:
        logger.debug("No token found in request")
        return None
    
    # Verify token
    payload = verify_jwt_token(token)
    if not payload:
        logger.debug("Invalid token payload")
        return None
    
    try:
        # Check if database is connected
        if not db or not users_collection:
            logger.error("Database not connected")
            return None
            
        user = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
        if not user:
            logger.debug(f"User not found for ID: {payload['user_id']}")
            return None
            
        return user
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_user_from_request()
        if not user:
            logger.warning("Admin access denied: No user found")
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        if not user.get('is_admin', False):
            logger.warning(f"Admin access denied: User {user.get('username')} is not admin")
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def create_notification(user_id, title, message, type='info'):
    try:
        safe_message = html.escape(message)
        return notifications_collection.insert_one({
            'user_id': str(user_id), 'title': title, 'message': safe_message,
            'type': type, 'read': False, 'created_at': datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Failed to create notification: {e}")
        return None

def log_admin_action(admin_id, action, details):
    try:
        admin_logs_collection.insert_one({
            'admin_id': str(admin_id), 'action': action, 'details': details,
            'ip_address': request.remote_addr, 'created_at': datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")

# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    """Process investment profits with batch processing"""
    if not db:
        logger.error("Database not connected, skipping profit processing")
        return
    
    try:
        logger.info("🔄 Processing investment profits...")
        
        cursor = investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        }).batch_size(100)
        
        processed_count = 0
        error_count = 0
        
        for investment in cursor:
            try:
                user_id = investment['user_id']
                amount = investment['amount']
                expected_profit = investment.get('expected_profit', 0)
                
                result = users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.balance': expected_profit, 'wallet.total_profit': expected_profit}}
                )
                
                if result.modified_count > 0:
                    investments_collection.update_one(
                        {'_id': investment['_id']},
                        {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}}
                    )
                    
                    transactions_collection.insert_one({
                        'user_id': user_id, 'type': 'profit', 'amount': expected_profit,
                        'status': 'completed', 'description': f'Profit from {investment.get("plan_name", "Investment")}',
                        'investment_id': str(investment['_id']), 'created_at': datetime.now(timezone.utc)
                    })
                    
                    create_notification(user_id, 'Investment Completed! 🎉',
                        f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!', 'success')
                    
                    user = users_collection.find_one({'_id': ObjectId(user_id)})
                    if user:
                        send_investment_completed_email(user, amount, investment.get("plan_name", "Investment"), expected_profit)
                    
                    processed_count += 1
                    logger.info(f"✅ Processed profit for investment {investment['_id']}")
                else:
                    logger.warning(f"⚠️ User not found for investment {investment['_id']}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Error processing investment {investment.get('_id', 'unknown')}: {e}")
                continue
        
        logger.info(f"✅ Profit processing completed: {processed_count} processed, {error_count} errors")
        
    except Exception as e:
        logger.error(f"❌ Error in profit processing: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=process_investment_profits, trigger="interval", hours=1, id="profit_processor", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())
logger.info("✅ Auto-profit scheduler started")

# ==================== INPUT VALIDATION FUNCTIONS ====================
def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    return len(password) >= 6

def validate_amount(amount, min_amount=0):
    try:
        amount = float(amount)
        return amount >= min_amount and amount <= 1000000
    except (ValueError, TypeError):
        return False

# ==================== AUTHENTICATION API ====================
@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip().lower()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')

        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        if not validate_email(email):
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400
        
        if not validate_password(password):
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        
        if len(username) < 3 or len(username) > 30:
            return jsonify({'success': False, 'message': 'Username must be 3-30 characters'}), 400

        if users_collection.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        if users_collection.find_one({'username': username}):
            return jsonify({'success': False, 'message': 'Username already taken'}), 400

        referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))
        wallet = {'balance': 0.00, 'total_deposited': 0.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00}

        user_data = {
            'full_name': full_name, 'email': email, 'username': username, 'password': hash_password(password),
            'phone': data.get('phone', ''), 'country': data.get('country', ''), 'wallet': wallet,
            'is_admin': False, 'is_verified': False, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': referral_code, 'referred_by': data.get('referral_code', '').upper(),
            'referrals': [], 'kyc_status': 'pending'
        }

        result = users_collection.insert_one(user_data)
        create_notification(result.inserted_id, 'Welcome to Veloxtrades!', 'Thank you for joining. Start your investment journey today.', 'success')
        response = jsonify({'success': True, 'message': 'Registration successful! You can now login.'})
        return add_cors_headers(response), 201
    except Exception as e:
        logger.error(f"❌ Registration error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def auth_register():
    return register()

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No credentials provided'}), 400
            
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        if not username_or_email or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400

        user = users_collection.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})

        if not user or not verify_password(user['password'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account has been suspended'}), 403

        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))
        users_collection.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})

        user_data = {
            'id': str(user['_id']), 'username': user['username'], 'full_name': user.get('full_name', ''),
            'email': user['email'], 'balance': user.get('wallet', {}).get('balance', 0.00),
            'is_admin': user.get('is_admin', False)
        }

        response = make_response(jsonify({'success': True, 'message': 'Login successful!', 'data': {'token': token, 'user': user_data}}))
        
        # Set cookies with proper configuration
        response.set_cookie('veloxtrades_token', value=token, httponly=True, secure=True, samesite='Lax', 
                           max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        response.set_cookie('elite_token', value=token, httponly=True, secure=True, samesite='Lax', 
                           max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        
        return add_cors_headers(response), 200
    except Exception as e:
        logger.error(f"❌ Login error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Login failed'}), 500

@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        return handle_preflight()
    response = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/', httponly=True, secure=True, samesite='Lax')
    response.set_cookie('elite_token', '', expires=0, path='/', httponly=True, secure=True, samesite='Lax')
    return add_cors_headers(response)

@app.route('/api/auth/profile', methods=['GET', 'OPTIONS'])
def get_profile():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    user_data = {
        'id': str(user['_id']), 'full_name': user.get('full_name', ''), 'username': user.get('username', ''),
        'email': user.get('email', ''), 'phone': user.get('phone', ''), 'country': user.get('country', ''),
        'wallet': user.get('wallet', {'balance': 0.00}), 'is_admin': user.get('is_admin', False),
        'kyc_status': user.get('kyc_status', 'pending'), 'is_verified': user.get('is_verified', False),
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None
    }
    response = jsonify({'success': True, 'data': {'user': user_data}})
    return add_cors_headers(response)

@app.route('/api/verify-token', methods=['GET', 'OPTIONS'])
def verify_token():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
    response = jsonify({'success': True, 'message': 'Token is valid', 'user': {'id': str(user['_id']), 'username': user['username'], 'email': user['email'], 'is_admin': user.get('is_admin', False)}})
    return add_cors_headers(response)

# ==================== USER DASHBOARD API ====================
@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def get_dashboard():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        active_investments = list(investments_collection.find({'user_id': str(user['_id']), 'status': 'active'}))
        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)
        recent_transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).limit(10))
        for tx in recent_transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()
        unread_notifications = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
        dashboard_data = {
            'wallet': user.get('wallet', {'balance': 0.00}),
            'investments': {'total_active': total_active, 'total_profit': user.get('wallet', {}).get('total_profit', 0),
                'pending_profit': pending_profit, 'count': len(active_investments),
                'active_investments': [{'id': str(inv['_id']), 'amount': inv.get('amount', 0), 'plan_name': inv.get('plan_name', 'Unknown'),
                    'expected_profit': inv.get('expected_profit', 0), 'end_date': inv.get('end_date').isoformat() if inv.get('end_date') else None} for inv in active_investments]},
            'recent_transactions': recent_transactions, 'notification_count': unread_notifications
        }
        response = jsonify({'success': True, 'data': dashboard_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"❌ Dashboard error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load dashboard'}), 500

# ==================== TRANSACTIONS API ====================
@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        all_transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        for tx in all_transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx and isinstance(tx['created_at'], datetime):
                tx['created_at'] = tx['created_at'].isoformat()
        response = jsonify({'success': True, 'data': {'transactions': all_transactions}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Transactions error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load transactions'}), 500

# ==================== INVESTMENTS API ====================
@app.route('/api/investments', methods=['GET', 'OPTIONS'])
def get_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        investments = list(investments_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if 'start_date' in inv and isinstance(inv['start_date'], datetime):
                inv['start_date'] = inv['start_date'].isoformat()
            if 'end_date' in inv and isinstance(inv['end_date'], datetime):
                inv['end_date'] = inv['end_date'].isoformat()
        response = jsonify({'success': True, 'data': {'investments': investments}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Investments error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load investments'}), 500

# ==================== DEPOSIT API ====================
@app.route('/api/deposit', methods=['POST', 'OPTIONS'])
def create_deposit():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        crypto = data.get('crypto', '')
        
        if not validate_amount(amount, 10):
            return jsonify({'success': False, 'message': 'Invalid amount. Minimum deposit is $10'}), 400
        
        if not crypto or crypto not in ['btc', 'eth', 'usdt', 'usdc']:
            return jsonify({'success': False, 'message': 'Invalid cryptocurrency'}), 400
        
        deposit = {
            'user_id': str(user['_id']), 'amount': amount, 'crypto': crypto,
            'wallet_address': data.get('wallet_address', ''), 'transaction_id': data.get('transaction_id', ''),
            'status': 'pending', 'created_at': datetime.now(timezone.utc)
        }
        result = deposits_collection.insert_one(deposit)
        admin_logs_collection.insert_one({'type': 'deposit_request', 'user_id': str(user['_id']), 'username': user['username'],
            'amount': deposit['amount'], 'crypto': deposit['crypto'], 'deposit_id': str(result.inserted_id), 'created_at': datetime.now(timezone.utc)})
        transactions_collection.insert_one({'user_id': str(user['_id']), 'type': 'deposit', 'amount': deposit['amount'],
            'status': 'pending', 'description': f'Deposit request of ${deposit["amount"]} via {deposit["crypto"]} - Pending admin approval', 'created_at': datetime.now(timezone.utc)})
        response = jsonify({'success': True, 'message': 'Deposit request submitted successfully. Awaiting admin approval.',
            'data': {'deposit_id': str(result.inserted_id), 'status': 'pending'}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"❌ Deposit creation error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== NOTIFICATIONS API ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        notifications = list(notifications_collection.find(
            {'user_id': str(user['_id'])}
        ).sort('created_at', -1))
        
        for n in notifications:
            n['_id'] = str(n['_id'])
            if 'created_at' in n and isinstance(n['created_at'], datetime):
                n['created_at'] = n['created_at'].isoformat()
        
        unread_count = notifications_collection.count_documents({
            'user_id': str(user['_id']),
            'read': False
        })
        
        response = jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'unread_count': unread_count
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/<notification_id>/read', methods=['PUT', 'OPTIONS'])
def mark_notification_read_route(notification_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        result = notifications_collection.update_one(
            {'_id': ObjectId(notification_id), 'user_id': str(user['_id'])},
            {'$set': {'read': True}}
        )
        
        if result.modified_count > 0:
            response = jsonify({'success': True, 'message': 'Notification marked as read'})
            return add_cors_headers(response)
        else:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== WITHDRAWAL API ====================
@app.route('/api/withdrawals', methods=['POST', 'OPTIONS'])
def create_withdrawal():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        currency = data.get('currency', '')
        wallet_address = data.get('wallet_address', '')
        
        if not validate_amount(amount, 50):
            return jsonify({'success': False, 'message': 'Invalid amount. Minimum withdrawal is $50'}), 400
        
        if not wallet_address or len(wallet_address) < 10:
            return jsonify({'success': False, 'message': 'Invalid wallet address'}), 400
        
        current_balance = user.get('wallet', {}).get('balance', 0)
        if amount > current_balance:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        withdrawal = {
            'user_id': str(user['_id']), 'amount': amount, 'currency': currency,
            'wallet_address': wallet_address, 'status': 'pending', 'created_at': datetime.now(timezone.utc)
        }
        result = withdrawals_collection.insert_one(withdrawal)
        transactions_collection.insert_one({'user_id': str(user['_id']), 'type': 'withdrawal', 'amount': amount,
            'status': 'pending', 'description': f'Withdrawal request of ${amount} to {currency} - Pending admin approval', 'created_at': datetime.now(timezone.utc)})
        admin_logs_collection.insert_one({'type': 'withdrawal_request', 'user_id': str(user['_id']), 'username': user['username'],
            'amount': amount, 'currency': currency, 'wallet_address': wallet_address, 'withdrawal_id': str(result.inserted_id), 'created_at': datetime.now(timezone.utc)})
        response = jsonify({'success': True, 'message': 'Withdrawal request submitted successfully. Awaiting admin approval.',
            'data': {'withdrawal_id': str(result.inserted_id), 'status': 'pending'}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"❌ Withdrawal creation error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== INVEST API ====================
@app.route('/api/invest', methods=['POST', 'OPTIONS'])
def create_investment():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        plan_type = data.get('plan_type', '')
        amount = float(data.get('amount', 0))
        plan = INVESTMENT_PLANS.get(plan_type)
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400
        
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum investment is ${plan["min_deposit"]}'}), 400
        if amount > plan['max_deposit'] and plan['max_deposit'] != float('inf'):
            return jsonify({'success': False, 'message': f'Maximum investment is ${plan["max_deposit"]}'}), 400
        
        current_balance = user.get('wallet', {}).get('balance', 0)
        if amount > current_balance:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        expected_profit = amount * plan['roi'] / 100
        end_date = datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])
        
        result = users_collection.update_one(
            {'_id': user['_id'], 'wallet.balance': {'$gte': amount}},
            {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}}
        )
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'message': 'Insufficient balance or transaction failed'}), 400
        
        investment = {
            'user_id': str(user['_id']), 'plan_name': plan['name'], 'plan_type': plan_type, 'amount': amount,
            'expected_profit': expected_profit, 'roi': plan['roi'], 'duration_hours': plan['duration_hours'],
            'status': 'active', 'start_date': datetime.now(timezone.utc), 'end_date': end_date, 'created_at': datetime.now(timezone.utc)
        }
        inv_result = investments_collection.insert_one(investment)
        
        transactions_collection.insert_one({'user_id': str(user['_id']), 'type': 'investment', 'amount': amount,
            'status': 'completed', 'description': f'Investment in {plan["name"]}', 'investment_id': str(inv_result.inserted_id), 'created_at': datetime.now(timezone.utc)})
        create_notification(user['_id'], 'Investment Created! 🚀', f'Your investment of ${amount:,.2f} in {plan["name"]} has been started. Expected profit: ${expected_profit:,.2f}', 'success')
        send_investment_created_email(user, amount, plan['name'], expected_profit)
        
        updated_user = users_collection.find_one({'_id': user['_id']})
        new_balance = updated_user.get('wallet', {}).get('balance', 0)
        response = jsonify({'success': True, 'message': 'Investment created successfully',
            'data': {'investment_id': str(inv_result.inserted_id), 'new_balance': new_balance, 'expected_profit': expected_profit}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"❌ Investment creation error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN API ENDPOINTS ====================

@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        # Safely get counts with error handling
        total_users = 0
        total_deposit_amount = 0
        total_withdrawal_amount = 0
        active_investments = 0
        pending_deposits = 0
        pending_withdrawals = 0
        banned_users = 0
        
        # Users collection
        if users_collection:
            total_users = users_collection.count_documents({})
            banned_users = users_collection.count_documents({'is_banned': True})
        
        # Deposits collection
        if deposits_collection:
            try:
                approved_deposits = list(deposits_collection.find({'status': 'approved'}))
                total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
                pending_deposits = deposits_collection.count_documents({'status': 'pending'})
            except Exception as e:
                logger.error(f"Error fetching deposits: {e}")
        
        # Withdrawals collection
        if withdrawals_collection:
            try:
                approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
                total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
                pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
            except Exception as e:
                logger.error(f"Error fetching withdrawals: {e}")
        
        # Investments collection
        if investments_collection:
            try:
                active_investments = investments_collection.count_documents({'status': 'active'})
            except Exception as e:
                logger.error(f"Error fetching investments: {e}")
        
        response = jsonify({
            'success': True, 
            'data': {
                'total_users': total_users,
                'total_deposit_amount': total_deposit_amount,
                'total_withdrawal_amount': total_withdrawal_amount,
                'active_investments': active_investments,
                'pending_deposits': pending_deposits,
                'pending_withdrawals': pending_withdrawals,
                'banned_users': banned_users
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        # Return empty stats instead of error to prevent dashboard failure
        return jsonify({
            'success': True, 
            'data': {
                'total_users': 0,
                'total_deposit_amount': 0,
                'total_withdrawal_amount': 0,
                'active_investments': 0,
                'pending_deposits': 0,
                'pending_withdrawals': 0,
                'banned_users': 0,
                'error': str(e)
            }
        }), 200

@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        tx_type = request.args.get('type', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if tx_type != 'all':
            query['type'] = tx_type
        
        # Check if transactions collection exists
        if not transactions_collection:
            return jsonify({
                'success': True,
                'data': {
                    'transactions': [],
                    'total': 0,
                    'page': page,
                    'pages': 1
                }
            }), 200
        
        total = transactions_collection.count_documents(query)
        transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_transactions = []
        for tx in transactions:
            try:
                tx['_id'] = str(tx['_id'])
                if 'created_at' in tx and isinstance(tx['created_at'], datetime):
                    tx['created_at'] = tx['created_at'].isoformat()
                
                # Get user info safely
                if users_collection and 'user_id' in tx:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(tx['user_id'])})
                        tx['user'] = {
                            'username': user.get('username', 'Unknown') if user else 'Unknown',
                            'email': user.get('email', '') if user else ''
                        }
                    except:
                        tx['user'] = {'username': 'Unknown', 'email': ''}
                else:
                    tx['user'] = {'username': 'Unknown', 'email': ''}
                result_transactions.append(tx)
            except Exception as e:
                logger.error(f"Error processing transaction: {e}")
                continue
        
        response = jsonify({
            'success': True,
            'data': {
                'transactions': result_transactions,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get admin transactions error: {e}", exc_info=True)
        return jsonify({
            'success': True,
            'data': {
                'transactions': [],
                'total': 0,
                'page': 1,
                'pages': 1,
                'error': str(e)
            }
        }), 200

@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        # CRITICAL: Check database connection first
        if not users_collection:
            logger.error("Users collection not available")
            return jsonify({
                'success': False,
                'message': 'Database connection error',
                'data': {
                    'users': [],
                    'total': 0,
                    'page': 1,
                    'pages': 1
                }
            }), 500
        
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        search = request.args.get('search', '')
        skip = (page - 1) * limit
        
        query = {}
        if search:
            query['$or'] = [
                {'username': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'full_name': {'$regex': search, '$options': 'i'}}
            ]
        
        # Get total count
        total = users_collection.count_documents(query)
        logger.info(f"Total users found: {total} with query: {query}")
        
        # Get users with pagination
        users = list(users_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        # Format users for response
        formatted_users = []
        for user in users:
            try:
                user_data = {
                    '_id': str(user['_id']),
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'full_name': user.get('full_name', ''),
                    'phone': user.get('phone', ''),
                    'country': user.get('country', ''),
                    'wallet': user.get('wallet', {'balance': 0}),
                    'is_admin': user.get('is_admin', False),
                    'is_banned': user.get('is_banned', False),
                    'is_verified': user.get('is_verified', False),
                    'kyc_status': user.get('kyc_status', 'pending'),
                    'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
                    'last_login': user.get('last_login').isoformat() if user.get('last_login') else None
                }
                formatted_users.append(user_data)
            except Exception as e:
                logger.error(f"Error formatting user: {e}")
                continue
        
        # Calculate total pages
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        response_data = {
            'success': True,
            'data': {
                'users': formatted_users,
                'total': total,
                'page': page,
                'pages': total_pages,
                'limit': limit
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get users error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'message': str(e),
            'data': {
                'users': [],
                'total': 0,
                'page': 1,
                'pages': 1
            }
        }), 500

@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_deposits():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        if not deposits_collection:
            return jsonify({
                'success': True,
                'data': {
                    'deposits': [],
                    'total': 0,
                    'page': page,
                    'pages': 1
                }
            }), 200
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = deposits_collection.count_documents(query)
        deposits = list(deposits_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_deposits = []
        for deposit in deposits:
            try:
                deposit['_id'] = str(deposit['_id'])
                if 'created_at' in deposit and isinstance(deposit['created_at'], datetime):
                    deposit['created_at'] = deposit['created_at'].isoformat()
                
                if users_collection and 'user_id' in deposit:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
                        deposit['username'] = user.get('username', 'Unknown') if user else 'Unknown'
                    except:
                        deposit['username'] = 'Unknown'
                else:
                    deposit['username'] = 'Unknown'
                result_deposits.append(deposit)
            except Exception as e:
                logger.error(f"Error processing deposit: {e}")
                continue
        
        response = jsonify({
            'success': True, 
            'data': {
                'deposits': result_deposits,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get deposits error: {e}", exc_info=True)
        return jsonify({
            'success': True,
            'data': {
                'deposits': [],
                'total': 0,
                'page': 1,
                'pages': 1
            }
        }), 200

@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_withdrawals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        if not withdrawals_collection:
            return jsonify({
                'success': True,
                'data': {
                    'withdrawals': [],
                    'total': 0,
                    'page': page,
                    'pages': 1
                }
            }), 200
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = withdrawals_collection.count_documents(query)
        withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_withdrawals = []
        for withdrawal in withdrawals:
            try:
                withdrawal['_id'] = str(withdrawal['_id'])
                if 'created_at' in withdrawal and isinstance(withdrawal['created_at'], datetime):
                    withdrawal['created_at'] = withdrawal['created_at'].isoformat()
                
                if users_collection and 'user_id' in withdrawal:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
                        withdrawal['username'] = user.get('username', 'Unknown') if user else 'Unknown'
                    except:
                        withdrawal['username'] = 'Unknown'
                else:
                    withdrawal['username'] = 'Unknown'
                result_withdrawals.append(withdrawal)
            except Exception as e:
                logger.error(f"Error processing withdrawal: {e}")
                continue
        
        response = jsonify({
            'success': True, 
            'data': {
                'withdrawals': result_withdrawals,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}", exc_info=True)
        return jsonify({
            'success': True,
            'data': {
                'withdrawals': [],
                'total': 0,
                'page': 1,
                'pages': 1
            }
        }), 200

@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        if not investments_collection:
            return jsonify({
                'success': True,
                'data': {
                    'investments': [],
                    'total': 0,
                    'page': page,
                    'pages': 1
                }
            }), 200
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = investments_collection.count_documents(query)
        investments = list(investments_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_investments = []
        for inv in investments:
            try:
                inv['_id'] = str(inv['_id'])
                if 'start_date' in inv and isinstance(inv['start_date'], datetime):
                    inv['start_date'] = inv['start_date'].isoformat()
                if 'end_date' in inv and isinstance(inv['end_date'], datetime):
                    inv['end_date'] = inv['end_date'].isoformat()
                
                if users_collection and 'user_id' in inv:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
                        inv['username'] = user.get('username', 'Unknown') if user else 'Unknown'
                    except:
                        inv['username'] = 'Unknown'
                else:
                    inv['username'] = 'Unknown'
                result_investments.append(inv)
            except Exception as e:
                logger.error(f"Error processing investment: {e}")
                continue
        
        response = jsonify({
            'success': True, 
            'data': {
                'investments': result_investments,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get investments error: {e}", exc_info=True)
        return jsonify({
            'success': True,
            'data': {
                'investments': [],
                'total': 0,
                'page': 1,
                'pages': 1
            }
        }), 200

@app.route('/api/admin/deposits/<deposit_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_deposit(deposit_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        action = data.get('action')
        send_email_notification = data.get('send_email', True)
        
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        if deposit['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Deposit already processed'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        
        if action == 'approve':
            users_collection.update_one(
                {'_id': ObjectId(deposit['user_id'])},
                {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}}
            )
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'approved', 'processed_at': datetime.now(timezone.utc)}})
            transactions_collection.insert_one({
                'user_id': deposit['user_id'], 'type': 'deposit', 'amount': deposit['amount'],
                'status': 'completed', 'description': f'Deposit of ${deposit["amount"]} via {deposit["crypto"]} approved by admin',
                'created_at': datetime.now(timezone.utc)
            })
            create_notification(deposit['user_id'], 'Deposit Approved! ✅', f'Your deposit of ${deposit["amount"]:,.2f} via {deposit["crypto"]} has been approved and added to your wallet.', 'success')
            if send_email_notification and user:
                send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_id', ''))
            message = 'Deposit approved successfully'
        elif action == 'reject':
            reason = data.get('reason', 'Not specified')
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'processed_at': datetime.now(timezone.utc)}})
            transactions_collection.insert_one({
                'user_id': deposit['user_id'], 'type': 'deposit', 'amount': deposit['amount'],
                'status': 'failed', 'description': f'Deposit of ${deposit["amount"]} rejected: {reason}',
                'created_at': datetime.now(timezone.utc)
            })
            create_notification(deposit['user_id'], 'Deposit Rejected ❌', f'Your deposit of ${deposit["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            if send_email_notification and user:
                send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], reason)
            message = 'Deposit rejected'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], f'process_deposit_{action}', f'Deposit {deposit_id} for user {deposit["user_id"]} was {action}ed')
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals/<withdrawal_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_withdrawal(withdrawal_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        action = data.get('action')
        send_email_notification = data.get('send_email', True)
        
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Withdrawal already processed'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        
        if action == 'approve':
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {'$inc': {'wallet.balance': -withdrawal['amount'], 'wallet.total_withdrawn': withdrawal['amount']}}
            )
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved', 'processed_at': datetime.now(timezone.utc), 'transaction_id': data.get('transaction_id', '')}})
            transactions_collection.update_one(
                {'user_id': withdrawal['user_id'], 'type': 'withdrawal', 'status': 'pending'},
                {'$set': {'status': 'completed', 'description': f'Withdrawal of ${withdrawal["amount"]} approved and sent'}},
                sort=[('created_at', -1)]
            )
            create_notification(withdrawal['user_id'], 'Withdrawal Approved! ✅', f'Your withdrawal of ${withdrawal["amount"]:,.2f} has been approved and sent to your wallet.', 'success')
            if send_email_notification and user:
                send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
            message = 'Withdrawal approved successfully'
        elif action == 'reject':
            reason = data.get('reason', 'Not specified')
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'processed_at': datetime.now(timezone.utc)}})
            transactions_collection.update_one(
                {'user_id': withdrawal['user_id'], 'type': 'withdrawal', 'status': 'pending'},
                {'$set': {'status': 'failed', 'description': f'Withdrawal of ${withdrawal["amount"]} rejected: {reason}'}},
                sort=[('created_at', -1)]
            )
            create_notification(withdrawal['user_id'], 'Withdrawal Rejected ❌', f'Your withdrawal of ${withdrawal["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            if send_email_notification and user:
                send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
            message = 'Withdrawal rejected'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN SEND EMAIL ENDPOINT ====================
@app.route('/api/admin/send-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_send_email():
    """Send manual email to a specific user"""
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        subject = data.get('subject')
        message = data.get('message')
        email_type = data.get('type', 'info')
        
        if not user_id or not subject or not message:
            return jsonify({'success': False, 'message': 'User ID, subject, and message are required'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        safe_message = html.escape(message)
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{html.escape(subject)}</title>
<style>
body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
.content {{ padding: 20px; background: #f9fafb; }}
.message-box {{ background: white; padding: 20px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #10b981; }}
.footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
.button {{ background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; }}
</style>
</head>
<body>
<div class="container">
<div class="header"><h2>📧 {html.escape(subject)}</h2></div>
<div class="content">
<p>Dear <strong>{html.escape(user.get('full_name', user['username']))}</strong>,</p>
<div class="message-box">{safe_message.replace(chr(10), '<br>')}</div>
<a href="https://www.veloxtrades.com.ng/dashboard.html" class="button">View Dashboard</a>
</div>
<div class="footer"><p>© 2025 Veloxtrades. All rights reserved.</p></div>
</div>
</body>
</html>
"""
        
        email_sent = send_email(user['email'], subject, message, html_body)
        
        if email_sent:
            create_notification(user_id, subject, message, email_type)
            admin_user = get_user_from_request()
            if admin_user:
                log_admin_action(admin_user['_id'], 'send_manual_email', f'Sent email to {user["username"]}: {subject}')
            response = jsonify({'success': True, 'message': f'Email sent to {user["email"]}'})
        else:
            response = jsonify({'success': False, 'message': 'Failed to send email. Please check email configuration.'})
        
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Send email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast_email():
    """Send broadcast email to multiple users"""
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        recipients_type = data.get('recipients', 'all')
        subject = data.get('subject')
        message = data.get('message')
        email_type = data.get('type', 'info')
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message are required'}), 400
        
        query = {}
        if recipients_type == 'active':
            query = {'is_banned': False}
        elif recipients_type == 'depositors':
            query = {'wallet.total_deposited': {'$gt': 0}}
        elif recipients_type == 'investors':
            if investments_collection:
                active_investors = investments_collection.distinct('user_id', {'status': 'active'})
                if active_investors:
                    query = {'_id': {'$in': [ObjectId(uid) for uid in active_investors if uid]}}
                else:
                    query = {'_id': {'$in': []}}
            else:
                query = {'_id': {'$in': []}}
        
        users = list(users_collection.find(query)) if users_collection else []
        
        safe_message = html.escape(message)
        
        sent_count = 0
        for user in users:
            html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{html.escape(subject)}</title>
<style>
body {{ font-family: Arial, sans-serif; }}
.container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
.content {{ padding: 20px; background: #f9fafb; }}
.message-box {{ background: white; padding: 20px; border-radius: 8px; margin: 15px 0; }}
.footer {{ text-align: center; padding: 20px; font-size: 12px; }}
.button {{ background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block; }}
</style>
</head>
<body>
<div class="container">
<div class="header"><h2>📢 {html.escape(subject)}</h2></div>
<div class="content">
<p>Dear <strong>{html.escape(user.get('full_name', user['username']))}</strong>,</p>
<div class="message-box">{safe_message.replace(chr(10), '<br>')}</div>
<a href="https://www.veloxtrades.com.ng/dashboard.html" class="button">View Dashboard</a>
</div>
<div class="footer"><p>© 2025 Veloxtrades</p></div>
</div>
</body>
</html>
"""
            if send_email(user['email'], subject, message, html_body):
                create_notification(user['_id'], subject, message, email_type)
                sent_count += 1
        
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], 'broadcast_email', f'Sent broadcast to {sent_count} users: {subject}')
        
        response = jsonify({'success': True, 'message': f'Broadcast sent to {sent_count} users', 'data': {'count': sent_count}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Admin adjustment')
        
        if not validate_amount(amount, -1000000) or amount > 1000000:
            return jsonify({'success': False, 'message': 'Invalid amount. Amount must be between -1,000,000 and 1,000,000'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        current_balance = user.get('wallet', {}).get('balance', 0)
        new_balance = current_balance + amount
        
        result = users_collection.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'message': 'Failed to update balance'}), 500
        
        transaction_type = 'adjustment'
        if amount > 0:
            transaction_type = 'credit'
        elif amount < 0:
            transaction_type = 'debit'
        
        transactions_collection.insert_one({
            'user_id': str(user_id), 'type': transaction_type, 'amount': abs(amount),
            'status': 'completed', 'description': f'Balance adjustment by admin: {reason} (${amount:+,.2f})',
            'created_at': datetime.now(timezone.utc)
        })
        
        create_notification(user_id, 'Balance Adjusted', f'Your balance has been adjusted by ${amount:+,.2f}. Reason: {reason}', 'info')
        
        try:
            send_transaction_confirmation_email(user, transaction_type, abs(amount), reason, new_balance)
        except Exception as email_error:
            logger.error(f"Failed to send balance adjustment email: {email_error}")
        
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], 'adjust_balance', f'Adjusted balance for user {user["username"]} by ${amount}')
        
        response = jsonify({'success': True, 'message': f'Balance adjusted by ${amount:+,.2f}', 'data': {'new_balance': new_balance}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Balance adjustment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/toggle-ban', methods=['POST', 'OPTIONS'])
@require_admin
def admin_toggle_ban(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        new_ban_status = not user.get('is_banned', False)
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status}})
        action = 'banned' if new_ban_status else 'unbanned'
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], f'{action}_user', f'User {user["username"]} was {action}')
        create_notification(user_id, f'Account {action.capitalize()}', f'Your account has been {action}.', 'warning' if new_ban_status else 'success')
        response = jsonify({'success': True, 'message': f'User {action} successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Toggle ban error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['DELETE', 'OPTIONS'])
@require_admin
def admin_delete_user(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        username = user.get('username', 'Unknown')
        
        if investments_collection:
            investments_collection.delete_many({'user_id': str(user_id)})
        if transactions_collection:
            transactions_collection.delete_many({'user_id': str(user_id)})
        if deposits_collection:
            deposits_collection.delete_many({'user_id': str(user_id)})
        if withdrawals_collection:
            withdrawals_collection.delete_many({'user_id': str(user_id)})
        if notifications_collection:
            notifications_collection.delete_many({'user_id': str(user_id)})
        if users_collection:
            users_collection.delete_one({'_id': ObjectId(user_id)})
        
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], 'delete_user', f'Deleted user: {username}')
        
        response = jsonify({'success': True, 'message': f'User {username} permanently deleted'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== DEBUG ADMIN ENDPOINT ====================
@app.route('/api/admin/debug-users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_debug_users():
    """Debug endpoint to check what's wrong with user fetching"""
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        # Check database connection
        db_status = "connected" if db else "disconnected"
        
        # Check if users_collection exists
        collection_exists = users_collection is not None
        
        # Count users
        total_users = 0
        if users_collection:
            try:
                total_users = users_collection.count_documents({})
            except Exception as e:
                total_users = f"Error: {e}"
        
        # Get sample of users (first 5)
        sample_users = []
        if users_collection and total_users > 0:
            try:
                sample = list(users_collection.find({}, {'password': 0}).limit(5))
                for user in sample:
                    user['_id'] = str(user['_id'])
                    user.pop('password', None)
                    sample_users.append(user)
            except Exception as e:
                sample_users = f"Error: {e}"
        
        # Get admin user info from token
        current_user = get_user_from_request()
        admin_info = None
        if current_user:
            admin_info = {
                'id': str(current_user.get('_id')),
                'username': current_user.get('username'),
                'email': current_user.get('email'),
                'is_admin': current_user.get('is_admin', False)
            }
        
        return jsonify({
            'success': True,
            'debug_info': {
                'database_connected': db_status,
                'users_collection_exists': collection_exists,
                'total_users': total_users,
                'sample_users': sample_users,
                'current_admin': admin_info,
                'request_cookies': {k: '***HIDDEN***' if 'token' in k else v for k, v in request.cookies.items()},
                'request_headers': {k: v for k, v in request.headers.items() if k.lower() not in ['authorization', 'cookie']}
            }
        })
    except Exception as e:
        logger.error(f"Debug error: {e}", exc_info=True)
        return jsonify({
            'success': False, 
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

# ==================== ADMIN RESET ENDPOINT ====================
@app.route('/api/admin/reset-all', methods=['GET'])
def reset_all_admin():
    """Emergency reset - removes all admins and creates fresh one with password admin123"""
    secret_key = request.args.get('secret')
    if not secret_key or secret_key != ADMIN_RESET_SECRET:
        logger.warning(f"Unauthorized admin reset attempt from {request.remote_addr}")
        return jsonify({'success': False, 'message': 'Unauthorized. Secret key required.'}), 401
    
    try:
        if users_collection:
            users_collection.delete_many({'is_admin': True})
            users_collection.delete_many({'username': 'admin'})
            users_collection.delete_many({'email': 'admin@veloxtrades.ltd'})
        
        hashed_password = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        new_admin = {
            'full_name': 'System Administrator',
            'email': 'admin@veloxtrades.ltd',
            'username': 'admin',
            'password': hashed_password,
            'phone': '+1234567890',
            'country': 'USA',
            'wallet': {'balance': 100000.00, 'total_deposited': 100000.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00},
            'is_admin': True, 'is_verified': True, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': 'ADMIN2025', 'referrals': [], 'kyc_status': 'verified', 'role': 'admin'
        }
        
        result = users_collection.insert_one(new_admin)
        
        logger.info(f"Admin reset performed by {request.remote_addr}")
        
        return jsonify({
            'success': True,
            'message': '✅ Admin system completely reset!',
            'credentials': {'username': 'admin', 'password': 'admin123', 'email': 'admin@veloxtrades.ltd'},
            'admin_id': str(result.inserted_id)
        })
    except Exception as e:
        logger.error(f"Reset admin error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/check-status', methods=['GET'])
def check_admin_status():
    try:
        if not users_collection:
            return jsonify({'success': False, 'message': 'Database not connected', 'admin_exists': False}), 500
        admin_user = users_collection.find_one({'username': 'admin'})
        if not admin_user:
            return jsonify({'success': False, 'message': 'Admin user not found', 'admin_exists': False})
        return jsonify({
            'success': True, 'admin_exists': True,
            'admin_data': {
                'username': admin_user.get('username'), 'email': admin_user.get('email'),
                'is_banned': admin_user.get('is_banned', False), 'is_admin': admin_user.get('is_admin', False)
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/list-users', methods=['GET'])
def list_users():
    try:
        if not users_collection:
            return jsonify({'success': False, 'message': 'Database not connected'}), 500
        users = list(users_collection.find({}, {'password': 0}))
        for user in users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user and user['created_at']:
                user['created_at'] = user['created_at'].isoformat()
        return jsonify({'success': True, 'total_users': len(users), 'users': users})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== FRONTEND ROUTES ====================
@app.route('/')
def serve_index():
    response = jsonify({
        'success': True, 'message': 'Veloxtrades API Server',
        'frontend': FRONTEND_URL, 'backend': BACKEND_URL,
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login']
    })
    return add_cors_headers(response)

@app.route('/<path:filename>')
def serve_static_files(filename):
    try:
        response = make_response(send_from_directory(app.static_folder, filename))
        if filename.endswith('.js'):
            response.headers['Content-Type'] = 'application/javascript'
        elif filename.endswith('.css'):
            response.headers['Content-Type'] = 'text/css'
        elif filename.endswith('.html'):
            response.headers['Content-Type'] = 'text/html'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return add_cors_headers(response)
    except Exception as e:
        return jsonify({'success': False, 'message': 'File not found'}), 404

@app.route('/health', methods=['GET', 'OPTIONS'])
def simple_health_check():
    if request.method == 'OPTIONS':
        return handle_preflight()
    response = jsonify({'success': True, 'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat()})
    return add_cors_headers(response)

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    mongo_status = 'disconnected'
    try:
        if db:
            db.command('ping')
            mongo_status = 'connected'
    except:
        pass
    
    response = jsonify({
        'success': True, 'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat(),
        'mongo': mongo_status, 'email': 'configured'
    })
    return add_cors_headers(response)

# ==================== INIT DATABASE ====================
def init_database():
    try:
        if db:
            users_collection.create_index('email', unique=True)
            users_collection.create_index('username', unique=True)
            users_collection.create_index('referral_code', unique=True)
            transactions_collection.create_index('user_id')
            transactions_collection.create_index('created_at')
            deposits_collection.create_index('status')
            withdrawals_collection.create_index('status')
            investments_collection.create_index('status')
            investments_collection.create_index('end_date')
            logger.info("✅ Database indexes created")
            total_users = users_collection.count_documents({})
            logger.info(f"👥 Total users: {total_users}")
            logger.info("ℹ️ Use /api/admin/reset-all?secret=YOUR_SECRET to create admin account")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")

with app.app_context():
    init_database()

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({'success': False, 'message': 'Internal server error'}), 500

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 VELOXTRADES API SERVER - PRODUCTION READY")
    print("=" * 70)
    print("📊 MongoDB Status: " + ("Connected" if db else "Disconnected"))
    print("📧 Email Service Configured")
    print(f"   SMTP: {EMAIL_USER}")
    print(f"   From: {EMAIL_FROM}")
    print("👑 Admin Dashboard Ready")
    print("🔄 Auto-Profit Cron: Every hour")
    print("=" * 70)
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print(f"🔧 Backend URL: {BACKEND_URL}")
    print("\n📝 TO CREATE ADMIN:")
    print(f"   Visit: {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   This will create admin with: admin / admin123")
    print("=" * 70)

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
