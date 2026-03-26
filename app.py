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
import json
import csv
import base64
from io import StringIO, BytesIO
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory, make_response, send_file
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

# ==================== URL CONFIGURATION ====================
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://www.veloxtrades.com.ng')
BACKEND_URL = os.getenv('BACKEND_URL', 'https://investment-gto3.onrender.com')

# Admin reset secret
ADMIN_RESET_SECRET = os.getenv('ADMIN_RESET_SECRET', 'veloxtrades-admin-reset-2025')

# Platform settings (default values)
PLATFORM_SETTINGS = {
    'min_deposit': 10,
    'max_deposit': 100000,
    'min_withdrawal': 50,
    'max_withdrawal': 50000,
    'withdrawal_fee': 0,
    'referral_bonus': 5,
    'maintenance_mode': False,
    'maintenance_message': 'Site under maintenance. Please check back later.'
}

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

# ==================== MONGO DB CONNECTION ====================
client = None
db = None
users_collection = None
investments_collection = None
transactions_collection = None
deposits_collection = None
withdrawals_collection = None
notifications_collection = None
kyc_collection = None
support_tickets_collection = None
admin_logs_collection = None
settings_collection = None
email_logs_collection = None
referral_stats_collection = None

def init_mongo():
    """Initialize MongoDB connection with enhanced error handling"""
    global client, db, users_collection, investments_collection, transactions_collection
    global deposits_collection, withdrawals_collection, notifications_collection, kyc_collection
    global support_tickets_collection, admin_logs_collection, settings_collection, email_logs_collection, referral_stats_collection
    
    try:
        logger.info("🔄 Attempting to connect to MongoDB...")
        
        mongo_uri = app.config['MONGO_URI']
        if not mongo_uri or mongo_uri == 'mongodb://localhost:27017/':
            logger.warning("⚠️ Using default MongoDB URI")
        
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        client.admin.command('ping')
        logger.info("✅ MongoDB ping successful")
        
        db = client['veloxtrades_db']
        
        users_collection = db['users']
        investments_collection = db['investments']
        transactions_collection = db['transactions']
        deposits_collection = db['deposits']
        withdrawals_collection = db['withdrawals']
        notifications_collection = db['notifications']
        kyc_collection = db['kyc_verifications']
        support_tickets_collection = db['support_tickets']
        admin_logs_collection = db['admin_logs']
        settings_collection = db['platform_settings']
        email_logs_collection = db['email_logs']
        referral_stats_collection = db['referral_stats']
        logger.info("✅ All collections initialized")
        
        # Create indexes
        try:
            users_collection.create_index('email', unique=True, sparse=True)
            users_collection.create_index('username', unique=True, sparse=True)
            users_collection.create_index('referral_code', unique=True, sparse=True)
            transactions_collection.create_index('user_id')
            transactions_collection.create_index('created_at')
            support_tickets_collection.create_index('user_id')
            support_tickets_collection.create_index('status')
            deposits_collection.create_index('user_id')
            deposits_collection.create_index('status')
            withdrawals_collection.create_index('user_id')
            withdrawals_collection.create_index('status')
            logger.info("✅ Database indexes created")
        except Exception as e:
            logger.warning(f"⚠️ Index creation warning: {e}")
        
        # Initialize settings if not exists
        try:
            if settings_collection.count_documents({}) == 0:
                settings_collection.insert_one(PLATFORM_SETTINGS)
                logger.info("✅ Default platform settings initialized")
        except Exception as e:
            logger.error(f"❌ Error initializing settings: {e}")
        
        logger.info("✅ MongoDB Connected Successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ MongoDB Connection Error: {e}")
        logger.error(traceback.format_exc())
        return False

# Initialize MongoDB
mongo_connected = init_mongo()

@app.before_request
def ensure_db_connection():
    """Ensure database is connected before processing requests"""
    global mongo_connected, users_collection
    
    if request.path in ['/health', '/api/health', '/api/db-health', '/api/test-db']:
        return
    
    if users_collection is None:
        logger.warning(f"⚠️ Database not connected for request: {request.path}")
        mongo_connected = init_mongo()
        
        if users_collection is None:
            if request.path.startswith('/api/') and request.path not in ['/api/health', '/api/db-health', '/api/test-db']:
                return jsonify({
                    'success': False, 
                    'message': 'Database connection error. Please try again later.'
                }), 503

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

# ==================== EMAIL CONFIGURATION ====================
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USER = 'kingsleyuzokwe523@gmail.com'
EMAIL_PASSWORD = 'aonjmqllcpuwlwkp'
EMAIL_FROM = 'Veloxtrades'

def get_email_template(title, content, button_text=None, button_link=None):
    """Return styled HTML email template"""
    button_html = ''
    if button_text and button_link:
        button_html = f'''
        <div style="text-align: center; margin: 30px 0;">
            <a href="{button_link}" style="background: #10b981; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">{button_text}</a>
        </div>
        '''
    
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f5f5f5; margin: 0; padding: 0; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #10b981, #059669); color: white; padding: 30px 20px; text-align: center; border-radius: 10px 10px 0 0; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .header p {{ margin: 10px 0 0; opacity: 0.9; }}
            .content {{ background: white; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; border-top: 1px solid #eee; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>VELOXTRADES</h1>
                <p>The Velocity of Wealth</p>
            </div>
            <div class="content">
                <h2>{title}</h2>
                {content}
                {button_html}
            </div>
            <div class="footer">
                <p>© 2025 Veloxtrades. All rights reserved.</p>
                <p>If you did not request this email, please ignore it.</p>
            </div>
        </div>
    </body>
    </html>
    '''

def log_email(to_email, subject, status, error=None):
    """Log email attempts for debugging"""
    try:
        if email_logs_collection is not None:
            email_logs_collection.insert_one({
                'to_email': to_email,
                'subject': subject,
                'status': status,
                'error': str(error) if error else None,
                'created_at': datetime.now(timezone.utc)
            })
    except Exception as e:
        logger.error(f"Failed to log email: {e}")

def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email with logging and retry logic"""
    for attempt in range(max_retries):
        try:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
                logger.error(f"❌ Invalid email format: {to_email}")
                log_email(to_email, subject, 'failed', 'Invalid email format')
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
            log_email(to_email, subject, 'sent')
            return True
            
        except Exception as e:
            logger.error(f"❌ Email error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                log_email(to_email, subject, 'failed', str(e))
                return False
    return False

def send_deposit_approved_email(user, amount, crypto, transaction_id):
    subject = f"✅ Deposit Approved - ${amount} added to your Veloxtrades account"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ Deposit Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Method: <strong>{crypto.upper()}</strong></p>
        <p>Transaction ID: <strong>{transaction_id or 'N/A'}</strong></p>
    </div>
    <p>Your deposit has been successfully added to your wallet balance.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your deposit of ${amount:,.2f} has been approved.", html_body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount} sent to your wallet"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ Withdrawal Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Currency: <strong>{currency.upper()}</strong></p>
    </div>
    <p>Your withdrawal has been processed and sent to your wallet.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your withdrawal of ${amount:,.2f} has been approved.", html_body)

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
        return None

def get_user_from_request():
    token = None
    token = request.cookies.get('veloxtrades_token')
    if not token:
        token = request.cookies.get('elite_token')
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
        if users_collection is None:
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
        return notifications_collection.insert_one({
            'user_id': str(user_id), 'title': title, 'message': message,
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

# ==================== INVESTMENT PLANS ====================
INVESTMENT_PLANS = {
    'standard': {'name': 'Standard Plan', 'roi': 8, 'duration_hours': 20, 'min_deposit': 50, 'max_deposit': 999},
    'advanced': {'name': 'Advanced Plan', 'roi': 18, 'duration_hours': 48, 'min_deposit': 1000, 'max_deposit': 5000},
    'professional': {'name': 'Professional Plan', 'roi': 35, 'duration_hours': 96, 'min_deposit': 5001, 'max_deposit': 10000},
    'classic': {'name': 'Classic Plan', 'roi': 50, 'duration_hours': 144, 'min_deposit': 10001, 'max_deposit': float('inf')}
}

# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    if investments_collection is None or users_collection is None:
        return
    
    try:
        logger.info("🔄 Processing investment profits...")
        cursor = investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        }).batch_size(100)
        
        processed_count = 0
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
            except Exception as e:
                logger.error(f"Error processing investment: {e}")
        
        logger.info(f"✅ Processed {processed_count} investments")
    except Exception as e:
        logger.error(f"Error in profit processing: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=process_investment_profits, trigger="interval", hours=1, id="profit_processor", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

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
        referral_code = data.get('referral_code', '').strip().upper()

        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        if users_collection.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        if users_collection.find_one({'username': username}):
            return jsonify({'success': False, 'message': 'Username already taken'}), 400

        referred_by = None
        if referral_code:
            referrer = users_collection.find_one({'referral_code': referral_code})
            if referrer:
                referred_by = str(referrer['_id'])
                users_collection.update_one(
                    {'_id': referrer['_id']},
                    {'$push': {'referrals': username}}
                )

        new_referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))
        wallet = {'balance': 0.00, 'total_deposited': 0.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00}

        user_data = {
            'full_name': full_name, 'email': email, 'username': username, 'password': hash_password(password),
            'phone': data.get('phone', ''), 'country': data.get('country', ''), 'wallet': wallet,
            'is_admin': False, 'is_verified': False, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': new_referral_code, 'referred_by': referred_by,
            'referrals': [], 'kyc_status': 'pending', 'notification_preferences': {'email': True, 'push': True}
        }

        result = users_collection.insert_one(user_data)
        create_notification(result.inserted_id, 'Welcome to Veloxtrades!', 'Thank you for joining. Start your investment journey today.', 'success')
        
        response = jsonify({'success': True, 'message': 'Registration successful! You can now login.'})
        return add_cors_headers(response), 201
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        logger.error("❌ Login attempted but users_collection is None")
        return jsonify({'success': False, 'message': 'Database connection error. Please try again later.'}), 503
    
    try:
        logger.info(f"📝 Login attempt received from IP: {request.remote_addr}")
        
        data = request.get_json()
        if not data:
            logger.warning("⚠️ Login attempt with no data")
            return jsonify({'success': False, 'message': 'No credentials provided'}), 400
            
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')
        
        logger.info(f"🔐 Login attempt for: {username_or_email}")
        
        if not username_or_email or not password:
            logger.warning(f"⚠️ Missing credentials for: {username_or_email}")
            return jsonify({'success': False, 'message': 'Username/email and password are required'}), 400

        user = users_collection.find_one({
            '$or': [
                {'email': username_or_email}, 
                {'username': username_or_email}
            ]
        })

        if not user:
            logger.warning(f"⚠️ User not found: {username_or_email}")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        password_valid = verify_password(user['password'], password)

        if not password_valid:
            logger.warning(f"⚠️ Invalid password for user: {username_or_email}")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        if user.get('is_banned', False):
            logger.warning(f"⚠️ Banned account attempted login: {username_or_email}")
            return jsonify({'success': False, 'message': 'Account has been suspended. Contact support.'}), 403

        maintenance_mode = False
        maintenance_message = 'Site under maintenance. Please check back later.'
        
        try:
            if settings_collection is not None:
                settings = settings_collection.find_one({})
                if settings:
                    maintenance_mode = settings.get('maintenance_mode', False)
                    maintenance_message = settings.get('maintenance_message', maintenance_message)
        except Exception as e:
            logger.error(f"❌ Error fetching settings: {e}")
        
        if maintenance_mode and not user.get('is_admin', False):
            logger.info(f"🚫 Maintenance mode blocked login for: {username_or_email}")
            return jsonify({'success': False, 'message': maintenance_message}), 503

        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))

        users_collection.update_one(
            {'_id': user['_id']}, 
            {'$set': {'last_login': datetime.now(timezone.utc)}}
        )

        user_data = {
            'id': str(user['_id']),
            'username': user['username'],
            'full_name': user.get('full_name', ''),
            'email': user['email'],
            'balance': user.get('wallet', {}).get('balance', 0.00),
            'is_admin': user.get('is_admin', False),
            'kyc_status': user.get('kyc_status', 'pending'),
            'is_verified': user.get('is_verified', False)
        }

        response_data = {
            'success': True, 
            'message': 'Login successful!', 
            'data': {'token': token, 'user': user_data}
        }
        
        response = make_response(jsonify(response_data))
        response.set_cookie(
            'veloxtrades_token', 
            value=token, 
            httponly=True, 
            secure=True, 
            samesite='Lax',
            max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, 
            path='/'
        )
        
        logger.info(f"✅ Login successful for user: {username_or_email}")
        return add_cors_headers(response), 200

    except Exception as e:
        logger.error(f"❌ Unexpected login error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'An unexpected error occurred. Please try again.'}), 500

@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        return handle_preflight()
    response = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
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
        'referral_code': user.get('referral_code', ''), 'referrals': user.get('referrals', []),
        'notification_preferences': user.get('notification_preferences', {'email': True, 'push': True}),
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
            'is_admin': user.get('is_admin', False),
            'kyc_status': user.get('kyc_status', 'pending')
        }
    })
    return add_cors_headers(response)

# ==================== USER DASHBOARD ====================
@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def user_dashboard():
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
        
        referral_count = len(user.get('referrals', []))
        referral_earnings = referral_stats_collection.find_one({'user_id': str(user['_id'])}) if referral_stats_collection else None
        
        # Add deposit stats
        pending_deposits = deposits_collection.count_documents({'user_id': str(user['_id']), 'status': 'pending'}) if deposits_collection else 0
        approved_deposits = deposits_collection.count_documents({'user_id': str(user['_id']), 'status': 'approved'}) if deposits_collection else 0
        
        dashboard_data = {
            'wallet': user.get('wallet', {'balance': 0.00}),
            'investments': {
                'total_active': total_active,
                'total_profit': user.get('wallet', {}).get('total_profit', 0),
                'pending_profit': pending_profit,
                'count': len(active_investments)
            },
            'recent_transactions': recent_transactions,
            'notification_count': unread_notifications,
            'referral_stats': {
                'code': user.get('referral_code', ''),
                'count': referral_count,
                'earnings': referral_earnings.get('total_earnings', 0) if referral_earnings else 0
            },
            'kyc_status': user.get('kyc_status', 'pending'),
            'deposit_stats': {
                'pending': pending_deposits,
                'approved': approved_deposits,
                'total_deposited': user.get('wallet', {}).get('total_deposited', 0)
            }
        }
        response = jsonify({'success': True, 'data': dashboard_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load dashboard'}), 500

# ==================== DEPOSIT MANAGEMENT ====================
@app.route('/api/deposits', methods=['POST', 'OPTIONS'])
def create_deposit():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        crypto = data.get('crypto', 'usdt')
        transaction_hash = data.get('transaction_hash', '').strip()
        
        settings = settings_collection.find_one({})
        min_deposit = settings.get('min_deposit', 10) if settings else 10
        max_deposit = settings.get('max_deposit', 100000) if settings else 100000
        
        if amount < min_deposit:
            return jsonify({'success': False, 'message': f'Minimum deposit amount is ${min_deposit}'}), 400
        if amount > max_deposit:
            return jsonify({'success': False, 'message': f'Maximum deposit amount is ${max_deposit}'}), 400
        
        deposit_id = 'DEP-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))
        
        deposit_data = {
            'deposit_id': deposit_id,
            'user_id': str(user['_id']),
            'username': user['username'],
            'amount': amount,
            'crypto': crypto,
            'transaction_hash': transaction_hash,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc),
            'approved_at': None,
            'rejected_at': None,
            'rejection_reason': None
        }
        
        deposits_collection.insert_one(deposit_data)
        
        create_notification(user['_id'], 'Deposit Request Submitted', f'Your deposit request of ${amount:,.2f} has been submitted.', 'info')
        
        response = jsonify({'success': True, 'message': 'Deposit request submitted', 'data': {'deposit_id': deposit_id}})
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"Create deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/deposits', methods=['GET', 'OPTIONS'])
def get_deposits():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        query = {'user_id': str(user['_id'])}
        total = deposits_collection.count_documents(query)
        deposits = list(deposits_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for deposit in deposits:
            deposit['_id'] = str(deposit['_id'])
            if 'created_at' in deposit:
                deposit['created_at'] = deposit['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': {'deposits': deposits, 'total': total}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== WITHDRAWAL MANAGEMENT ====================
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
        currency = data.get('currency', 'usdt')
        wallet_address = data.get('wallet_address', '').strip()
        
        if not wallet_address:
            return jsonify({'success': False, 'message': 'Wallet address is required'}), 400
        
        settings = settings_collection.find_one({})
        min_withdrawal = settings.get('min_withdrawal', 50) if settings else 50
        max_withdrawal = settings.get('max_withdrawal', 50000) if settings else 50000
        withdrawal_fee = settings.get('withdrawal_fee', 0) if settings else 0
        
        if amount < min_withdrawal:
            return jsonify({'success': False, 'message': f'Minimum withdrawal amount is ${min_withdrawal}'}), 400
        if amount > max_withdrawal:
            return jsonify({'success': False, 'message': f'Maximum withdrawal amount is ${max_withdrawal}'}), 400
        
        fee_amount = amount * (withdrawal_fee / 100)
        net_amount = amount - fee_amount
        
        if user['wallet']['balance'] < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        withdrawal_id = 'WIT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))
        
        withdrawal_data = {
            'withdrawal_id': withdrawal_id,
            'user_id': str(user['_id']),
            'username': user['username'],
            'amount': amount,
            'fee': fee_amount,
            'net_amount': net_amount,
            'currency': currency,
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc),
            'approved_at': None,
            'rejected_at': None,
            'rejection_reason': None
        }
        
        withdrawals_collection.insert_one(withdrawal_data)
        
        create_notification(user['_id'], 'Withdrawal Request Submitted', f'Your withdrawal request of ${amount:,.2f} has been submitted.', 'info')
        
        response = jsonify({'success': True, 'message': 'Withdrawal request submitted', 'data': {'withdrawal_id': withdrawal_id}})
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"Create withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/withdrawals', methods=['GET', 'OPTIONS'])
def get_withdrawals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        query = {'user_id': str(user['_id'])}
        total = withdrawals_collection.count_documents(query)
        withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for withdrawal in withdrawals:
            withdrawal['_id'] = str(withdrawal['_id'])
            if 'created_at' in withdrawal:
                withdrawal['created_at'] = withdrawal['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': {'withdrawals': withdrawals, 'total': total}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== INVESTMENT ====================
@app.route('/api/invest', methods=['POST', 'OPTIONS'])
def invest():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        plan_type = data.get('plan')
        amount = float(data.get('amount', 0))
        
        plan = INVESTMENT_PLANS.get(plan_type)
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400
        
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum investment is ${plan["min_deposit"]}'}), 400
        if amount > plan['max_deposit']:
            return jsonify({'success': False, 'message': f'Maximum investment is ${plan["max_deposit"]}'}), 400
        
        if user['wallet']['balance'] < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        expected_profit = amount * plan['roi'] / 100
        end_date = datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])
        
        users_collection.update_one(
            {'_id': user['_id']},
            {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}}
        )
        
        investment_data = {
            'user_id': str(user['_id']),
            'username': user['username'],
            'plan': plan_type,
            'plan_name': plan['name'],
            'amount': amount,
            'roi': plan['roi'],
            'expected_profit': expected_profit,
            'duration_hours': plan['duration_hours'],
            'start_date': datetime.now(timezone.utc),
            'end_date': end_date,
            'status': 'active'
        }
        
        result = investments_collection.insert_one(investment_data)
        
        transactions_collection.insert_one({
            'user_id': str(user['_id']),
            'type': 'investment',
            'amount': amount,
            'status': 'completed',
            'description': f'Investment in {plan["name"]}',
            'investment_id': str(result.inserted_id),
            'created_at': datetime.now(timezone.utc)
        })
        
        create_notification(user['_id'], 'Investment Started!', f'You have invested ${amount:,.2f} in {plan["name"]}.', 'success')
        
        response = jsonify({'success': True, 'message': 'Investment successful', 'data': {'expected_profit': expected_profit, 'end_date': end_date.isoformat()}})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Investment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/investments', methods=['GET', 'OPTIONS'])
def get_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        investments = list(investments_collection.find({'user_id': str(user['_id'])}).sort('start_date', -1))
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if 'start_date' in inv:
                inv['start_date'] = inv['start_date'].isoformat()
            if 'end_date' in inv:
                inv['end_date'] = inv['end_date'].isoformat()
        
        response = jsonify({'success': True, 'data': {'investments': investments}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get investments error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: USERS MANAGEMENT ====================
@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
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
        
        for user in users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user:
                user['created_at'] = user['created_at'].isoformat()
            if 'last_login' in user and user['last_login']:
                user['last_login'] = user['last_login'].isoformat()
            # Remove password
            user.pop('password', None)
        
        # Get statistics
        total_users = users_collection.count_documents({})
        active_users = users_collection.count_documents({'is_active': True})
        banned_users = users_collection.count_documents({'is_banned': True})
        verified_users = users_collection.count_documents({'is_verified': True})
        
        stats = {
            'total': total_users,
            'active': active_users,
            'banned': banned_users,
            'verified': verified_users
        }
        
        response = jsonify({
            'success': True,
            'data': {
                'users': users,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1,
                'stats': stats
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# Add email stats to admin stats
email_stats = {
    'total_sent': email_logs_collection.count_documents({'status': 'sent'}) if email_logs_collection else 0,
    'total_failed': email_logs_collection.count_documents({'status': 'failed'}) if email_logs_collection else 0
}

# Add to your response
'email': email_stats
@app.route('/api/admin/users/<user_id>', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_user(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user['_id'] = str(user['_id'])
        if 'created_at' in user:
            user['created_at'] = user['created_at'].isoformat()
        if 'last_login' in user and user['last_login']:
            user['last_login'] = user['last_login'].isoformat()
        user.pop('password', None)
        
        # Get user's transactions
        transactions = list(transactions_collection.find({'user_id': str(user_id)}).sort('created_at', -1).limit(20))
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()
        
        # Get user's investments
        investments = list(investments_collection.find({'user_id': str(user_id)}).sort('start_date', -1))
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if 'start_date' in inv:
                inv['start_date'] = inv['start_date'].isoformat()
        
        response = jsonify({
            'success': True,
            'data': {
                'user': user,
                'transactions': transactions,
                'investments': investments
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/ban', methods=['POST', 'OPTIONS'])
@require_admin
def admin_ban_user(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        reason = data.get('reason', 'No reason provided')
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_banned': True, 'ban_reason': reason, 'banned_at': datetime.now(timezone.utc)}}
        )
        
        create_notification(user_id, 'Account Suspended', f'Your account has been suspended. Reason: {reason}', 'error')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'ban_user', f'Banned user {user["username"]}. Reason: {reason}')
        
        response = jsonify({'success': True, 'message': 'User banned successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Ban user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/unban', methods=['POST', 'OPTIONS'])
@require_admin
def admin_unban_user(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_banned': False}, '$unset': {'ban_reason': '', 'banned_at': ''}}
        )
        
        create_notification(user_id, 'Account Restored', 'Your account has been restored. You can now login.', 'success')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'unban_user', f'Unbanned user {user["username"]}')
        
        response = jsonify({'success': True, 'message': 'User unbanned successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Unban user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: DEPOSITS MANAGEMENT ====================
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
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = deposits_collection.count_documents(query)
        deposits = list(deposits_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for deposit in deposits:
            deposit['_id'] = str(deposit['_id'])
            if 'created_at' in deposit:
                deposit['created_at'] = deposit['created_at'].isoformat()
        
        # Get statistics
        stats = {
            'pending': deposits_collection.count_documents({'status': 'pending'}),
            'approved': deposits_collection.count_documents({'status': 'approved'}),
            'rejected': deposits_collection.count_documents({'status': 'rejected'}),
            'total_amount': deposits_collection.aggregate([
                {'$match': {'status': 'approved'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ]).next().get('total', 0)
        }
        
        response = jsonify({
            'success': True,
            'data': {
                'deposits': deposits,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1,
                'stats': stats
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits/<deposit_id>/approve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_approve_deposit(deposit_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        deposit = deposits_collection.find_one({'deposit_id': deposit_id})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        if deposit['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Deposit is already {deposit["status"]}'}), 400
        
        deposits_collection.update_one(
            {'deposit_id': deposit_id},
            {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}}
        )
        
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if user:
            users_collection.update_one(
                {'_id': ObjectId(deposit['user_id'])},
                {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}}
            )
            
            transactions_collection.insert_one({
                'user_id': str(deposit['user_id']),
                'type': 'deposit',
                'amount': deposit['amount'],
                'status': 'completed',
                'description': f'Deposit approved - {deposit["crypto"].upper()}',
                'deposit_id': deposit_id,
                'created_at': datetime.now(timezone.utc)
            })
            
            create_notification(deposit['user_id'], 'Deposit Approved', f'Your deposit of ${deposit["amount"]:,.2f} has been approved.', 'success')
            
            try:
                send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'approve_deposit', f'Approved deposit {deposit_id} for ${deposit["amount"]}')
        
        response = jsonify({'success': True, 'message': 'Deposit approved successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Approve deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits/<deposit_id>/reject', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reject_deposit(deposit_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        reason = data.get('reason', 'Not specified')
        
        deposit = deposits_collection.find_one({'deposit_id': deposit_id})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        if deposit['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Deposit is already {deposit["status"]}'}), 400
        
        deposits_collection.update_one(
            {'deposit_id': deposit_id},
            {'$set': {'status': 'rejected', 'rejected_at': datetime.now(timezone.utc), 'rejection_reason': reason}}
        )
        
        create_notification(deposit['user_id'], 'Deposit Rejected', f'Your deposit of ${deposit["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'reject_deposit', f'Rejected deposit {deposit_id} for ${deposit["amount"]}. Reason: {reason}')
        
        response = jsonify({'success': True, 'message': 'Deposit rejected successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Reject deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: WITHDRAWALS MANAGEMENT ====================
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
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = withdrawals_collection.count_documents(query)
        withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for withdrawal in withdrawals:
            withdrawal['_id'] = str(withdrawal['_id'])
            if 'created_at' in withdrawal:
                withdrawal['created_at'] = withdrawal['created_at'].isoformat()
        
        stats = {
            'pending': withdrawals_collection.count_documents({'status': 'pending'}),
            'approved': withdrawals_collection.count_documents({'status': 'approved'}),
            'rejected': withdrawals_collection.count_documents({'status': 'rejected'}),
            'total_amount': withdrawals_collection.aggregate([
                {'$match': {'status': 'approved'}},
                {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
            ]).next().get('total', 0)
        }
        
        response = jsonify({
            'success': True,
            'data': {
                'withdrawals': withdrawals,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1,
                'stats': stats
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals/<withdrawal_id>/approve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_approve_withdrawal(withdrawal_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        withdrawal = withdrawals_collection.find_one({'withdrawal_id': withdrawal_id})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Withdrawal is already {withdrawal["status"]}'}), 400
        
        withdrawals_collection.update_one(
            {'withdrawal_id': withdrawal_id},
            {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}}
        )
        
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        if user:
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {'$inc': {'wallet.total_withdrawn': withdrawal['amount']}}
            )
            
            create_notification(withdrawal['user_id'], 'Withdrawal Approved', f'Your withdrawal of ${withdrawal["amount"]:,.2f} has been approved and processed.', 'success')
            
            try:
                send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
            except Exception as e:
                logger.error(f"Failed to send email: {e}")
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'approve_withdrawal', f'Approved withdrawal {withdrawal_id} for ${withdrawal["amount"]}')
        
        response = jsonify({'success': True, 'message': 'Withdrawal approved successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Approve withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals/<withdrawal_id>/reject', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reject_withdrawal(withdrawal_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        reason = data.get('reason', 'Not specified')
        
        withdrawal = withdrawals_collection.find_one({'withdrawal_id': withdrawal_id})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': f'Withdrawal is already {withdrawal["status"]}'}), 400
        
        withdrawals_collection.update_one(
            {'withdrawal_id': withdrawal_id},
            {'$set': {'status': 'rejected', 'rejected_at': datetime.now(timezone.utc), 'rejection_reason': reason}}
        )
        
        # Refund the amount back to user
        users_collection.update_one(
            {'_id': ObjectId(withdrawal['user_id'])},
            {'$inc': {'wallet.balance': withdrawal['amount']}}
        )
        
        create_notification(withdrawal['user_id'], 'Withdrawal Rejected', f'Your withdrawal of ${withdrawal["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'reject_withdrawal', f'Rejected withdrawal {withdrawal_id} for ${withdrawal["amount"]}. Reason: {reason}')
        
        response = jsonify({'success': True, 'message': 'Withdrawal rejected successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Reject withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: STATS DASHBOARD ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        now = datetime.now(timezone.utc)
        today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        
        # User stats
        total_users = users_collection.count_documents({})
        new_users_today = users_collection.count_documents({'created_at': {'$gte': today_start}})
        active_users = users_collection.count_documents({'is_active': True})
        
        # Financial stats
        total_deposits = deposits_collection.aggregate([
            {'$match': {'status': 'approved'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]).next().get('total', 0)
        
        total_withdrawals = withdrawals_collection.aggregate([
            {'$match': {'status': 'approved'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]).next().get('total', 0)
        
        total_profit_paid = transactions_collection.aggregate([
            {'$match': {'type': 'profit', 'status': 'completed'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]).next().get('total', 0)
        
        # Investment stats
        active_investments = investments_collection.count_documents({'status': 'active'})
        total_invested = investments_collection.aggregate([
            {'$match': {'status': 'active'}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}}
        ]).next().get('total', 0)
        
        # Pending requests
        pending_deposits = deposits_collection.count_documents({'status': 'pending'})
        pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
        pending_kyc = kyc_collection.count_documents({'status': 'pending'}) if kyc_collection else 0
        open_tickets = support_tickets_collection.count_documents({'status': 'open'}) if support_tickets_collection else 0
        
        response = jsonify({
            'success': True,
            'data': {
                'users': {
                    'total': total_users,
                    'new_today': new_users_today,
                    'active': active_users
                },
                'finance': {
                    'total_deposits': total_deposits,
                    'total_withdrawals': total_withdrawals,
                    'total_profit_paid': total_profit_paid,
                    'platform_balance': total_deposits - total_withdrawals
                },
                'investments': {
                    'active': active_investments,
                    'total_invested': total_invested
                },
                'pending': {
                    'deposits': pending_deposits,
                    'withdrawals': pending_withdrawals,
                    'kyc': pending_kyc,
                    'tickets': open_tickets
                }
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: NOTIFICATIONS ====================
@app.route('/api/admin/notifications/send', methods=['POST', 'OPTIONS'])
@require_admin
def admin_send_notification():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        title = data.get('title')
        message = data.get('message')
        type = data.get('type', 'info')
        
        if not title or not message:
            return jsonify({'success': False, 'message': 'Title and message are required'}), 400
        
        if user_id:
            # Send to specific user
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if not user:
                return jsonify({'success': False, 'message': 'User not found'}), 404
            
            create_notification(user_id, title, message, type)
            
            # Send email if user has email preference
            if user.get('notification_preferences', {}).get('email', True):
                html_body = get_email_template(title, f'<p>{message}</p>', 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
                send_email(user['email'], title, message, html_body)
        else:
            # Send to all users
            all_users = users_collection.find({})
            count = 0
            for user in all_users:
                create_notification(user['_id'], title, message, type)
                count += 1
            
            response_msg = f'Notification sent to {count} users'
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'send_notification', f'Sent notification: {title}')
        
        response = jsonify({'success': True, 'message': response_msg if 'response_msg' in dir() else 'Notification sent'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Send notification error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== NOTIFICATIONS ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        notifications = list(notifications_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).skip(skip).limit(limit))
        
        for notif in notifications:
            notif['_id'] = str(notif['_id'])
            if 'created_at' in notif:
                notif['created_at'] = notif['created_at'].isoformat()
        
        total = notifications_collection.count_documents({'user_id': str(user['_id'])})
        unread = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
        
        response = jsonify({
            'success': True,
            'data': {
                'notifications': notifications,
                'total': total,
                'unread': unread,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get notifications error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/<notification_id>/read', methods=['PUT', 'OPTIONS'])
def mark_notification_read(notification_id):
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
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'message': 'Notification not found'}), 404
        
        response = jsonify({'success': True, 'message': 'Notification marked as read'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/notifications/read-all', methods=['PUT', 'OPTIONS'])
def mark_all_notifications_read():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        notifications_collection.update_many(
            {'user_id': str(user['_id']), 'read': False},
            {'$set': {'read': True}}
        )
        
        response = jsonify({'success': True, 'message': 'All notifications marked as read'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Mark all read error: {e}")
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

@app.route('/api/db-health', methods=['GET', 'OPTIONS'])
def db_health_check():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        health_status = {
            'mongo_connected': users_collection is not None,
            'collections': {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if users_collection is not None:
            try:
                health_status['collections']['users'] = users_collection.count_documents({}) >= 0
                health_status['collections']['deposits'] = deposits_collection.count_documents({}) >= 0
                health_status['collections']['withdrawals'] = withdrawals_collection.count_documents({}) >= 0
            except Exception as e:
                health_status['error'] = str(e)
        
        response = jsonify({'success': True, 'data': health_status})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN RESET ====================
@app.route('/api/admin/reset-all', methods=['GET', 'OPTIONS'])
def admin_reset_all():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    secret = request.args.get('secret', '')
    
    if secret != ADMIN_RESET_SECRET:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        # Check if admin already exists
        existing_admin = users_collection.find_one({'is_admin': True})
        
        if existing_admin:
            return jsonify({
                'success': False, 
                'message': 'Admin already exists. Login with admin credentials.'
            }), 400
        
        # Create admin user
        admin_password = hash_password('admin123')
        admin_wallet = {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0}
        
        admin_data = {
            'full_name': 'System Administrator',
            'email': 'admin@veloxtrades.com',
            'username': 'admin',
            'password': admin_password,
            'phone': '+1234567890',
            'country': 'Global',
            'wallet': admin_wallet,
            'is_admin': True,
            'is_verified': True,
            'is_active': True,
            'is_banned': False,
            'two_factor_enabled': False,
            'created_at': datetime.now(timezone.utc),
            'last_login': None,
            'referral_code': 'ADMIN001',
            'referred_by': None,
            'referrals': [],
            'kyc_status': 'approved',
            'notification_preferences': {'email': True, 'push': True}
        }
        
        result = users_collection.insert_one(admin_data)
        
        return jsonify({
            'success': True,
            'message': 'Admin user created successfully',
            'credentials': {
                'username': 'admin',
                'password': 'admin123',
                'email': 'admin@veloxtrades.com'
            }
        })
    except Exception as e:
        logger.error(f"Admin reset error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
    print("🚀 VELOXTRADES API SERVER - FULL FEATURE READY")
    print("=" * 70)
    print(f"📊 MongoDB Status: {'Connected' if users_collection is not None else 'Disconnected'}")
    print("📧 Email Service: Configured with logging")
    print("👑 Admin Dashboard: Full management features")
    print("💰 Deposits: Enabled")
    print("💸 Withdrawals: Enabled")
    print("📊 Investments: Enabled")
    print("📋 KYC Verification: Enabled")
    print("🎫 Support Tickets: Enabled")
    print("📊 Referral System: Enabled")
    print("=" * 70)
    print("📝 TO CREATE ADMIN:")
    print(f"   Visit: {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
