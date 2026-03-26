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
        if users_collection is not None:
            users_collection.create_index('email', unique=True, sparse=True)
            users_collection.create_index('username', unique=True, sparse=True)
            users_collection.create_index('referral_code', unique=True, sparse=True)
        if transactions_collection is not None:
            transactions_collection.create_index('user_id')
            transactions_collection.create_index('created_at')
        if support_tickets_collection is not None:
            support_tickets_collection.create_index('user_id')
            support_tickets_collection.create_index('status')
        
        # Initialize settings if not exists
        if settings_collection is not None and settings_collection.count_documents({}) == 0:
            settings_collection.insert_one(PLATFORM_SETTINGS)
            logger.info("✅ Default settings created")
        
        logger.info("✅ MongoDB Connected Successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB Connection Error: {e}")
        logger.error(traceback.format_exc())
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
    return add_cors_headers(response)

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

def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email with logging and retry logic"""
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

# ==================== EMAIL TEMPLATES ====================
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

def send_deposit_approved_email(user, amount, crypto, transaction_hash):
    subject = f"✅ Deposit Approved - ${amount} added to your Veloxtrades account"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ Deposit Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Method: <strong>{crypto.upper()}</strong></p>
        <p>Transaction ID: <strong>{transaction_hash or 'N/A'}</strong></p>
    </div>
    <p>Your deposit has been successfully added to your wallet balance.</p>
    <p>You can now start investing with your funds.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your deposit of ${amount:,.2f} has been approved.", html_body)

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount} deposit was not approved"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
        <p><strong>❌ Deposit Rejected</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Method: <strong>{crypto.upper()}</strong></p>
        <p>Reason: <strong>{reason}</strong></p>
    </div>
    <p>Your deposit request was not approved. Please contact support if you have any questions.</p>
    <p>You can submit a new deposit request at any time.</p>
    '''
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your deposit of ${amount:,.2f} was rejected. Reason: {reason}", html_body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount} sent to your wallet"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ Withdrawal Approved!</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Currency: <strong>{currency.upper()}</strong></p>
        <p>Wallet Address: <strong>{wallet_address}</strong></p>
    </div>
    <p>Your withdrawal has been processed and sent to your wallet. Funds should reflect within a few hours.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your withdrawal of ${amount:,.2f} has been approved.", html_body)

def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount} withdrawal request"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
        <p><strong>❌ Withdrawal Rejected</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>Currency: <strong>{currency.upper()}</strong></p>
        <p>Reason: <strong>{reason}</strong></p>
    </div>
    <p>Your withdrawal request was not approved. The funds have been returned to your wallet.</p>
    <p>Please ensure your wallet address is correct and try again.</p>
    '''
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your withdrawal of ${amount:,.2f} was rejected. Reason: {reason}", html_body)

def send_investment_confirmation_email(user, amount, plan_name, roi, expected_profit):
    subject = f"🚀 Investment Confirmed - ${amount} invested in {plan_name}"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ Investment Started!</strong></p>
        <p>Plan: <strong>{plan_name}</strong></p>
        <p>Amount: <strong>${amount:,.2f}</strong></p>
        <p>ROI: <strong>{roi}%</strong></p>
        <p>Expected Profit: <strong>${expected_profit:,.2f}</strong></p>
        <p>Total Return: <strong>${(amount + expected_profit):,.2f}</strong></p>
    </div>
    <p>Your investment is now active and will automatically complete at the end of the duration.</p>
    <p>You will receive another email when your investment completes with your profit.</p>
    '''
    html_body = get_email_template(subject, content, 'View Investments', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your investment of ${amount:,.2f} in {plan_name} has started.", html_body)

def send_investment_completed_email(user, amount, plan_name, profit):
    subject = f"✅ Investment Completed - You earned ${profit:,.2f}!"
    content = f'''
    <p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>🎉 Investment Completed!</strong></p>
        <p>Plan: <strong>{plan_name}</strong></p>
        <p>Initial Investment: <strong>${amount:,.2f}</strong></p>
        <p>Profit Earned: <strong>${profit:,.2f}</strong></p>
        <p>Total Return: <strong>${(amount + profit):,.2f}</strong></p>
    </div>
    <p>Your investment has been successfully completed. The profit has been added to your wallet balance.</p>
    <p>You can start a new investment or withdraw your funds.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, f"Your investment of ${amount:,.2f} has completed. You earned ${profit:,.2f} profit!", html_body)

# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    """Process completed investments and add profits to user wallets"""
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
                user = users_collection.find_one({'_id': ObjectId(user_id)})
                amount = investment['amount']
                expected_profit = investment.get('expected_profit', 0)
                plan_name = investment.get('plan_name', 'Investment')
                
                result = users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.balance': expected_profit, 'wallet.total_profit': expected_profit}}
                )
                
                if result.modified_count > 0:
                    investments_collection.update_one(
                        {'_id': investment['_id']},
                        {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}}
                    )
                    
                    if transactions_collection is not None:
                        transactions_collection.insert_one({
                            'user_id': user_id, 'type': 'profit', 'amount': expected_profit,
                            'status': 'completed', 'description': f'Profit from {plan_name}',
                            'investment_id': str(investment['_id']), 'created_at': datetime.now(timezone.utc)
                        })
                    
                    # Send notification
                    create_notification(user_id, 'Investment Completed! 🎉',
                        f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!', 'success')
                    
                    # Send email confirmation
                    if user:
                        try:
                            send_investment_completed_email(user, amount, plan_name, expected_profit)
                        except Exception as e:
                            logger.error(f"Failed to send investment completion email: {e}")
                    
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

        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
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
            'referral_code': referral_code, 'referrals': [], 'kyc_status': 'pending'
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
            'is_admin': user.get('is_admin', False), 'kyc_status': user.get('kyc_status', 'pending')
        }

        response = make_response(jsonify({'success': True, 'message': 'Login successful!', 'data': {'token': token, 'user': user_data}}))
        response.set_cookie('veloxtrades_token', value=token, httponly=True, secure=True, samesite='Lax', 
                           max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        
        return add_cors_headers(response), 200
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
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

# ==================== USER DEPOSITS ====================
@app.route('/api/deposits', methods=['POST', 'OPTIONS'])
def create_deposit():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if deposits_collection is None or users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        crypto = data.get('crypto', 'usdt')
        transaction_hash = data.get('transaction_hash', '').strip()
        wallet_address = data.get('wallet_address', '')
        
        # Get settings
        settings = None
        if settings_collection is not None:
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
            'wallet_address': wallet_address,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc),
            'approved_at': None,
            'rejected_at': None,
            'rejection_reason': None
        }
        
        deposits_collection.insert_one(deposit_data)
        
        # Record transaction
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']),
                'type': 'deposit',
                'amount': amount,
                'status': 'pending',
                'description': f'Deposit request of ${amount:,.2f} via {crypto.upper()}',
                'deposit_id': deposit_id,
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user['_id'], 'Deposit Request Submitted', 
            f'Your deposit request of ${amount:,.2f} has been submitted and is pending approval.', 'info')
        
        response = jsonify({'success': True, 'message': 'Deposit request submitted', 
                           'data': {'deposit_id': deposit_id}})
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"Create deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/deposits', methods=['GET', 'OPTIONS'])
def get_user_deposits():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        deposits = []
        if deposits_collection is not None:
            deposits = list(deposits_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        
        for deposit in deposits:
            deposit['_id'] = str(deposit['_id'])
            if 'created_at' in deposit:
                deposit['created_at'] = deposit['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': {'deposits': deposits}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== USER WITHDRAWALS ====================
@app.route('/api/withdrawals', methods=['POST', 'OPTIONS'])
def create_withdrawal():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if withdrawals_collection is None or users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        currency = data.get('currency', 'usdt')
        wallet_address = data.get('wallet_address', '').strip()
        
        if not wallet_address:
            return jsonify({'success': False, 'message': 'Wallet address is required'}), 400
        
        # Get settings
        settings = None
        if settings_collection is not None:
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
        
        # Deduct from wallet immediately for pending withdrawal
        users_collection.update_one(
            {'_id': user['_id']},
            {'$inc': {'wallet.balance': -amount}}
        )
        
        # Record transaction
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']),
                'type': 'withdrawal',
                'amount': amount,
                'status': 'pending',
                'description': f'Withdrawal request of ${amount:,.2f} to {currency.upper()}',
                'withdrawal_id': withdrawal_id,
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user['_id'], 'Withdrawal Request Submitted', 
            f'Your withdrawal request of ${amount:,.2f} has been submitted and is pending approval.', 'info')
        
        response = jsonify({'success': True, 'message': 'Withdrawal request submitted', 
                           'data': {'withdrawal_id': withdrawal_id}})
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"Create withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/withdrawals', methods=['GET', 'OPTIONS'])
def get_user_withdrawals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        withdrawals = []
        if withdrawals_collection is not None:
            withdrawals = list(withdrawals_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        
        for withdrawal in withdrawals:
            withdrawal['_id'] = str(withdrawal['_id'])
            if 'created_at' in withdrawal:
                withdrawal['created_at'] = withdrawal['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': {'withdrawals': withdrawals}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== USER INVESTMENTS ====================
@app.route('/api/invest', methods=['POST', 'OPTIONS'])
def create_investment():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if investments_collection is None or users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        plan_type = data.get('plan') or data.get('plan_type')
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
        
        # Deduct from wallet
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
        
        # Record transaction
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']),
                'type': 'investment',
                'amount': amount,
                'status': 'completed',
                'description': f'Investment in {plan["name"]}',
                'investment_id': str(result.inserted_id),
                'created_at': datetime.now(timezone.utc)
            })
        
        # Send notification
        create_notification(user['_id'], 'Investment Started!', 
            f'You have invested ${amount:,.2f} in {plan["name"]}. Expected profit: ${expected_profit:,.2f}', 'success')
        
        # Send email confirmation
        try:
            send_investment_confirmation_email(user, amount, plan['name'], plan['roi'], expected_profit)
        except Exception as e:
            logger.error(f"Failed to send investment confirmation email: {e}")
        
        response = jsonify({'success': True, 'message': 'Investment successful', 
                           'data': {'expected_profit': expected_profit, 'end_date': end_date.isoformat()}})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Investment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/investments', methods=['GET', 'OPTIONS'])
def get_user_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        investments = []
        if investments_collection is not None:
            investments = list(investments_collection.find({'user_id': str(user['_id'])}).sort('start_date', -1))
        
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if 'start_date' in inv and inv['start_date']:
                inv['start_date'] = inv['start_date'].isoformat()
            if 'end_date' in inv and inv['end_date']:
                inv['end_date'] = inv['end_date'].isoformat()
        
        response = jsonify({'success': True, 'data': {'investments': investments}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get investments error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== USER TRANSACTIONS ====================
@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        transactions = []
        if transactions_collection is not None:
            transactions = list(transactions_collection.find(
                {'user_id': str(user['_id'])}
            ).sort('created_at', -1))
        
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': {'transactions': transactions}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get transactions error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== USER DASHBOARD ====================
@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def user_dashboard():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # Get active investments
        active_investments = []
        if investments_collection is not None:
            active_investments = list(investments_collection.find({'user_id': str(user['_id']), 'status': 'active'}))
        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)
        
        # Get recent transactions
        recent_transactions = []
        if transactions_collection is not None:
            recent_transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).limit(10))
        for tx in recent_transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()
        
        # Get unread notifications count
        unread_count = 0
        if notifications_collection is not None:
            unread_count = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
        
        # Get pending counts
        pending_deposits = 0
        if deposits_collection is not None:
            pending_deposits = deposits_collection.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
        
        pending_withdrawals = 0
        if withdrawals_collection is not None:
            pending_withdrawals = withdrawals_collection.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
        
        dashboard_data = {
            'wallet': user.get('wallet', {'balance': 0.00, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0}),
            'investments': {
                'total_active': total_active,
                'total_profit': user.get('wallet', {}).get('total_profit', 0),
                'pending_profit': pending_profit,
                'count': len(active_investments)
            },
            'recent_transactions': recent_transactions,
            'notification_count': unread_count,
            'kyc_status': user.get('kyc_status', 'pending'),
            'pending_requests': {
                'deposits': pending_deposits,
                'withdrawals': pending_withdrawals
            }
        }
        
        response = jsonify({'success': True, 'data': dashboard_data})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== USER NOTIFICATIONS ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if notifications_collection is None:
        return jsonify({'success': True, 'data': {'notifications': [], 'total': 0, 'unread': 0, 'page': 1, 'pages': 1}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        notifications = list(notifications_collection.find(
            {'user_id': str(user['_id'])}
        ).sort('created_at', -1).skip(skip).limit(limit))
        
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
    
    if notifications_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
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

# ==================== ADMIN API ENDPOINTS ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    try:
        total_users = users_collection.count_documents({}) if users_collection is not None else 0
        total_deposit_amount = 0
        total_withdrawal_amount = 0
        active_investments = 0
        pending_deposits = 0
        pending_withdrawals = 0
        banned_users = users_collection.count_documents({'is_banned': True}) if users_collection is not None else 0
        
        if deposits_collection is not None:
            approved_deposits = list(deposits_collection.find({'status': 'approved'}))
            total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
            pending_deposits = deposits_collection.count_documents({'status': 'pending'})
        
        if withdrawals_collection is not None:
            approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
            total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
            pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
        
        if investments_collection is not None:
            active_investments = investments_collection.count_documents({'status': 'active'})
        
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
        return jsonify({'success': True, 'data': {
            'total_users': 0, 'total_deposit_amount': 0, 'total_withdrawal_amount': 0,
            'active_investments': 0, 'pending_deposits': 0, 'pending_withdrawals': 0, 'banned_users': 0
        }}), 200

@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error', 'data': {'users': [], 'total': 0}}), 500
    
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
                'last_login': user.get('last_login').isoformat() if user.get('last_login') else None,
                'referral_code': user.get('referral_code', ''),
                'referrals': user.get('referrals', [])
            }
            formatted_users.append(user_data)
        
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        response = jsonify({
            'success': True,
            'data': {
                'users': formatted_users,
                'total': total,
                'page': page,
                'pages': total_pages,
                'limit': limit
            }
        })
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get users error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e), 'data': {'users': [], 'total': 0}}), 500

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
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        current_balance = user.get('wallet', {}).get('balance', 0)
        new_balance = current_balance + amount
        
        result = users_collection.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        
        if result.modified_count == 0:
            return jsonify({'success': False, 'message': 'Failed to update balance'}), 500
        
        if transactions_collection is not None:
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
        
        if investments_collection is not None:
            investments_collection.delete_many({'user_id': str(user_id)})
        if transactions_collection is not None:
            transactions_collection.delete_many({'user_id': str(user_id)})
        if deposits_collection is not None:
            deposits_collection.delete_many({'user_id': str(user_id)})
        if withdrawals_collection is not None:
            withdrawals_collection.delete_many({'user_id': str(user_id)})
        if notifications_collection is not None:
            notifications_collection.delete_many({'user_id': str(user_id)})
        
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        response = jsonify({'success': True, 'message': f'User {username} permanently deleted'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_deposits():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if deposits_collection is None:
        return jsonify({'success': True, 'data': {'deposits': [], 'total': 0}}), 200
    
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
        return jsonify({'success': True, 'data': {'deposits': [], 'total': 0}}), 200

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
        reason = data.get('reason', 'Not specified')
        
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
            
            if transactions_collection is not None:
                transactions_collection.insert_one({
                    'user_id': deposit['user_id'], 'type': 'deposit', 'amount': deposit['amount'],
                    'status': 'completed', 'description': f'Deposit of ${deposit["amount"]} via {deposit["crypto"]} approved',
                    'created_at': datetime.now(timezone.utc)
                })
            
            create_notification(deposit['user_id'], 'Deposit Approved! ✅', 
                f'Your deposit of ${deposit["amount"]:,.2f} via {deposit["crypto"]} has been approved and added to your wallet.', 'success')
            
            try:
                send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
            except Exception as e:
                logger.error(f"Failed to send deposit approval email: {e}")
            
            message = 'Deposit approved successfully'
            
        elif action == 'reject':
            reason = data.get('reason', 'Not specified')
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'processed_at': datetime.now(timezone.utc)}})
            
            if transactions_collection is not None:
                transactions_collection.insert_one({
                    'user_id': deposit['user_id'], 'type': 'deposit', 'amount': deposit['amount'],
                    'status': 'failed', 'description': f'Deposit of ${deposit["amount"]} rejected: {reason}',
                    'created_at': datetime.now(timezone.utc)
                })
            
            create_notification(deposit['user_id'], 'Deposit Rejected ❌', 
                f'Your deposit of ${deposit["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            
            try:
                send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], reason)
            except Exception as e:
                logger.error(f"Failed to send deposit rejection email: {e}")
            
            message = 'Deposit rejected'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_withdrawals():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if withdrawals_collection is None:
        return jsonify({'success': True, 'data': {'withdrawals': [], 'total': 0}}), 200
    
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
        return jsonify({'success': True, 'data': {'withdrawals': [], 'total': 0}}), 200

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
        reason = data.get('reason', 'Not specified')
        
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Withdrawal already processed'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        
        if action == 'approve':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved', 'processed_at': datetime.now(timezone.utc)}})
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'user_id': withdrawal['user_id'], 'type': 'withdrawal', 'status': 'pending'},
                    {'$set': {'status': 'completed', 'description': f'Withdrawal of ${withdrawal["amount"]} approved and sent'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(withdrawal['user_id'], 'Withdrawal Approved! ✅', 
                f'Your withdrawal of ${withdrawal["amount"]:,.2f} has been approved and sent to your wallet.', 'success')
            
            try:
                send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
            except Exception as e:
                logger.error(f"Failed to send withdrawal approval email: {e}")
            
            message = 'Withdrawal approved successfully'
            
        elif action == 'reject':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'processed_at': datetime.now(timezone.utc)}})
            
            # Refund the amount back to user
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {'$inc': {'wallet.balance': withdrawal['amount']}}
            )
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'user_id': withdrawal['user_id'], 'type': 'withdrawal', 'status': 'pending'},
                    {'$set': {'status': 'failed', 'description': f'Withdrawal of ${withdrawal["amount"]} rejected: {reason}'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(withdrawal['user_id'], 'Withdrawal Rejected ❌', 
                f'Your withdrawal of ${withdrawal["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            
            try:
                send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
            except Exception as e:
                logger.error(f"Failed to send withdrawal rejection email: {e}")
            
            message = 'Withdrawal rejected'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if investments_collection is None:
        return jsonify({'success': True, 'data': {'investments': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = investments_collection.count_documents(query)
        investments = list(investments_collection.find(query).sort('start_date', -1).skip(skip).limit(limit))
        
        result_investments = []
        for inv in investments:
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
        return jsonify({'success': True, 'data': {'investments': [], 'total': 0}}), 200

@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_transactions():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    if transactions_collection is None:
        return jsonify({'success': True, 'data': {'transactions': [], 'total': 0}}), 200
    
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
        return jsonify({'success': True, 'data': {'transactions': [], 'total': 0}}), 200

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
            if investments_collection is not None:
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
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
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
    print("🚀 VELOXTRADES API SERVER - READY")
    print("=" * 70)
    print(f"📊 MongoDB Status: {'Connected' if users_collection is not None else 'Disconnected'}")
    print("📧 Email Service: Configured")
    print("👑 Admin Dashboard Ready")
    print("=" * 70)
    print("📝 TO CREATE ADMIN:")
    print(f"   Visit: {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
