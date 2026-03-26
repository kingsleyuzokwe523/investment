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

# Admin reset secret
ADMIN_RESET_SECRET = os.getenv('ADMIN_RESET_SECRET', 'veloxtrades-admin-reset-2025')

# ==================== CORS CONFIGURATION ====================
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

CORS(app, 
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken", "Origin"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=86400)

# ==================== MONGO DB CONNECTION FIX ====================
# Initialize collections as None first
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

def init_mongo():
    """Initialize MongoDB connection properly"""
    global client, db, users_collection, investments_collection, transactions_collection
    global deposits_collection, withdrawals_collection, notifications_collection, payments_collection, admin_logs_collection
    
    try:
        logger.info("🔄 Connecting to MongoDB...")
        client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
        # Test connection
        client.admin.command('ping')
        db = client['veloxtrades_db']
        
        # Initialize collections (they will be created if they don't exist)
        users_collection = db['users']
        investments_collection = db['investments']
        transactions_collection = db['transactions']
        deposits_collection = db['deposits']
        withdrawals_collection = db['withdrawals']
        notifications_collection = db['notifications']
        payments_collection = db['payments']
        admin_logs_collection = db['admin_logs']
        
        # Create indexes
        users_collection.create_index('email', unique=True, sparse=True)
        users_collection.create_index('username', unique=True, sparse=True)
        users_collection.create_index('referral_code', unique=True, sparse=True)
        transactions_collection.create_index('user_id')
        transactions_collection.create_index('created_at')
        deposits_collection.create_index('status')
        withdrawals_collection.create_index('status')
        investments_collection.create_index('status')
        investments_collection.create_index('end_date')
        
        logger.info("✅ MongoDB Connected Successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB Connection Error: {e}")
        # Keep collections as None but don't crash
        return False

# Initialize MongoDB
mongo_connected = init_mongo()

@app.before_request
def before_request():
    """Check MongoDB connection before each request"""
    if not mongo_connected:
        try:
            init_mongo()
        except:
            pass

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

def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email to user with retry logic"""
    for attempt in range(max_retries):
        try:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
                logger.error(f"❌ Invalid email format: {to_email}")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['From'] = EMAIL_FROM
            msg['To'] = to_email
            msg['Subject'] = subject
            
            part1 = MIMEText(body, 'plain')
            msg.attach(part1)
            
            if html_body:
                part2 = MIMEText(html_body, 'html')
                msg.attach(part2)
            
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
            
            logger.info(f"✅ Email sent to {to_email}: {subject}")
            return True
            
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
    return send_email(user['email'], subject, body)

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

# Investment Plans
INVESTMENT_PLANS = {
    'standard': {'name': 'Standard Plan', 'roi': 8, 'duration_hours': 20, 'min_deposit': 50, 'max_deposit': 999},
    'advanced': {'name': 'Advanced Plan', 'roi': 18, 'duration_hours': 48, 'min_deposit': 1000, 'max_deposit': 5000},
    'professional': {'name': 'Professional Plan', 'roi': 35, 'duration_hours': 96, 'min_deposit': 5001, 'max_deposit': 10000},
    'classic': {'name': 'Classic Plan', 'roi': 50, 'duration_hours': 144, 'min_deposit': 10001, 'max_deposit': float('inf')}
}

def utc_now():
    return datetime.now(timezone.utc)

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
    except Exception as e:
        logger.warning(f"⚠️ Token verification error: {e}")
        return None

def get_user_from_request():
    """Extract user from token"""
    token = None
    
    # Try to get token from cookies
    token = request.cookies.get('veloxtrades_token')
    if not token:
        token = request.cookies.get('elite_token')
    
    # Try Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
    
    if not token:
        return None
    
    payload = verify_jwt_token(token)
    if not payload:
        return None
    
    try:
        # Check if users_collection is available
        if users_collection is None:
            logger.error("Users collection not available")
            return None
        
        user = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
        return user
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None

def require_admin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_user_from_request()
        if not user:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        if not user.get('is_admin', False):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def create_notification(user_id, title, message, type='info'):
    try:
        if notifications_collection is None:
            return None
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
        if admin_logs_collection is None:
            return
        admin_logs_collection.insert_one({
            'admin_id': str(admin_id), 'action': action, 'details': details,
            'ip_address': request.remote_addr, 'created_at': datetime.now(timezone.utc)
        })
    except Exception as e:
        logger.error(f"Failed to log admin action: {e}")

# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    """Process investment profits with batch processing"""
    if investments_collection is None or users_collection is None:
        logger.error("Collections not available, skipping profit processing")
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
                    
                    if transactions_collection:
                        transactions_collection.insert_one({
                            'user_id': user_id, 'type': 'profit', 'amount': expected_profit,
                            'status': 'completed', 'description': f'Profit from {investment.get("plan_name", "Investment")}',
                            'investment_id': str(investment['_id']), 'created_at': datetime.now(timezone.utc)
                        })
                    
                    create_notification(user_id, 'Investment Completed! 🎉',
                        f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!', 'success')
                    
                    processed_count += 1
                    logger.info(f"✅ Processed profit for investment {investment['_id']}")
                    
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
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
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

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
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
    response = jsonify({
        'success': True, 
        'message': 'Token is valid', 
        'user': {
            'id': str(user['_id']), 
            'username': user['username'], 
            'email': user['email'], 
            'is_admin': user.get('is_admin', False)
        }
    })
    return add_cors_headers(response)

# ==================== ADMIN API ENDPOINTS ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        total_users = 0
        total_deposit_amount = 0
        total_withdrawal_amount = 0
        active_investments = 0
        pending_deposits = 0
        pending_withdrawals = 0
        banned_users = 0
        
        # Check each collection exists before using
        if users_collection is not None:
            total_users = users_collection.count_documents({})
            banned_users = users_collection.count_documents({'is_banned': True})
        
        if deposits_collection is not None:
            try:
                approved_deposits = list(deposits_collection.find({'status': 'approved'}))
                total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
                pending_deposits = deposits_collection.count_documents({'status': 'pending'})
            except Exception as e:
                logger.error(f"Error fetching deposits: {e}")
        
        if withdrawals_collection is not None:
            try:
                approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
                total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
                pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
            except Exception as e:
                logger.error(f"Error fetching withdrawals: {e}")
        
        if investments_collection is not None:
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
        return jsonify({
            'success': True, 
            'data': {
                'total_users': 0,
                'total_deposit_amount': 0,
                'total_withdrawal_amount': 0,
                'active_investments': 0,
                'pending_deposits': 0,
                'pending_withdrawals': 0,
                'banned_users': 0
            }
        }), 200

@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    # Check if collection exists
    if users_collection is None:
        return jsonify({
            'success': False,
            'message': 'Database connection error',
            'data': {'users': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 500
    
    try:
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
        
        total = users_collection.count_documents(query)
        users = list(users_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
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
                    'wallet': user.get('wallet', {'balance': 0, 'total_deposited': 0, 'total_profit': 0}),
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
            'data': {'users': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 500

@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_deposits():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if deposits_collection is None:
        return jsonify({
            'success': True,
            'data': {'deposits': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
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
                
                if users_collection is not None and 'user_id' in deposit:
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
            'data': {'deposits': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200

@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_withdrawals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if withdrawals_collection is None:
        return jsonify({
            'success': True,
            'data': {'withdrawals': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
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
                
                if users_collection is not None and 'user_id' in withdrawal:
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
            'data': {'withdrawals': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200

@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if investments_collection is None:
        return jsonify({
            'success': True,
            'data': {'investments': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
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
                
                if users_collection is not None and 'user_id' in inv:
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
            'data': {'investments': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200

@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if transactions_collection is None:
        return jsonify({
            'success': True,
            'data': {'transactions': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        tx_type = request.args.get('type', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if tx_type != 'all':
            query['type'] = tx_type
        
        total = transactions_collection.count_documents(query)
        transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_transactions = []
        for tx in transactions:
            try:
                tx['_id'] = str(tx['_id'])
                if 'created_at' in tx and isinstance(tx['created_at'], datetime):
                    tx['created_at'] = tx['created_at'].isoformat()
                
                if users_collection is not None and 'user_id' in tx:
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
            'data': {'transactions': [], 'total': 0, 'page': 1, 'pages': 1}
        }), 200

@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Admin adjustment')
        
        if not validate_amount(amount, -1000000) or amount > 1000000:
            return jsonify({'success': False, 'message': 'Invalid amount'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        current_balance = user.get('wallet', {}).get('balance', 0)
        new_balance = current_balance + amount
        
        result = users_collection.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'message': 'Failed to update balance'}), 500
        
        if transactions_collection:
            transactions_collection.insert_one({
                'user_id': str(user_id), 'type': 'adjustment', 'amount': abs(amount),
                'status': 'completed', 'description': f'Balance adjustment by admin: {reason} (${amount:+,.2f})',
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user_id, 'Balance Adjusted', f'Your balance has been adjusted by ${amount:+,.2f}. Reason: {reason}', 'info')
        
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
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        new_ban_status = not user.get('is_banned', False)
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status}})
        action = 'banned' if new_ban_status else 'unbanned'
        
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
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        username = user.get('username', 'Unknown')
        
        # Delete related data
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
        
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        response = jsonify({'success': True, 'message': f'User {username} permanently deleted'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits/<deposit_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_deposit(deposit_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if deposits_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
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
            
            if transactions_collection:
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
            
            if transactions_collection:
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
    
    if withdrawals_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
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
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved', 'processed_at': datetime.now(timezone.utc)}})
            
            if transactions_collection:
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
            
            if transactions_collection:
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

@app.route('/api/admin/send-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_send_email():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        subject = data.get('subject')
        message = data.get('message')
        
        if not user_id or not subject or not message:
            return jsonify({'success': False, 'message': 'User ID, subject, and message are required'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        email_sent = send_email(user['email'], subject, message)
        
        if email_sent:
            create_notification(user_id, subject, message, 'info')
            response = jsonify({'success': True, 'message': f'Email sent to {user["email"]}'})
        else:
            response = jsonify({'success': False, 'message': 'Failed to send email'})
        
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Send email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast_email():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        recipients_type = data.get('recipients', 'all')
        subject = data.get('subject')
        message = data.get('message')
        
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
        
        users = list(users_collection.find(query))
        
        sent_count = 0
        for user in users:
            if send_email(user['email'], subject, message):
                create_notification(user['_id'], subject, message, 'info')
                sent_count += 1
        
        response = jsonify({'success': True, 'message': f'Broadcast sent to {sent_count} users', 'data': {'count': sent_count}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/reset-all', methods=['GET'])
def reset_all_admin():
    """Emergency reset - creates fresh admin account"""
    secret_key = request.args.get('secret')
    if not secret_key or secret_key != ADMIN_RESET_SECRET:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        if users_collection is not None:
            users_collection.delete_many({'is_admin': True})
            users_collection.delete_many({'username': 'admin'})
        
        hashed_password = hash_password('admin123')
        
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
            'referral_code': 'ADMIN2025', 'referrals': [], 'kyc_status': 'verified'
        }
        
        result = users_collection.insert_one(new_admin)
        
        return jsonify({
            'success': True,
            'message': '✅ Admin account created!',
            'credentials': {'username': 'admin', 'password': 'admin123'},
            'admin_id': str(result.inserted_id)
        })
    except Exception as e:
        logger.error(f"Reset admin error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== HEALTH CHECK ====================
@app.route('/health', methods=['GET', 'OPTIONS'])
def health_check():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    mongo_status = 'connected' if users_collection is not None else 'disconnected'
    response = jsonify({
        'success': True, 
        'status': 'healthy', 
        'mongo': mongo_status,
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    return add_cors_headers(response)

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def api_health_check():
    return health_check()

# ==================== FRONTEND ROUTES ====================
@app.route('/')
def serve_index():
    response = jsonify({
        'success': True, 
        'message': 'Veloxtrades API Server',
        'frontend': FRONTEND_URL,
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login', '/api/verify-token']
    })
    return add_cors_headers(response)

@app.route('/<path:filename>')
def serve_static_files(filename):
    try:
        response = make_response(send_from_directory(app.static_folder, filename))
        return add_cors_headers(response)
    except Exception as e:
        return jsonify({'success': False, 'message': 'File not found'}), 404

# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 VELOXTRADES API SERVER - PRODUCTION READY")
    print("=" * 70)
    print(f"📊 MongoDB Status: {'Connected' if users_collection is not None else 'Disconnected'}")
    print("📧 Email Service Configured")
    print("👑 Admin Dashboard Ready")
    print("=" * 70)
    print("📝 TO CREATE ADMIN:")
    print(f"   Visit: {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
