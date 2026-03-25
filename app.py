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

# ==================== URL CONFIGURATION ====================
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://www.veloxtrades.com.ng')
BACKEND_URL = os.getenv('BACKEND_URL', 'https://investment-gto3.onrender.com')

ALLOWED_ORIGINS = [
    "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000", "http://localhost:5500",
    "https://frontend-ugb2.onrender.com", "https://elite-eky6.onrender.com",
    "https://veloxtrades.com.ng", "https://www.veloxtrades.com.ng",
    "https://velox-wnn4.onrender.com", "https://investment-gto3.onrender.com"
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
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = EMAIL_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
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
    subject = f"✅ Deposit Approved - ${amount} added"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour deposit of ${amount:,.2f} via {crypto.upper()} has been approved.\n\nTransaction ID: {transaction_id or 'N/A'}\n\nThank you!"
    return send_email(user['email'], subject, body)

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour deposit of ${amount:,.2f} via {crypto.upper()} has been REJECTED.\n\nReason: {reason}\n\nBest regards."
    return send_email(user['email'], subject, body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount} sent"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour withdrawal of ${amount:,.2f} to {currency.upper()} has been APPROVED.\n\nWallet: {wallet_address}\n\nThank you!"
    return send_email(user['email'], subject, body)

def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nYour withdrawal of ${amount:,.2f} to {currency.upper()} has been REJECTED.\n\nReason: {reason}"
    return send_email(user['email'], subject, body)

def send_investment_created_email(user, amount, plan_name, expected_profit):
    subject = f"🚀 Investment Created - ${amount:,.2f}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nInvestment of ${amount:,.2f} in {plan_name} created.\nExpected Profit: ${expected_profit:,.2f}"
    return send_email(user['email'], subject, body)

def send_investment_completed_email(user, amount, plan_name, profit):
    subject = f"🎉 Investment Completed - Earned ${profit:,.2f}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nInvestment of ${amount:,.2f} in {plan_name} completed.\nProfit: ${profit:,.2f}"
    return send_email(user['email'], subject, body)

def send_investment_paid_email(user, investment_amount, profit, plan_name):
    subject = f"💰 Profit Paid - ${profit:,.2f}"
    body = f"Dear {user.get('full_name', user['username'])},\n\nProfit of ${profit:,.2f} from {plan_name} paid to your wallet."
    return send_email(user['email'], subject, body)

# ==================== CORS CONFIGURATION ====================
CORS(app, supports_credentials=True, origins=ALLOWED_ORIGINS,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"], max_age=3600)

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
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
    admin_logs_collection = db['admin_logs']
    logger.info("✅ MongoDB Connected!")
except Exception as e:
    logger.error(f"❌ MongoDB Error: {e}")
    raise

# ==================== HELPER FUNCTIONS ====================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(hashed_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_jwt_token(user_id, username, is_admin=False):
    payload = {'user_id': str(user_id), 'username': username, 'is_admin': is_admin,
               'exp': datetime.now(timezone.utc) + timedelta(days=app.config['JWT_EXPIRATION_DAYS']),
               'iat': datetime.now(timezone.utc)}
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')

def verify_jwt_token(token):
    try:
        return jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
    except:
        return None

def get_user_from_request():
    token = request.cookies.get('veloxtrades_token')
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
    except:
        return None

def require_admin(f):
    def decorated(*args, **kwargs):
        user = get_user_from_request()
        if not user or not user.get('is_admin', False):
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

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
            'status': 'active', 'end_date': {'$lte': datetime.now(timezone.utc)}
        }))
        for inv in active_investments:
            try:
                result = users_collection.update_one(
                    {'_id': ObjectId(inv['user_id'])},
                    {'$inc': {'wallet.balance': inv['expected_profit'], 'wallet.total_profit': inv['expected_profit']}}
                )
                if result.modified_count > 0:
                    investments_collection.update_one({'_id': inv['_id']}, {'$set': {'status': 'completed'}})
                    transactions_collection.insert_one({
                        'user_id': inv['user_id'], 'type': 'profit', 'amount': inv['expected_profit'],
                        'status': 'completed', 'description': f'Profit from {inv["plan_name"]}',
                        'created_at': datetime.now(timezone.utc)
                    })
                    create_notification(inv['user_id'], 'Investment Completed! 🎉',
                        f'You earned ${inv["expected_profit"]:,.2f} profit!', 'success')
                    user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
                    if user:
                        send_investment_completed_email(user, inv['amount'], inv['plan_name'], inv['expected_profit'])
            except Exception as e:
                logger.error(f"Error: {e}")
    except Exception as e:
        logger.error(f"Profit processing error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=process_investment_profits, trigger="interval", hours=1, id="profit_processor", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ==================== AUTHENTICATION API ====================
@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data'}), 400
        full_name = data.get('full_name', '').strip()
        email = data.get('email', '').strip().lower()
        username = data.get('username', '').strip().lower()
        password = data.get('password', '')
        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields required'}), 400
        if users_collection.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        if users_collection.find_one({'username': username}):
            return jsonify({'success': False, 'message': 'Username taken'}), 400
        referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))
        wallet = {'balance': 0.00, 'total_deposited': 0.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00}
        user_data = {
            'full_name': full_name, 'email': email, 'username': username, 'password': hash_password(password),
            'phone': data.get('phone', ''), 'country': data.get('country', ''), 'wallet': wallet,
            'is_admin': False, 'is_verified': False, 'is_active': True, 'is_banned': False,
            'created_at': datetime.now(timezone.utc), 'referral_code': referral_code, 'kyc_status': 'pending'
        }
        result = users_collection.insert_one(user_data)
        create_notification(result.inserted_id, 'Welcome!', 'Thank you for joining Veloxtrades!', 'success')
        return jsonify({'success': True, 'message': 'Registration successful!'}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')
        if not username_or_email or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400
        user = users_collection.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
        if not user or not verify_password(user['password'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account suspended'}), 403
        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))
        users_collection.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})
        user_data = {
            'id': str(user['_id']), 'username': user['username'], 'full_name': user.get('full_name', ''),
            'email': user['email'], 'balance': user.get('wallet', {}).get('balance', 0),
            'is_admin': user.get('is_admin', False)
        }
        response = make_response(jsonify({'success': True, 'data': {'token': token, 'user': user_data}}))
        response.set_cookie('veloxtrades_token', token, httponly=True, secure=True, samesite='Lax', max_age=30*24*60*60, path='/')
        return response
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    response = make_response(jsonify({'success': True}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    return response

@app.route('/api/verify-token', methods=['GET', 'OPTIONS'])
def verify_token():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Invalid token'}), 401
    return jsonify({'success': True, 'user': {'id': str(user['_id']), 'username': user['username'], 'is_admin': user.get('is_admin', False)}})

# ==================== USER DASHBOARD API ====================
@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def get_dashboard():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    active = list(investments_collection.find({'user_id': str(user['_id']), 'status': 'active'}))
    return jsonify({'success': True, 'data': {
        'wallet': user.get('wallet', {'balance': 0}),
        'investments': {'total_active': sum(i.get('amount',0) for i in active), 'count': len(active)},
        'recent_transactions': list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).limit(10))
    }})

@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    return jsonify({'success': True, 'data': {'transactions': list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))}})

@app.route('/api/investments', methods=['GET', 'OPTIONS'])
def get_investments():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    return jsonify({'success': True, 'data': {'investments': list(investments_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))}})

@app.route('/api/deposit', methods=['POST', 'OPTIONS'])
def create_deposit():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    try:
        data = request.get_json()
        deposit = {'user_id': str(user['_id']), 'amount': float(data.get('amount',0)), 'crypto': data.get('crypto',''),
                   'wallet_address': data.get('wallet_address',''), 'transaction_id': data.get('transaction_id',''),
                   'status': 'pending', 'created_at': datetime.now(timezone.utc)}
        result = deposits_collection.insert_one(deposit)
        return jsonify({'success': True, 'data': {'deposit_id': str(result.inserted_id), 'status': 'pending'}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/withdrawals', methods=['POST', 'OPTIONS'])
def create_withdrawal():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    try:
        data = request.get_json()
        amount = float(data.get('amount',0))
        if amount > user.get('wallet',{}).get('balance',0):
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        withdrawal = {'user_id': str(user['_id']), 'amount': amount, 'currency': data.get('currency',''),
                      'wallet_address': data.get('wallet_address',''), 'status': 'pending', 'created_at': datetime.now(timezone.utc)}
        result = withdrawals_collection.insert_one(withdrawal)
        return jsonify({'success': True, 'data': {'withdrawal_id': str(result.inserted_id), 'status': 'pending'}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/invest', methods=['POST', 'OPTIONS'])
def create_investment():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    try:
        data = request.get_json()
        plan = INVESTMENT_PLANS.get(data.get('plan_type'))
        amount = float(data.get('amount',0))
        if amount > user.get('wallet',{}).get('balance',0):
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        expected_profit = amount * plan['roi'] / 100
        users_collection.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}})
        inv = {'user_id': str(user['_id']), 'plan_name': plan['name'], 'amount': amount,
               'expected_profit': expected_profit, 'status': 'active',
               'start_date': datetime.now(timezone.utc), 'end_date': datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])}
        result = investments_collection.insert_one(inv)
        send_investment_created_email(user, amount, plan['name'], expected_profit)
        return jsonify({'success': True, 'data': {'investment_id': str(result.inserted_id)}})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== NOTIFICATIONS API ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    notifications = list(notifications_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
    unread = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
    for n in notifications:
        n['_id'] = str(n['_id'])
        if 'created_at' in n:
            n['created_at'] = n['created_at'].isoformat()
    return jsonify({'success': True, 'data': {'notifications': notifications, 'unread_count': unread}})

@app.route('/api/notifications/<notification_id>/read', methods=['PUT', 'OPTIONS'])
def mark_notification_read(notification_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False}), 401
    notifications_collection.update_one({'_id': ObjectId(notification_id), 'user_id': str(user['_id'])}, {'$set': {'read': True}})
    return jsonify({'success': True})

# ==================== ADMIN API ENDPOINTS (FULL SET) ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_stats():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    return jsonify({'success': True, 'data': {
        'total_users': users_collection.count_documents({}),
        'total_deposit_amount': sum(d.get('amount',0) for d in deposits_collection.find({'status':'approved'})),
        'total_withdrawal_amount': sum(w.get('amount',0) for w in withdrawals_collection.find({'status':'approved'})),
        'active_investments': investments_collection.count_documents({'status':'active'}),
        'pending_deposits': deposits_collection.count_documents({'status':'pending'}),
        'pending_withdrawals': withdrawals_collection.count_documents({'status':'pending'})
    }})

@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_transactions():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    skip = (page - 1) * limit
    transactions = list(transactions_collection.find().sort('created_at', -1).skip(skip).limit(limit))
    for tx in transactions:
        tx['_id'] = str(tx['_id'])
        user = users_collection.find_one({'_id': ObjectId(tx['user_id'])})
        tx['user'] = {'username': user.get('username') if user else 'Unknown'}
    return jsonify({'success': True, 'data': {'transactions': transactions, 'total': transactions_collection.count_documents({})}})

@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_users():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    skip = (page - 1) * limit
    users = list(users_collection.find().sort('created_at', -1).skip(skip).limit(limit))
    for u in users:
        u['_id'] = str(u['_id'])
    return jsonify({'success': True, 'data': {'users': users, 'total': users_collection.count_documents({})}})

@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def admin_deposits():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    status = request.args.get('status', 'all')
    query = {} if status == 'all' else {'status': status}
    deposits = list(deposits_collection.find(query).sort('created_at', -1))
    for d in deposits:
        d['_id'] = str(d['_id'])
        user = users_collection.find_one({'_id': ObjectId(d['user_id'])})
        d['username'] = user.get('username') if user else 'Unknown'
    return jsonify({'success': True, 'data': {'deposits': deposits}})

@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_withdrawals():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    status = request.args.get('status', 'all')
    query = {} if status == 'all' else {'status': status}
    withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1))
    for w in withdrawals:
        w['_id'] = str(w['_id'])
        user = users_collection.find_one({'_id': ObjectId(w['user_id'])})
        w['username'] = user.get('username') if user else 'Unknown'
    return jsonify({'success': True, 'data': {'withdrawals': withdrawals}})

@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_investments():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    status = request.args.get('status', 'all')
    query = {} if status == 'all' else {'status': status}
    investments = list(investments_collection.find(query).sort('created_at', -1))
    for inv in investments:
        inv['_id'] = str(inv['_id'])
        user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
        inv['username'] = user.get('username') if user else 'Unknown'
    return jsonify({'success': True, 'data': {'investments': investments}})

@app.route('/api/admin/deposits/<deposit_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def process_deposit(deposit_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        action = data.get('action')
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit or deposit['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Deposit not found or already processed'}), 400
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if action == 'approve':
            users_collection.update_one({'_id': ObjectId(deposit['user_id'])}, {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}})
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'approved'}})
            transactions_collection.insert_one({'user_id': deposit['user_id'], 'type': 'deposit', 'amount': deposit['amount'], 'status': 'completed', 'created_at': datetime.now(timezone.utc)})
            send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_id',''))
            return jsonify({'success': True, 'message': 'Deposit approved'})
        elif action == 'reject':
            reason = data.get('reason', 'Not specified')
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'rejected'}})
            send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], reason)
            return jsonify({'success': True, 'message': 'Deposit rejected'})
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals/<withdrawal_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def process_withdrawal(withdrawal_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        action = data.get('action')
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal or withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Withdrawal not found or already processed'}), 400
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        if action == 'approve':
            users_collection.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': -withdrawal['amount'], 'wallet.total_withdrawn': withdrawal['amount']}})
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved'}})
            transactions_collection.insert_one({'user_id': withdrawal['user_id'], 'type': 'withdrawal', 'amount': withdrawal['amount'], 'status': 'completed', 'created_at': datetime.now(timezone.utc)})
            send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
            return jsonify({'success': True, 'message': 'Withdrawal approved'})
        elif action == 'reject':
            reason = data.get('reason', 'Not specified')
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'rejected'}})
            send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
            return jsonify({'success': True, 'message': 'Withdrawal rejected'})
        return jsonify({'success': False, 'message': 'Invalid action'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def adjust_balance(user_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        return jsonify({'success': True, 'message': f'Balance adjusted by ${amount:+,.2f}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/toggle-ban', methods=['POST', 'OPTIONS'])
@require_admin
def toggle_ban(user_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        new_status = not user.get('is_banned', False)
        users_collection.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_status}})
        return jsonify({'success': True, 'message': f'User {"banned" if new_status else "unbanned"}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>', methods=['DELETE', 'OPTIONS'])
@require_admin
def delete_user(user_id):
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        users_collection.delete_one({'_id': ObjectId(user_id)})
        investments_collection.delete_many({'user_id': str(user_id)})
        transactions_collection.delete_many({'user_id': str(user_id)})
        deposits_collection.delete_many({'user_id': str(user_id)})
        withdrawals_collection.delete_many({'user_id': str(user_id)})
        return jsonify({'success': True, 'message': 'User deleted'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/send-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_send_email():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        subject = data.get('subject')
        message = data.get('message')
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        send_email(user['email'], subject, message)
        return jsonify({'success': True, 'message': f'Email sent to {user["email"]}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    try:
        data = request.get_json()
        subject = data.get('subject')
        message = data.get('message')
        users = list(users_collection.find({}))
        count = 0
        for user in users:
            send_email(user['email'], subject, message)
            count += 1
        return jsonify({'success': True, 'message': f'Broadcast sent to {count} users'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/reset-all', methods=['GET'])
def reset_admin():
    users_collection.delete_many({'is_admin': True})
    users_collection.delete_many({'username': 'admin'})
    hashed = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    new_admin = {
        'full_name': 'System Administrator', 'email': 'admin@veloxtrades.ltd', 'username': 'admin',
        'password': hashed, 'wallet': {'balance': 100000, 'total_deposited': 100000},
        'is_admin': True, 'is_verified': True, 'is_active': True, 'is_banned': False,
        'created_at': datetime.now(timezone.utc), 'kyc_status': 'verified'
    }
    users_collection.insert_one(new_admin)
    return jsonify({'success': True, 'credentials': {'username': 'admin', 'password': 'admin123'}})

@app.route('/api/admin/check-status', methods=['GET'])
def check_admin():
    admin = users_collection.find_one({'username': 'admin'})
    if not admin:
        return jsonify({'success': False, 'admin_exists': False})
    return jsonify({'success': True, 'admin_exists': True, 'is_banned': admin.get('is_banned', False)})

# ==================== FRONTEND ROUTES ====================
@app.route('/')
def index():
    return jsonify({'success': True, 'message': 'Veloxtrades API', 'endpoints': ['/api/login', '/api/register', '/api/health']})

@app.route('/health')
def health():
    return jsonify({'success': True, 'status': 'healthy'})

# ==================== INIT DATABASE ====================
def init_db():
    try:
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        logger.info("✅ Database indexes created")
    except Exception as e:
        logger.error(f"Init error: {e}")

with app.app_context():
    init_db()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 VELOXTRADES API SERVER")
    print("=" * 60)
    print("📧 Email: admin@veloxtrades.ltd (sender)")
    print("🔐 SMTP: kingsleyuzokwe523@gmail.com")
    print("👑 Admin: admin / admin123")
    print("=" * 60)
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
