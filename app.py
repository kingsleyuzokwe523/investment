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
    """Initialize MongoDB connection properly"""
    global client, db, users_collection, investments_collection, transactions_collection
    global deposits_collection, withdrawals_collection, notifications_collection, kyc_collection
    global support_tickets_collection, admin_logs_collection, settings_collection, email_logs_collection, referral_stats_collection
    
    try:
        logger.info("🔄 Connecting to MongoDB...")
        client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        db = client['veloxtrades_db']
        
        # Initialize collections
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
        
        # Create indexes
        users_collection.create_index('email', unique=True, sparse=True)
        users_collection.create_index('username', unique=True, sparse=True)
        users_collection.create_index('referral_code', unique=True, sparse=True)
        transactions_collection.create_index('user_id')
        transactions_collection.create_index('created_at')
        support_tickets_collection.create_index('user_id')
        support_tickets_collection.create_index('status')
        
        # Initialize settings if not exists
        if settings_collection.count_documents({}) == 0:
            settings_collection.insert_one(PLATFORM_SETTINGS)
        
        logger.info("✅ MongoDB Connected Successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB Connection Error: {e}")
        return False

# Initialize MongoDB
mongo_connected = init_mongo()

@app.before_request
def before_request():
    """Check MongoDB connection before each request"""
    global mongo_connected
    if not mongo_connected:
        mongo_connected = init_mongo()

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

# Email Templates with Styling
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
            .button {{ display: inline-block; background: #10b981; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; }}
            .warning {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 20px 0; }}
            .success {{ background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0; }}
            .error {{ background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0; }}
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

# ==================== ENHANCED EMAIL FUNCTIONS ====================
def send_deposit_approved_email(user, amount, crypto, transaction_id):
    subject = f"✅ Deposit Approved - ${amount} added to your Veloxtrades account"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="success">
        <p><strong>✅ Deposit Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Method: <strong>{crypto.upper()}</strong></p>
        <p>Transaction ID: <strong>{transaction_id or 'N/A'}</strong></p>
    </div>
    <p>Your deposit has been successfully added to your wallet balance. You can now use these funds to invest or withdraw.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your deposit of ${amount:,.2f} has been approved.", html_body)

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount} - Veloxtrades"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="error">
        <p><strong>❌ Deposit Rejected</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Method: <strong>{crypto.upper()}</strong></p>
        <p>Reason: <strong>{reason}</strong></p>
    </div>
    <p>If you believe this is a mistake, please contact our support team.</p>
    '''
    html_body = get_email_template(subject, content, 'Contact Support', f'{FRONTEND_URL}/support.html')
    return send_email(user['email'], subject, f"Your deposit of ${amount:,.2f} was rejected. Reason: {reason}", html_body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount} sent to your wallet"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="success">
        <p><strong>✅ Withdrawal Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Currency: <strong>{currency.upper()}</strong></p>
        <p>Wallet Address: <strong>{wallet_address[:20]}...{wallet_address[-10:]}</strong></p>
    </div>
    <p>Your withdrawal has been processed and sent to your wallet. Funds should arrive shortly.</p>
    '''
    html_body = get_email_template(subject, content, 'View Transaction', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your withdrawal of ${amount:,.2f} has been approved.", html_body)

def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount} - Veloxtrades"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="error">
        <p><strong>❌ Withdrawal Rejected</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Currency: <strong>{currency.upper()}</strong></p>
        <p>Reason: <strong>{reason}</strong></p>
    </div>
    <p>Please ensure your account is verified and you have sufficient balance before requesting withdrawal.</p>
    '''
    html_body = get_email_template(subject, content, 'Contact Support', f'{FRONTEND_URL}/support.html')
    return send_email(user['email'], subject, f"Your withdrawal of ${amount:,.2f} was rejected. Reason: {reason}", html_body)

def send_transaction_confirmation_email(user, transaction_type, amount, description, new_balance):
    subject = f"💰 Transaction Confirmation - ${amount:,.2f} {transaction_type}"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="success">
        <p><strong>💰 Transaction Completed</strong></p>
        <p>Type: <strong>{transaction_type.capitalize()}</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Description: <strong>{description}</strong></p>
        <p>New Balance: <strong>${new_balance:,.2f}</strong></p>
    </div>
    <p>Your transaction has been processed successfully.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your {transaction_type} of ${amount:,.2f} has been processed.", html_body)

def send_kyc_status_email(user, status, reason=None):
    subject = f"KYC Verification {status.capitalize()} - Veloxtrades"
    status_class = 'success' if status == 'approved' else 'error' if status == 'rejected' else 'warning'
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="{status_class}">
        <p><strong>📋 KYC Verification {status.upper()}</strong></p>
        <p>Status: <strong>{status.capitalize()}</strong></p>
        {f'<p>Reason: <strong>{reason}</strong></p>' if reason else ''}
    </div>
    <p>{"You can now access all platform features." if status == 'approved' else "Please submit valid documents for verification." if status == 'rejected' else "We are reviewing your documents."}</p>
    '''
    html_body = get_email_template(subject, content, 'View Profile', f'{FRONTEND_URL}/profile.html')
    return send_email(user['email'], subject, f"Your KYC verification is {status}.", html_body)

def send_support_ticket_reply_email(user, ticket_id, subject, reply_message):
    email_subject = f"📬 Support Ticket Update: {subject}"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div class="success">
        <p><strong>📬 New Reply to Your Support Ticket</strong></p>
        <p>Ticket ID: <strong>#{ticket_id}</strong></p>
        <p>Subject: <strong>{subject}</strong></p>
        <p>Message: <strong>{reply_message}</strong></p>
    </div>
    <p>Our support team has responded to your inquiry.</p>
    '''
    html_body = get_email_template(email_subject, content, 'View Ticket', f'{FRONTEND_URL}/support.html')
    return send_email(user['email'], email_subject, f"New reply to ticket #{ticket_id}", html_body)

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

        # Handle referral
        referred_by = None
        if referral_code:
            referrer = users_collection.find_one({'referral_code': referral_code})
            if referrer:
                referred_by = str(referrer['_id'])
                # Update referrer's referral list
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
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No credentials provided'}), 400
            
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        user = users_collection.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})

        if not user or not verify_password(user['password'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account has been suspended'}), 403

        # Check maintenance mode
        settings = settings_collection.find_one({}) if settings_collection else PLATFORM_SETTINGS
        if settings and settings.get('maintenance_mode', False) and not user.get('is_admin', False):
            return jsonify({'success': False, 'message': settings.get('maintenance_message', 'Site under maintenance')}), 503

        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))
        users_collection.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})

        user_data = {
            'id': str(user['_id']), 'username': user['username'], 'full_name': user.get('full_name', ''),
            'email': user['email'], 'balance': user.get('wallet', {}).get('balance', 0.00),
            'is_admin': user.get('is_admin', False), 'kyc_status': user.get('kyc_status', 'pending')
        }

        response = make_response(jsonify({'success': True, 'message': 'Login successful!', 'data': {'token': token, 'user': user_data}}))
        response.set_cookie('veloxtrades_token', value=token, httponly=True, secure=True, samesite='Lax', 
                           max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        
        return add_cors_headers(response), 200
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Login failed'}), 500

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

# ==================== USER DASHBOARD ENHANCEMENTS ====================
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
        
        # Referral stats
        referral_count = len(user.get('referrals', []))
        referral_earnings = referral_stats_collection.find_one({'user_id': str(user['_id'])}) if referral_stats_collection else None
        
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
            'kyc_status': user.get('kyc_status', 'pending')
        }
        response = jsonify({'success': True, 'data': dashboard_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'success': False, 'message': 'Failed to load dashboard'}), 500

# ==================== KYC VERIFICATION ====================
@app.route('/api/kyc/submit', methods=['POST', 'OPTIONS'])
def submit_kyc():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        document_type = data.get('document_type')
        document_number = data.get('document_number')
        document_image = data.get('document_image')  # Base64 encoded image
        
        if not all([document_type, document_number, document_image]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        # Check if KYC already submitted
        existing = kyc_collection.find_one({'user_id': str(user['_id'])})
        if existing and existing.get('status') != 'rejected':
            return jsonify({'success': False, 'message': 'KYC already submitted'}), 400
        
        kyc_data = {
            'user_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'document_type': document_type,
            'document_number': document_number,
            'document_image': document_image,
            'status': 'pending',
            'submitted_at': datetime.now(timezone.utc)
        }
        
        kyc_collection.update_one(
            {'user_id': str(user['_id'])},
            {'$set': kyc_data},
            upsert=True
        )
        
        users_collection.update_one({'_id': user['_id']}, {'$set': {'kyc_status': 'pending'}})
        
        # Notify admin
        admin_user = users_collection.find_one({'is_admin': True})
        if admin_user:
            create_notification(admin_user['_id'], 'New KYC Submission', f'User {user["username"]} has submitted KYC documents', 'info')
        
        response = jsonify({'success': True, 'message': 'KYC documents submitted successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"KYC submit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/kyc/status', methods=['GET', 'OPTIONS'])
def get_kyc_status():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        kyc = kyc_collection.find_one({'user_id': str(user['_id'])})
        response_data = {
            'status': user.get('kyc_status', 'pending'),
            'submitted_at': kyc.get('submitted_at').isoformat() if kyc and kyc.get('submitted_at') else None,
            'reviewed_at': kyc.get('reviewed_at').isoformat() if kyc and kyc.get('reviewed_at') else None,
            'rejection_reason': kyc.get('rejection_reason') if kyc else None
        }
        response = jsonify({'success': True, 'data': response_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"KYC status error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== SUPPORT TICKETS ====================
@app.route('/api/support/tickets', methods=['GET', 'OPTIONS'])
def get_tickets():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        tickets = list(support_tickets_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if 'created_at' in ticket:
                ticket['created_at'] = ticket['created_at'].isoformat()
        response = jsonify({'success': True, 'data': {'tickets': tickets}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/support/tickets', methods=['POST', 'OPTIONS'])
def create_ticket():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        subject = data.get('subject')
        message = data.get('message')
        priority = data.get('priority', 'normal')
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message are required'}), 400
        
        ticket_id = 'TKT-' + ''.join(random.choices(string.digits, k=8))
        
        ticket = {
            'ticket_id': ticket_id,
            'user_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'subject': subject,
            'message': message,
            'priority': priority,
            'status': 'open',
            'replies': [],
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        
        result = support_tickets_collection.insert_one(ticket)
        
        # Notify admin
        admin_user = users_collection.find_one({'is_admin': True})
        if admin_user:
            create_notification(admin_user['_id'], f'New Support Ticket: {ticket_id}', f'User {user["username"]} created a new support ticket', 'info')
        
        response = jsonify({'success': True, 'message': 'Ticket created', 'data': {'ticket_id': ticket_id}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Create ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
def reply_ticket(ticket_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        message = data.get('message')
        
        if not message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        if str(ticket['user_id']) != str(user['_id']) and not user.get('is_admin', False):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        reply = {
            'user_id': str(user['_id']),
            'username': user['username'],
            'message': message,
            'is_admin': user.get('is_admin', False),
            'created_at': datetime.now(timezone.utc)
        }
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'replies': reply},
                '$set': {'updated_at': datetime.now(timezone.utc), 'status': 'in_progress' if user.get('is_admin', False) else 'open'}
            }
        )
        
        # Send email notification
        if user.get('is_admin', False) and ticket.get('email'):
            recipient = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
            if recipient and recipient.get('notification_preferences', {}).get('email', True):
                send_support_ticket_reply_email(recipient, ticket_id, ticket['subject'], message)
        
        response = jsonify({'success': True, 'message': 'Reply sent'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== REFERRAL DASHBOARD ====================
@app.route('/api/referrals', methods=['GET', 'OPTIONS'])
def get_referrals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        referred_users = users_collection.find({'referred_by': str(user['_id'])})
        referrals_list = []
        total_earnings = 0
        
        for ref in referred_users:
            stats = referral_stats_collection.find_one({'user_id': str(ref['_id'])}) if referral_stats_collection else None
            earning = stats.get('total_earnings', 0) if stats else 0
            total_earnings += earning
            referrals_list.append({
                'username': ref['username'],
                'email': ref['email'],
                'joined_at': ref['created_at'].isoformat() if ref.get('created_at') else None,
                'total_deposited': ref.get('wallet', {}).get('total_deposited', 0),
                'earnings': earning
            })
        
        response_data = {
            'referral_code': user.get('referral_code', ''),
            'referral_link': f"{FRONTEND_URL}/register?ref={user.get('referral_code', '')}",
            'total_referrals': len(referrals_list),
            'total_earnings': total_earnings,
            'referrals': referrals_list
        }
        
        response = jsonify({'success': True, 'data': response_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get referrals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== TRANSACTION FILTERS & EXPORT ====================
@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_filtered_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        type_filter = request.args.get('type', 'all')
        status_filter = request.args.get('status', 'all')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        export = request.args.get('export', 'false') == 'true'
        
        skip = (page - 1) * limit
        
        query = {'user_id': str(user['_id'])}
        
        if type_filter != 'all':
            query['type'] = type_filter
        if status_filter != 'all':
            query['status'] = status_filter
        if start_date:
            query['created_at'] = {'$gte': datetime.fromisoformat(start_date)}
        if end_date:
            end = datetime.fromisoformat(end_date)
            query['created_at'] = {**query.get('created_at', {}), '$lte': end.replace(hour=23, minute=59, second=59)}
        
        total = transactions_collection.count_documents(query)
        transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()
        
        # Export to CSV if requested
        if export:
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Date', 'Type', 'Amount', 'Status', 'Description'])
            for tx in transactions:
                writer.writerow([
                    tx.get('created_at', ''),
                    tx.get('type', ''),
                    tx.get('amount', 0),
                    tx.get('status', ''),
                    tx.get('description', '')
                ])
            
            output.seek(0)
            return send_file(
                BytesIO(output.getvalue().encode('utf-8')),
                mimetype='text/csv',
                as_attachment=True,
                download_name='transactions.csv'
            )
        
        response = jsonify({
            'success': True,
            'data': {
                'transactions': transactions,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get transactions error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== NOTIFICATION PREFERENCES ====================
@app.route('/api/notifications/preferences', methods=['PUT', 'OPTIONS'])
def update_notification_preferences():
    if request.method == 'OPTIONS':
        return handle_preflight()
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        data = request.get_json()
        preferences = user.get('notification_preferences', {})
        preferences.update({
            'email': data.get('email', preferences.get('email', True)),
            'push': data.get('push', preferences.get('push', True))
        })
        
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'notification_preferences': preferences}}
        )
        
        response = jsonify({'success': True, 'message': 'Preferences updated'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Update preferences error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== INVESTMENT CALCULATOR ====================
@app.route('/api/calculator', methods=['POST', 'OPTIONS'])
def investment_calculator():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        plan_type = data.get('plan_type')
        amount = float(data.get('amount', 0))
        
        plan = INVESTMENT_PLANS.get(plan_type)
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid plan'}), 400
        
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum amount is ${plan["min_deposit"]}'}), 400
        if amount > plan['max_deposit'] and plan['max_deposit'] != float('inf'):
            return jsonify({'success': False, 'message': f'Maximum amount is ${plan["max_deposit"]}'}), 400
        
        expected_profit = amount * plan['roi'] / 100
        total_return = amount + expected_profit
        
        response = jsonify({
            'success': True,
            'data': {
                'plan_name': plan['name'],
                'amount': amount,
                'roi': plan['roi'],
                'duration_hours': plan['duration_hours'],
                'expected_profit': expected_profit,
                'total_return': total_return
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Calculator error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== CREATE TRANSACTION (Admin) ====================
@app.route('/api/admin/transactions/create', methods=['POST', 'OPTIONS'])
@require_admin
def admin_create_transaction():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        transaction_type = data.get('type')
        amount = float(data.get('amount', 0))
        description = data.get('description', '')
        send_email_notification = data.get('send_email', True)
        
        if not user_id or not transaction_type or amount <= 0:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Calculate balance change
        balance_change = 0
        if transaction_type in ['deposit', 'profit', 'credit']:
            balance_change = amount
        elif transaction_type in ['withdrawal', 'debit']:
            balance_change = -amount
        
        if balance_change != 0:
            new_balance = user['wallet']['balance'] + balance_change
            users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$inc': {'wallet.balance': balance_change}}
            )
            
            # Update totals if deposit
            if transaction_type == 'deposit':
                users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.total_deposited': amount}}
                )
            elif transaction_type == 'withdrawal':
                users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.total_withdrawn': amount}}
                )
            elif transaction_type == 'profit':
                users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.total_profit': amount}}
                )
        
        # Create transaction record
        transaction = {
            'user_id': str(user_id),
            'type': transaction_type,
            'amount': amount,
            'status': 'completed',
            'description': description,
            'created_at': datetime.now(timezone.utc)
        }
        transactions_collection.insert_one(transaction)
        
        create_notification(user_id, f'{transaction_type.capitalize()} Transaction', 
                           f'A {transaction_type} of ${amount:,.2f} has been processed. Description: {description}', 'success')
        
        # Send email notification if requested
        if send_email_notification and user.get('notification_preferences', {}).get('email', True):
            new_balance = user['wallet']['balance'] + (balance_change if balance_change != 0 else 0)
            send_transaction_confirmation_email(user, transaction_type, amount, description, new_balance)
        
        admin_user = get_user_from_request()
        if admin_user:
            log_admin_action(admin_user['_id'], 'create_transaction', 
                           f'Created {transaction_type} of ${amount} for user {user["username"]}')
        
        response = jsonify({'success': True, 'message': 'Transaction created successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: KYC MANAGEMENT ====================
@app.route('/api/admin/kyc', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        status_filter = request.args.get('status', 'all')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        query = {}
        if status_filter != 'all':
            query['status'] = status_filter
        
        total = kyc_collection.count_documents(query)
        kyc_requests = list(kyc_collection.find(query).sort('submitted_at', -1).skip(skip).limit(limit))
        
        for kyc in kyc_requests:
            kyc['_id'] = str(kyc['_id'])
            if 'submitted_at' in kyc:
                kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        
        response = jsonify({
            'success': True,
            'data': {
                'requests': kyc_requests,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/kyc/<kyc_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_kyc(kyc_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        action = data.get('action')
        reason = data.get('reason', '')
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC request not found'}), 404
        
        status = 'approved' if action == 'approve' else 'rejected'
        
        kyc_collection.update_one(
            {'_id': ObjectId(kyc_id)},
            {
                '$set': {
                    'status': status,
                    'rejection_reason': reason if status == 'rejected' else None,
                    'reviewed_at': datetime.now(timezone.utc),
                    'reviewed_by': str(get_user_from_request()['_id'])
                }
            }
        )
        
        users_collection.update_one(
            {'_id': ObjectId(kyc['user_id'])},
            {'$set': {'kyc_status': status, 'is_verified': status == 'approved'}}
        )
        
        user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
        if user:
            send_kyc_status_email(user, status, reason)
            create_notification(user['_id'], f'KYC {status.capitalize()}', 
                               f'Your KYC verification has been {status}. {reason if reason else ""}', 
                               'success' if status == 'approved' else 'error')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], f'process_kyc_{action}', f'Processed KYC for user {kyc["username"]}')
        
        response = jsonify({'success': True, 'message': f'KYC {status}'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: SUPPORT TICKETS ====================
@app.route('/api/admin/tickets', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_tickets():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        status_filter = request.args.get('status', 'all')
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        query = {}
        if status_filter != 'all':
            query['status'] = status_filter
        
        total = support_tickets_collection.count_documents(query)
        tickets = list(support_tickets_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if 'created_at' in ticket:
                ticket['created_at'] = ticket['created_at'].isoformat()
        
        response = jsonify({
            'success': True,
            'data': {
                'tickets': tickets,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Admin get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/tickets/<ticket_id>/close', methods=['POST', 'OPTIONS'])
@require_admin
def admin_close_ticket(ticket_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {'$set': {'status': 'closed', 'updated_at': datetime.now(timezone.utc)}}
        )
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'close_ticket', f'Closed ticket {ticket_id}')
        
        response = jsonify({'success': True, 'message': 'Ticket closed'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Close ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: SYSTEM LOGS ====================
@app.route('/api/admin/logs', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_logs():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        action_filter = request.args.get('action', '')
        skip = (page - 1) * limit
        
        query = {}
        if action_filter:
            query['action'] = {'$regex': action_filter, '$options': 'i'}
        
        total = admin_logs_collection.count_documents(query)
        logs = list(admin_logs_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for log in logs:
            log['_id'] = str(log['_id'])
            if 'created_at' in log:
                log['created_at'] = log['created_at'].isoformat()
        
        response = jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get logs error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: REFERRAL STATISTICS ====================
@app.route('/api/admin/referrals/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_referral_stats():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        # Get users with referrals
        users_with_refs = list(users_collection.find(
            {'referrals': {'$exists': True, '$ne': []}}
        ).sort('created_at', -1).skip(skip).limit(limit))
        
        total = users_collection.count_documents({'referrals': {'$exists': True, '$ne': []}})
        
        referral_data = []
        for user in users_with_refs:
            # Calculate total earnings from referrals
            total_earnings = 0
            for ref_username in user.get('referrals', []):
                ref_user = users_collection.find_one({'username': ref_username})
                if ref_user:
                    ref_stats = referral_stats_collection.find_one({'user_id': str(ref_user['_id'])}) if referral_stats_collection else None
                    total_earnings += ref_stats.get('total_earnings', 0) if ref_stats else 0
            
            referral_data.append({
                'user_id': str(user['_id']),
                'username': user['username'],
                'referral_code': user.get('referral_code', ''),
                'referral_count': len(user.get('referrals', [])),
                'referrals': user.get('referrals', []),
                'total_earnings': total_earnings,
                'joined_at': user.get('created_at').isoformat() if user.get('created_at') else None
            })
        
        response = jsonify({
            'success': True,
            'data': {
                'referrals': referral_data,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get referral stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: PLATFORM SETTINGS ====================
@app.route('/api/admin/settings', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_settings():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        settings = settings_collection.find_one({})
        if settings:
            settings['_id'] = str(settings['_id'])
        response = jsonify({'success': True, 'data': settings or PLATFORM_SETTINGS})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get settings error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/settings', methods=['PUT', 'OPTIONS'])
@require_admin
def admin_update_settings():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        
        settings_collection.update_one(
            {},
            {'$set': data},
            upsert=True
        )
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'update_settings', f'Updated platform settings: {list(data.keys())}')
        
        response = jsonify({'success': True, 'message': 'Settings updated'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Update settings error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN: INVESTMENT PLANS ====================
@app.route('/api/admin/plans', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_plans():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    response = jsonify({'success': True, 'data': INVESTMENT_PLANS})
    return add_cors_headers(response)

@app.route('/api/admin/plans/<plan_id>', methods=['PUT', 'OPTIONS'])
@require_admin
def admin_update_plan(plan_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        data = request.get_json()
        
        if plan_id not in INVESTMENT_PLANS:
            return jsonify({'success': False, 'message': 'Plan not found'}), 404
        
        INVESTMENT_PLANS[plan_id].update(data)
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'update_plan', f'Updated plan {plan_id}')
        
        response = jsonify({'success': True, 'message': 'Plan updated'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Update plan error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== EMAIL LOGS ====================
@app.route('/api/admin/email-logs', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_email_logs():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        skip = (page - 1) * limit
        
        total = email_logs_collection.count_documents({})
        logs = list(email_logs_collection.find({}).sort('created_at', -1).skip(skip).limit(limit))
        
        for log in logs:
            log['_id'] = str(log['_id'])
            if 'created_at' in log:
                log['created_at'] = log['created_at'].isoformat()
        
        response = jsonify({
            'success': True,
            'data': {
                'logs': logs,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get email logs error: {e}")
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
    print("🚀 VELOXTRADES API SERVER - FULL FEATURE READY")
    print("=" * 70)
    print(f"📊 MongoDB Status: {'Connected' if users_collection is not None else 'Disconnected'}")
    print("📧 Email Service: Configured with logging")
    print("👑 Admin Dashboard: Full management features")
    print("📋 KYC Verification: Enabled")
    print("🎫 Support Tickets: Enabled")
    print("📊 Referral System: Enabled")
    print("📧 Email Logs: Enabled")
    print("=" * 70)
    print("📝 TO CREATE ADMIN:")
    print(f"   Visit: {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
