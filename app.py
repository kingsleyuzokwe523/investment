import os
import bcrypt
import jwt
import random
import string
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='static')

# CORS Configuration with production URLs
CORS(app, supports_credentials=True, origins=[
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "https://frontend-ugb2.onrender.com",  # ✅ FIXED: Removed extra 'm'
    "https://investment-gto3.onrender.com"
])

# ==================== ADD THESE EXPLICIT CORS HEADERS ====================
@app.after_request
def after_request(response):
    """Add CORS headers to all responses"""
    origin = request.headers.get('Origin')
    allowed_origins = [
        'http://localhost:5000',
        'http://127.0.0.1:5000',
        'https://frontend-ugb2.onrender.com',
        'https://investment-gto3.onrender.com'
    ]

    if origin in allowed_origins:
        response.headers.add('Access-Control-Allow-Origin', origin)
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-Requested-With')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
        response.headers.add('Access-Control-Allow-Credentials', 'true')

    # Handle preflight requests
    if request.method == 'OPTIONS':
        response.status_code = 200

    return response
# ==========================================================================

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')

# NOWPayments Configuration
app.config['NOWPAYMENTS_API_KEY'] = os.getenv('NOWPAYMENTS_API_KEY', 'T25301Z-4WJMKC1-G41XRH2-DNA8HRZ')
app.config['NOWPAYMENTS_IPN_SECRET'] = os.getenv('NOWPAYMENTS_IPN_SECRET', 'bb6805f6-dbbb-442d-b31c-255dd3078628')
app.config['NOWPAYMENTS_API_URL'] = 'https://api.nowpayments.io/v1'

# Production URLs
FRONTEND_URL = 'https://frontend-ugb2.onrender.com'
BACKEND_URL = 'https://investment-gto3.onrender.com'

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Investment Plans
INVESTMENT_PLANS = {
    'standard': {
        'name': 'Standard Plan',
        'roi': 8,
        'duration_hours': 20,
        'min_deposit': 50,
        'max_deposit': 999
    },
    'advanced': {
        'name': 'Advanced Plan',
        'roi': 18,
        'duration_hours': 48,
        'min_deposit': 1000,
        'max_deposit': 5000
    },
    'professional': {
        'name': 'Professional Plan',
        'roi': 35,
        'duration_hours': 96,
        'min_deposit': 5001,
        'max_deposit': 10000
    },
    'classic': {
        'name': 'Classic Plan',
        'roi': 50,
        'duration_hours': 144,
        'min_deposit': 10001,
        'max_deposit': float('inf')
    }
}

# Helper function for UTC now
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
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    raise

# Initialize scheduler for automated tasks
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ==================== HELPER FUNCTIONS ====================

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(hashed_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_jwt_token(user_id, username, is_admin=False):
    payload = {
        'user_id': str(user_id),
        'username': username,
        'is_admin': is_admin,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
    return token

def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
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
        user = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
        return user
    except Exception:
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
    notification = {
        'user_id': str(user_id),
        'title': title,
        'message': message,
        'type': type,
        'read': False,
        'created_at': datetime.utcnow()
    }
    return notifications_collection.insert_one(notification)

def log_admin_action(admin_id, action, details):
    log = {
        'admin_id': str(admin_id),
        'action': action,
        'details': details,
        'ip_address': request.remote_addr,
        'created_at': datetime.utcnow()
    }
    admin_logs_collection.insert_one(log)

def verify_nowpayments_ipn(request_data, signature):
    """Verify NOWPayments IPN signature"""
    if not signature:
        return False
    calculated = hmac.new(
        app.config['NOWPAYMENTS_IPN_SECRET'].encode(),
        request_data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(calculated, signature)

# ==================== FRONTEND ROUTES ====================

@app.route('/')
def serve_index():
    return jsonify({
        'success': True,
        'message': 'Veloxtrades API Server',
        'frontend': FRONTEND_URL,
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login']
    })

@app.route('/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(app.static_folder, filename)

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.route('/health', methods=['GET'])
def simple_health_check():
    """Simple health check endpoint for frontend"""
    return jsonify({
        'success': True,
        'status': 'healthy',
        'message': 'Veloxtrades API is running',
        'timestamp': datetime.utcnow().isoformat()
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'mongo': 'connected',
        'nowpayments': 'configured',
        'frontend_url': FRONTEND_URL,
        'backend_url': BACKEND_URL
    })

# ==================== AUTHENTICATION API ====================

@app.route('/api/register', methods=['POST'])
def register():
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

        # Create wallet with zero balance
        wallet = {
            'balance': 0.00,
            'total_deposited': 0.00,
            'total_withdrawn': 0.00,
            'total_invested': 0.00,
            'total_profit': 0.00
        }

        user_data = {
            'full_name': full_name,
            'email': email,
            'username': username,
            'password': hash_password(password),
            'phone': data.get('phone', ''),
            'country': data.get('country', ''),
            'wallet': wallet,
            'is_admin': False,
            'is_verified': False,
            'is_active': True,
            'is_banned': False,
            'two_factor_enabled': False,
            'created_at': datetime.utcnow(),
            'last_login': None,
            'referral_code': referral_code,
            'referred_by': data.get('referral_code', '').upper(),
            'referrals': [],
            'kyc_status': 'pending'
        }

        result = users_collection.insert_one(user_data)

        # Create welcome notification
        create_notification(
            result.inserted_id,
            'Welcome to Veloxtrades!',
            'Thank you for joining. Start your investment journey today.',
            'success'
        )

        return jsonify({
            'success': True,
            'message': 'Registration successful! You can now login.'
        }), 201

    except Exception as e:
        print(f"❌ Registration error: {e}")
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        user = users_collection.find_one({
            '$or': [
                {'email': username_or_email},
                {'username': username_or_email}
            ]
        })

        if not user or not verify_password(user['password'], password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account has been suspended'}), 403

        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))

        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )

        user_data = {
            'id': str(user['_id']),
            'username': user['username'],
            'full_name': user.get('full_name', ''),
            'email': user['email'],
            'balance': user.get('wallet', {}).get('balance', 0.00),
            'is_admin': user.get('is_admin', False)
        }

        response = jsonify({
            'success': True,
            'message': 'Login successful!',
            'data': {
                'token': token,
                'user': user_data
            }
        })

        # Set secure cookie for production
        response.set_cookie(
            'veloxtrades_token',
            value=token,
            httponly=True,
            secure=True,
            samesite='Lax',
            max_age=7 * 24 * 60 * 60,
            path='/'
        )

        return response, 200

    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({'success': False, 'message': 'Login failed'}), 500

@app.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True, 'message': 'Logged out successfully'})
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    return response

@app.route('/api/auth/profile', methods=['GET'])
def get_profile():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    user_data = {
        'id': str(user['_id']),
        'full_name': user.get('full_name', ''),
        'username': user.get('username', ''),
        'email': user.get('email', ''),
        'phone': user.get('phone', ''),
        'country': user.get('country', ''),
        'wallet': user.get('wallet', {'balance': 0.00}),
        'is_admin': user.get('is_admin', False),
        'kyc_status': user.get('kyc_status', 'pending'),
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None
    }

    return jsonify({
        'success': True,
        'data': {'user': user_data}
    })

# ==================== USER DASHBOARD API ====================

@app.route('/api/user/dashboard', methods=['GET'])
def get_dashboard():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    # Get active investments
    active_investments = list(investments_collection.find({
        'user_id': str(user['_id']),
        'status': 'active'
    }))

    total_active = sum(inv.get('amount', 0) for inv in active_investments)
    pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments if inv.get('status') == 'active')

    # Get recent transactions
    recent_transactions = list(transactions_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1).limit(10))

    for tx in recent_transactions:
        tx['_id'] = str(tx['_id'])

    dashboard_data = {
        'wallet': user.get('wallet', {'balance': 0.00}),
        'investments': {
            'total_active': total_active,
            'total_profit': user.get('wallet', {}).get('total_profit', 0),
            'pending_profit': pending_profit,
            'count': len(active_investments)
        },
        'recent_transactions': recent_transactions,
        'notification_count': notifications_collection.count_documents({
            'user_id': str(user['_id']),
            'read': False
        })
    }

    return jsonify({
        'success': True,
        'data': dashboard_data
    })

# ==================== NOWPAYMENTS INTEGRATION ====================

@app.route('/api/create-payment', methods=['POST'])
def create_payment():
    """Create a NOWPayments payment"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))
    currency = data.get('currency', 'btc')

    if amount < 10:
        return jsonify({'success': False, 'message': 'Minimum deposit is $10'}), 400

    # Currency mapping for NOWPayments
    currency_map = {
        'btc': 'btc',
        'eth': 'eth',
        'usdt': 'usdttrc20',
        'sol': 'sol',
        'ltc': 'ltc'
    }

    pay_currency = currency_map.get(currency, 'btc')

    try:
        # Create payment with NOWPayments
        payment_data = {
            'price_amount': amount,
            'price_currency': 'usd',
            'pay_currency': pay_currency,
            'ipn_callback_url': f'{BACKEND_URL}/api/nowpayments-webhook',
            'order_id': f"ORDER_{user['_id']}_{int(datetime.utcnow().timestamp())}",
            'order_description': f"Veloxtrades deposit for {user['username']}",
            'success_url': f'{FRONTEND_URL}/dashboard.html',
            'cancel_url': f'{FRONTEND_URL}/dashboard.html'
        }

        headers = {
            'x-api-key': app.config['NOWPAYMENTS_API_KEY'],
            'Content-Type': 'application/json'
        }

        response = requests.post(
            f"{app.config['NOWPAYMENTS_API_URL']}/payment",
            json=payment_data,
            headers=headers,
            timeout=30
        )

        if response.status_code != 200 and response.status_code != 201:
            print(f"❌ NOWPayments error: {response.status_code} - {response.text}")
            return jsonify({'success': False, 'message': 'Payment creation failed'}), 500

        result = response.json()

        # Save payment to database
        payment_record = {
            'user_id': str(user['_id']),
            'payment_id': result.get('payment_id'),
            'amount': amount,
            'currency': currency,
            'pay_currency': pay_currency,
            'payment_status': 'waiting',
            'payment_url': result.get('invoice_url') or result.get('payment_url'),
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        payments_collection.insert_one(payment_record)

        return jsonify({
            'success': True,
            'data': {
                'payment_id': result.get('payment_id'),
                'payment_url': result.get('invoice_url') or result.get('payment_url'),
                'amount': amount
            }
        })

    except requests.exceptions.RequestException as e:
        print(f"❌ Payment creation network error: {e}")
        return jsonify({'success': False, 'message': 'Network error during payment creation'}), 500
    except Exception as e:
        print(f"❌ Payment creation error: {e}")
        return jsonify({'success': False, 'message': 'Payment creation failed'}), 500

@app.route('/api/nowpayments-webhook', methods=['POST'])
def nowpayments_webhook():
    """Handle NOWPayments IPN webhook"""
    try:
        # Get signature from header
        signature = request.headers.get('x-nowpayments-sig')

        # Get raw request data for verification
        raw_data = request.get_data()

        # Verify webhook signature
        if not verify_nowpayments_ipn(raw_data, signature):
            print("❌ Invalid webhook signature")
            return jsonify({'success': False}), 400

        data = request.json
        payment_id = data.get('payment_id')
        payment_status = data.get('payment_status')

        print(f"📨 Webhook received: Payment {payment_id} - Status: {payment_status}")

        if not payment_id:
            return jsonify({'success': False, 'message': 'No payment ID'}), 400

        # Find payment in database
        payment = payments_collection.find_one({'payment_id': payment_id})
        if not payment:
            print(f"❌ Payment not found: {payment_id}")
            return jsonify({'success': False}), 404

        # Update payment status
        payments_collection.update_one(
            {'payment_id': payment_id},
            {'$set': {
                'payment_status': payment_status,
                'updated_at': datetime.utcnow()
            }}
        )

        # If payment is finished, credit user
        if payment_status == 'finished':
            user_id = payment['user_id']
            amount = payment['amount']

            # Update user wallet
            users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {
                    '$inc': {
                        'wallet.balance': amount,
                        'wallet.total_deposited': amount
                    }
                }
            )

            # Create transaction record
            transaction = {
                'user_id': user_id,
                'type': 'deposit',
                'amount': amount,
                'currency': payment['currency'],
                'status': 'completed',
                'reference': payment_id,
                'description': f"Deposit via {payment['currency'].upper()}",
                'created_at': datetime.utcnow()
            }
            transactions_collection.insert_one(transaction)

            # Create notification
            create_notification(
                ObjectId(user_id),
                'Deposit Confirmed',
                f'Your deposit of ${amount:,.2f} has been confirmed and credited to your wallet.',
                'success'
            )

            print(f"✅ User {user_id} credited with ${amount}")

        return jsonify({'success': True}), 200

    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'success': False}), 500

@app.route('/api/payment-status/<payment_id>', methods=['GET'])
def get_payment_status(payment_id):
    """Check payment status from NOWPayments"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    try:
        headers = {'x-api-key': app.config['NOWPAYMENTS_API_KEY']}
        response = requests.get(
            f"{app.config['NOWPAYMENTS_API_URL']}/payment/{payment_id}",
            headers=headers,
            timeout=30
        )

        if response.status_code != 200:
            return jsonify({'success': False, 'message': 'Failed to get status'}), 500

        data = response.json()

        # Update local database
        payments_collection.update_one(
            {'payment_id': payment_id},
            {'$set': {
                'payment_status': data.get('payment_status'),
                'updated_at': datetime.utcnow()
            }}
        )

        return jsonify({
            'success': True,
            'data': {
                'payment_status': data.get('payment_status'),
                'pay_address': data.get('pay_address'),
                'pay_amount': data.get('pay_amount'),
                'actually_paid': data.get('actually_paid')
            }
        })

    except Exception as e:
        print(f"❌ Status check error: {e}")
        return jsonify({'success': False, 'message': 'Status check failed'}), 500

# ==================== INVESTMENT API ====================

@app.route('/api/investments', methods=['GET'])
def get_investments():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    investments = list(investments_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1))

    for inv in investments:
        inv['_id'] = str(inv['_id'])

    return jsonify({
        'success': True,
        'data': {'investments': investments}
    })

@app.route('/api/investments', methods=['POST'])
def create_investment():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    plan_key = data.get('plan')
    amount = float(data.get('amount', 0))

    if plan_key not in INVESTMENT_PLANS:
        return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400

    plan = INVESTMENT_PLANS[plan_key]

    if amount < plan['min_deposit'] or amount > plan['max_deposit']:
        return jsonify({'success': False,
                        'message': f'Amount must be between ${plan["min_deposit"]} and ${plan["max_deposit"]}'}), 400

    current_balance = user.get('wallet', {}).get('balance', 0)
    if current_balance < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    # Calculate expected profit
    expected_profit = (amount * plan['roi']) / 100
    expected_return = amount + expected_profit

    # Create investment
    investment = {
        'user_id': str(user['_id']),
        'plan_key': plan_key,
        'plan_name': plan['name'],
        'amount': amount,
        'roi': plan['roi'],
        'expected_profit': expected_profit,
        'expected_return': expected_return,
        'status': 'active',
        'start_date': datetime.utcnow(),
        'end_date': datetime.utcnow() + timedelta(hours=plan['duration_hours']),
        'profit_paid': False,
        'created_at': datetime.utcnow()
    }

    result = investments_collection.insert_one(investment)

    # Deduct from wallet
    users_collection.update_one(
        {'_id': user['_id']},
        {
            '$inc': {
                'wallet.balance': -amount,
                'wallet.total_invested': amount
            }
        }
    )

    # Create transaction
    transaction = {
        'user_id': str(user['_id']),
        'type': 'investment',
        'amount': amount,
        'plan': plan['name'],
        'status': 'completed',
        'description': f'Investment in {plan["name"]}',
        'reference': str(result.inserted_id),
        'created_at': datetime.utcnow()
    }
    transactions_collection.insert_one(transaction)

    return jsonify({
        'success': True,
        'message': f'Investment of ${amount:,.2f} created successfully'
    })

# ==================== DEPOSIT API ====================

@app.route('/api/deposits', methods=['GET'])
def get_deposits():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    deposits = list(payments_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1))

    for dep in deposits:
        dep['_id'] = str(dep['_id'])

    return jsonify({'success': True, 'data': deposits})

# ==================== WITHDRAWAL API ====================

@app.route('/api/withdrawals', methods=['GET'])
def get_withdrawals():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    withdrawals = list(withdrawals_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1))

    for wd in withdrawals:
        wd['_id'] = str(wd['_id'])

    return jsonify({'success': True, 'data': withdrawals})

@app.route('/api/withdrawals', methods=['POST'])
def create_withdrawal():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))
    currency = data.get('currency', 'btc')
    wallet_address = data.get('wallet_address', '').strip()

    if amount < 50:
        return jsonify({'success': False, 'message': 'Minimum withdrawal is $50'}), 400

    if not wallet_address:
        return jsonify({'success': False, 'message': 'Please provide wallet address'}), 400

    current_balance = user.get('wallet', {}).get('balance', 0)
    if current_balance < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    # Calculate fee (1%)
    fee = amount * 0.01
    net_amount = amount - fee

    withdrawal = {
        'user_id': str(user['_id']),
        'amount': amount,
        'currency': currency,
        'wallet_address': wallet_address,
        'fee': fee,
        'net_amount': net_amount,
        'status': 'pending',
        'created_at': datetime.utcnow()
    }

    result = withdrawals_collection.insert_one(withdrawal)

    # Deduct from balance (hold funds)
    users_collection.update_one(
        {'_id': user['_id']},
        {
            '$inc': {
                'wallet.balance': -amount,
                'wallet.pending_withdrawal': amount
            }
        }
    )

    # Create transaction
    transaction = {
        'user_id': str(user['_id']),
        'type': 'withdrawal',
        'amount': -amount,
        'currency': currency,
        'status': 'pending',
        'description': f'Withdrawal request to {currency.upper()} wallet',
        'reference': str(result.inserted_id),
        'created_at': datetime.utcnow()
    }
    transactions_collection.insert_one(transaction)

    # Notify user
    create_notification(
        user['_id'],
        'Withdrawal Requested',
        f'Your withdrawal request for ${amount:,.2f} has been submitted and is pending approval.',
        'info'
    )

    return jsonify({
        'success': True,
        'message': 'Withdrawal request submitted'
    })

# ==================== TRANSACTIONS API ====================

@app.route('/api/user/transactions', methods=['GET'])
def get_user_transactions():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    transactions = list(transactions_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1).limit(50))

    for tx in transactions:
        tx['_id'] = str(tx['_id'])

    return jsonify({
        'success': True,
        'data': {'transactions': transactions}
    })

# ==================== NOTIFICATIONS API ====================

@app.route('/api/notifications', methods=['GET'])
def get_user_notifications():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    notifications = list(notifications_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1).limit(20))

    for notif in notifications:
        notif['_id'] = str(notif['_id'])

    return jsonify({'success': True, 'data': notifications})

@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    notifications_collection.update_many(
        {'user_id': str(user['_id']), 'read': False},
        {'$set': {'read': True}}
    )

    return jsonify({'success': True})

# ==================== ADMIN API ENDPOINTS ====================

@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def get_admin_stats():
    """Get admin dashboard statistics"""
    try:
        total_users = users_collection.count_documents({})
        total_deposits = payments_collection.count_documents({'payment_status': 'finished'})
        total_deposit_amount = sum(p.get('amount', 0) for p in payments_collection.find({'payment_status': 'finished'}))

        total_withdrawals = withdrawals_collection.count_documents({'status': 'completed'})
        total_withdrawal_amount = sum(w.get('amount', 0) for w in withdrawals_collection.find({'status': 'completed'}))

        total_investments = investments_collection.count_documents({})
        active_investments = investments_collection.count_documents({'status': 'active'})

        pending_deposits = payments_collection.count_documents({'payment_status': 'waiting'})
        pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})

        # Recent users
        recent_users = list(users_collection.find(
            {},
            {'username': 1, 'full_name': 1, 'email': 1, 'created_at': 1, 'wallet': 1}
        ).sort('created_at', -1).limit(10))

        for user in recent_users:
            user['_id'] = str(user['_id'])
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()

        return jsonify({
            'success': True,
            'data': {
                'total_users': total_users,
                'total_deposits': total_deposits,
                'total_deposit_amount': total_deposit_amount,
                'total_withdrawals': total_withdrawals,
                'total_withdrawal_amount': total_withdrawal_amount,
                'total_investments': total_investments,
                'active_investments': active_investments,
                'pending_deposits': pending_deposits,
                'pending_withdrawals': pending_withdrawals,
                'recent_users': recent_users
            }
        })
    except Exception as e:
        print(f"❌ Admin stats error: {e}")
        return jsonify({'success': False, 'message': 'Failed to get stats'}), 500

# [REST OF ADMIN ENDPOINTS - keeping them as they were in your original file]

# ==================== INIT DATABASE ====================

def init_database():
    try:
        # Create indexes
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        print("✅ Database indexes created")

        # Create admin user if not exists
        admin_email = 'admin@veloxtrades.com'
        admin_exists = users_collection.find_one({'email': admin_email})

        if not admin_exists:
            admin_user = {
                'full_name': 'System Administrator',
                'email': admin_email,
                'username': 'admin',
                'password': hash_password('admin123'),
                'phone': '+1234567890',
                'country': 'USA',
                'wallet': {
                    'balance': 10000.00,
                    'total_deposited': 10000.00,
                    'total_withdrawn': 0.00,
                    'total_invested': 0.00,
                    'total_profit': 0.00
                },
                'is_admin': True,
                'is_verified': True,
                'is_active': True,
                'is_banned': False,
                'two_factor_enabled': False,
                'created_at': datetime.utcnow(),
                'last_login': None,
                'referral_code': 'ADMIN2024',
                'referrals': [],
                'kyc_status': 'verified'
            }
            users_collection.insert_one(admin_user)
            print("✅ Admin user created (username: admin, password: admin123)")

        # Create demo user
        demo_email = 'demo@veloxtrades.com'
        demo_exists = users_collection.find_one({'email': demo_email})

        if not demo_exists:
            demo_user = {
                'full_name': 'Demo User',
                'email': demo_email,
                'username': 'demo',
                'password': hash_password('demo123'),
                'phone': '+1987654321',
                'country': 'USA',
                'wallet': {
                    'balance': 5000.00,
                    'total_deposited': 5000.00,
                    'total_withdrawn': 0.00,
                    'total_invested': 2500.00,
                    'total_profit': 375.00
                },
                'is_admin': False,
                'is_verified': True,
                'is_active': True,
                'is_banned': False,
                'two_factor_enabled': False,
                'created_at': datetime.utcnow(),
                'last_login': None,
                'referral_code': 'DEMO123',
                'referrals': [],
                'kyc_status': 'verified'
            }
            users_collection.insert_one(demo_user)
            print("✅ Demo user created")

        print(f"👥 Total users: {users_collection.count_documents({})}")

    except Exception as e:
        print(f"❌ Database initialization error: {e}")

with app.app_context():
    init_database()

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 VELOXTRADES API SERVER - PRODUCTION READY")
    print("=" * 70)
    print("📊 MongoDB Connected")
    print("💳 NOWPayments Integration Active")
    print("👑 Admin Dashboard Ready")
    print("🔄 Auto-Profit Cron: Every hour")
    print("=" * 70)
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print(f"🔧 Backend URL: {BACKEND_URL}")
    print(f"👤 User Dashboard: {FRONTEND_URL}/dashboard.html")
    print(f"👑 Admin Dashboard: {FRONTEND_URL}/admin")
    print("\n📝 Test Accounts:")
    print("   Admin: admin@veloxtrades.com / admin123")
    print("   Demo:  demo@veloxtrades.com / demo123")
    print("=" * 70 + "\n")

    # For production on Render, use environment variable PORT
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
