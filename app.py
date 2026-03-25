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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler

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

def send_email(to_email, subject, body, html_body=None):
    """Send email to user"""
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        
        part1 = MIMEText(body, 'plain')
        msg.attach(part1)
        
        if html_body:
            part2 = MIMEText(html_body, 'html')
            msg.attach(part2)
        
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"✅ Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"❌ Email error: {e}")
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

def send_investment_paid_email(user, investment_amount, profit, plan_name):
    subject = f"💰 Investment Profit Paid - ${profit:,.2f} credited!"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour investment profit has been paid!\n\nInvestment: {plan_name}\nOriginal Amount: ${investment_amount:,.2f}\nProfit Earned: ${profit:,.2f}\nTotal Received: ${investment_amount + profit:,.2f}\n\nThank you for choosing Veloxtrades!\n\nBest regards,\nVeloxtrades Team"
    return send_email(user['email'], subject, body)

# ==================== CORS CONFIGURATION ====================
CORS(app, 
     supports_credentials=True,
     origins=ALLOWED_ORIGINS,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=3600)

@app.before_request
def handle_preflight():
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS:
            response.headers.add('Access-Control-Allow-Origin', origin)
        else:
            response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, PATCH')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Max-Age', '3600')
        return response

def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if origin in ALLOWED_ORIGINS:
        response.headers.add('Access-Control-Allow-Origin', origin)
    else:
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

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

# MongoDB Connection
try:
    client = MongoClient(app.config['MONGO_URI'])
    db = client['veloxtrades_db']
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
    raise

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
    token = request.cookies.get('veloxtrades_token') or request.cookies.get('elite_token')
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
        return users_collection.find_one({'_id': ObjectId(payload['user_id'])})
    except Exception as e:
        logger.error(f"⚠️ Get user error: {e}")
        return None

def require_admin(f):
    def decorated_function(*args, **kwargs):
        user = get_user_from_request()
        if not user or not user.get('is_admin', False):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def create_notification(user_id, title, message, type='info'):
    return notifications_collection.insert_one({
        'user_id': str(user_id), 'title': title, 'message': message,
        'type': type, 'read': False, 'created_at': datetime.now(timezone.utc)
    })

def log_admin_action(admin_id, action, details):
    admin_logs_collection.insert_one({
        'admin_id': str(admin_id), 'action': action, 'details': details,
        'ip_address': request.remote_addr, 'created_at': datetime.now(timezone.utc)
    })

# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    try:
        logger.info("🔄 Processing investment profits...")
        active_investments = list(investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        }))
        
        for investment in active_investments:
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
                    
                    logger.info(f"✅ Processed profit for investment {investment['_id']}")
            except Exception as e:
                logger.error(f"❌ Error processing investment {investment['_id']}: {e}")
    except Exception as e:
        logger.error(f"❌ Error in profit processing: {e}")

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=process_investment_profits, trigger="interval", hours=1, id="profit_processor", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())
logger.info("✅ Auto-profit scheduler started")

# ==================== FRONTEND ROUTES ====================
@app.route('/')
def serve_index():
    response = jsonify({
        'success': True, 'message': 'Veloxtrades API Server',
        'frontend': FRONTEND_URL, 'frontend_non_www': FRONTEND_URL_NON_WWW,
        'backend': BACKEND_URL, 'allowed_origins': ALLOWED_ORIGINS,
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login', '/api/auth/register', '/api/verify-token']
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
    response = jsonify({
        'success': True, 'status': 'healthy', 'timestamp': datetime.now(timezone.utc).isoformat(),
        'mongo': 'connected', 'email': 'configured', 'frontend_url': FRONTEND_URL, 'backend_url': BACKEND_URL
    })
    return add_cors_headers(response)

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
        logger.error(f"❌ Registration error: {e}")
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
        response.set_cookie('veloxtrades_token', value=token, httponly=True, secure=True, samesite='Lax', max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        response.set_cookie('elite_token', value=token, httponly=True, secure=True, samesite='Lax', max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        return add_cors_headers(response), 200
    except Exception as e:
        logger.error(f"❌ Login error: {e}")
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
        deposit = {
            'user_id': str(user['_id']), 'amount': float(data.get('amount', 0)), 'crypto': data.get('crypto', ''),
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
        current_balance = user.get('wallet', {}).get('balance', 0)
        if amount > current_balance:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        if amount < 50:
            return jsonify({'success': False, 'message': 'Minimum withdrawal is $50'}), 400
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
        users_collection.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}})
        investment = {
            'user_id': str(user['_id']), 'plan_name': plan['name'], 'plan_type': plan_type, 'amount': amount,
            'expected_profit': expected_profit, 'roi': plan['roi'], 'duration_hours': plan['duration_hours'],
            'status': 'active', 'start_date': datetime.now(timezone.utc), 'end_date': end_date, 'created_at': datetime.now(timezone.utc)
        }
        result = investments_collection.insert_one(investment)
        transactions_collection.insert_one({'user_id': str(user['_id']), 'type': 'investment', 'amount': amount,
            'status': 'completed', 'description': f'Investment in {plan["name"]}', 'investment_id': str(result.inserted_id), 'created_at': datetime.now(timezone.utc)})
        create_notification(user['_id'], 'Investment Created! 🚀', f'Your investment of ${amount:,.2f} in {plan["name"]} has been started. Expected profit: ${expected_profit:,.2f}', 'success')
        send_investment_created_email(user, amount, plan['name'], expected_profit)
        updated_user = users_collection.find_one({'_id': user['_id']})
        new_balance = updated_user.get('wallet', {}).get('balance', 0)
        response = jsonify({'success': True, 'message': 'Investment created successfully',
            'data': {'investment_id': str(result.inserted_id), 'new_balance': new_balance, 'expected_profit': expected_profit}})
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
        total_users = users_collection.count_documents({})
        approved_deposits = list(deposits_collection.find({'status': 'approved'}))
        total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
        approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
        total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
        active_investments = investments_collection.count_documents({'status': 'active'})
        pending_deposits = deposits_collection.count_documents({'status': 'pending'})
        pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
        banned_users = users_collection.count_documents({'is_banned': True})
        response = jsonify({'success': True, 'data': {
            'total_users': total_users,
            'total_deposit_amount': total_deposit_amount,
            'total_withdrawal_amount': total_withdrawal_amount,
            'active_investments': active_investments,
            'pending_deposits': pending_deposits,
            'pending_withdrawals': pending_withdrawals,
            'banned_users': banned_users
        }})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        
        total = transactions_collection.count_documents(query)
        transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_transactions = []
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx and isinstance(tx['created_at'], datetime):
                tx['created_at'] = tx['created_at'].isoformat()
            
            user = users_collection.find_one({'_id': ObjectId(tx['user_id'])})
            tx['user'] = {
                'username': user.get('username', 'Unknown') if user else 'Unknown',
                'email': user.get('email', '') if user else ''
            }
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
        logger.error(f"Get admin transactions error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
            if 'created_at' in user and isinstance(user['created_at'], datetime):
                user['created_at'] = user['created_at'].isoformat()
            if 'last_login' in user and isinstance(user['last_login'], datetime):
                user['last_login'] = user['last_login'].isoformat()
        response = jsonify({'success': True, 'data': {
            'users': users,
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit if total > 0 else 1
        }})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        result_deposits = []
        for deposit in deposits:
            deposit['_id'] = str(deposit['_id'])
            if 'created_at' in deposit and isinstance(deposit['created_at'], datetime):
                deposit['created_at'] = deposit['created_at'].isoformat()
            user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
            deposit['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_deposits.append(deposit)
        response = jsonify({'success': True, 'data': {
            'deposits': result_deposits,
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit if total > 0 else 1
        }})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        result_withdrawals = []
        for withdrawal in withdrawals:
            withdrawal['_id'] = str(withdrawal['_id'])
            if 'created_at' in withdrawal and isinstance(withdrawal['created_at'], datetime):
                withdrawal['created_at'] = withdrawal['created_at'].isoformat()
            user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
            withdrawal['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_withdrawals.append(withdrawal)
        response = jsonify({'success': True, 'data': {
            'withdrawals': result_withdrawals,
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit if total > 0 else 1
        }})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
        query = {}
        if status != 'all':
            query['status'] = status
        total = investments_collection.count_documents(query)
        investments = list(investments_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        result_investments = []
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if 'start_date' in inv and isinstance(inv['start_date'], datetime):
                inv['start_date'] = inv['start_date'].isoformat()
            if 'end_date' in inv and isinstance(inv['end_date'], datetime):
                inv['end_date'] = inv['end_date'].isoformat()
            user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
            inv['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_investments.append(inv)
        response = jsonify({'success': True, 'data': {
            'investments': result_investments,
            'total': total,
            'page': page,
            'pages': (total + limit - 1) // limit if total > 0 else 1
        }})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Get investments error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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
            users_collection.update_one({'_id': ObjectId(deposit['user_id'])}, {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}})
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
            users_collection.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': -withdrawal['amount'], 'wallet.total_withdrawn': withdrawal['amount']}})
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
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{subject}</title>
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
<div class="header"><h2>📧 {subject}</h2></div>
<div class="content">
<p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
<div class="message-box">{message.replace(chr(10), '<br>')}</div>
<a href="https://www.veloxtrades.com.ng/dashboard.html" class="button">View Dashboard</a>
</div>
<div class="footer"><p>© 2025 Veloxtrades. All rights reserved.</p></div>
</div>
</body>
</html>
"""
        
        send_email(user['email'], subject, message, html_body)
        create_notification(user_id, subject, message, email_type)
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'send_manual_email', f'Sent email to {user["username"]}: {subject}')
        
        response = jsonify({'success': True, 'message': f'Email sent to {user["email"]}'})
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
            active_investors = investments_collection.distinct('user_id', {'status': 'active'})
            query = {'_id': {'$in': [ObjectId(uid) for uid in active_investors]}}
        
        users = list(users_collection.find(query))
        
        sent_count = 0
        for user in users:
            html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{subject}</title>
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
<div class="header"><h2>📢 {subject}</h2></div>
<div class="content">
<p>Dear <strong>{user.get('full_name', user['username'])}</strong>,</p>
<div class="message-box">{message.replace(chr(10), '<br>')}</div>
<a href="https://www.veloxtrades.com.ng/dashboard.html" class="button">View Dashboard</a>
</div>
<div class="footer"><p>© 2025 Veloxtrades</p></div>
</div>
</body>
</html>
"""
            send_email(user['email'], subject, message, html_body)
            create_notification(user['_id'], subject, message, email_type)
            sent_count += 1
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'broadcast_email', f'Sent broadcast to {sent_count} users: {subject}')
        
        response = jsonify({'success': True, 'message': f'Broadcast sent to {sent_count} users', 'data': {'count': sent_count}})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
    """Adjust user balance"""
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Admin adjustment')
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        
        transactions_collection.insert_one({
            'user_id': str(user_id), 'type': 'adjustment', 'amount': amount,
            'status': 'completed', 'description': f'Balance adjustment by admin: {reason} (${amount:+,.2f})',
            'created_at': datetime.now(timezone.utc)
        })
        
        create_notification(user_id, 'Balance Adjusted', f'Your balance has been adjusted by ${amount:+,.2f}. Reason: {reason}', 'info')
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'adjust_balance', f'Adjusted balance for user {user["username"]} by ${amount} - Reason: {reason}')
        
        response = jsonify({'success': True, 'message': f'Balance adjusted by ${amount:+,.2f}'})
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
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status, 'banned_at': datetime.now(timezone.utc) if new_ban_status else None}})
        action = 'banned' if new_ban_status else 'unbanned'
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], f'{action}_user', f'User {user["username"]} was {action}')
        create_notification(user_id, f'Account {action.capitalize()}', f'Your account has been {action}.', 'warning' if new_ban_status else 'success')
        response = jsonify({'success': True, 'message': f'User {action} successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Toggle ban error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/reset-password', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reset_password(user_id):
    if request.method == 'OPTIONS':
        return handle_preflight()
    try:
        data = request.get_json()
        new_password = data.get('new_password')
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        
        hashed = hash_password(new_password)
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'password': hashed}})
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'reset_password', f'Password reset for user {user["username"]}')
        create_notification(user_id, 'Password Reset', 'Your password has been reset by an administrator.', 'warning')
        
        response = jsonify({'success': True, 'message': 'Password reset successfully'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Reset password error: {e}")
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
        
        investments_collection.delete_many({'user_id': str(user_id)})
        transactions_collection.delete_many({'user_id': str(user_id)})
        deposits_collection.delete_many({'user_id': str(user_id)})
        withdrawals_collection.delete_many({'user_id': str(user_id)})
        notifications_collection.delete_many({'user_id': str(user_id)})
        users_collection.delete_one({'_id': ObjectId(user_id)})
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'delete_user', f'Deleted user: {username}')
        
        response = jsonify({'success': True, 'message': f'User {username} permanently deleted'})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/reset-all', methods=['GET'])
def reset_all_admin():
    """Emergency reset - removes all admins and creates fresh one with password admin123"""
    try:
        admin_count = users_collection.count_documents({'is_admin': True})
        if admin_count > 0:
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
        users = list(users_collection.find({}, {'password': 0}))
        for user in users:
            user['_id'] = str(user['_id'])
            if 'created_at' in user and user['created_at']:
                user['created_at'] = user['created_at'].isoformat()
        return jsonify({'success': True, 'total_users': len(users), 'users': users})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== INIT DATABASE ====================
def init_database():
    try:
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        users_collection.create_index('referral_code', unique=True)
        investments_collection.create_index('user_id')
        investments_collection.create_index('status')
        transactions_collection.create_index('user_id')
        deposits_collection.create_index('user_id')
        withdrawals_collection.create_index('user_id')
        notifications_collection.create_index('user_id')
        logger.info("✅ Database indexes created")
        
        total_users = users_collection.count_documents({})
        logger.info(f"👥 Total users: {total_users}")
        logger.info("ℹ️ Use /api/admin/reset-all to create admin account")
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
    print("📊 MongoDB Connected")
    print("📧 Email Service Configured")
    print(f"   SMTP: {EMAIL_USER}")
    print(f"   From: {EMAIL_FROM}")
    print("💳 NOWPayments Integration Active")
    print("👑 Admin Dashboard Ready")
    print("🔄 Auto-Profit Cron: Every hour")
    print("=" * 70)
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print(f"🔧 Backend URL: {BACKEND_URL}")
    print("\n📝 TO CREATE ADMIN:")
    print("   Visit: /api/admin/reset-all")
    print("   This will create admin with: admin / admin123")
    print("=" * 70)
    print("\n🔐 Token Expiration: 30 DAYS")
    print("=" * 70 + "\n")

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
