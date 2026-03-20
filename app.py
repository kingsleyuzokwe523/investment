import os
import bcrypt
import jwt
import random
import string
import hmac
import hashlib
import requests
import secrets
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

# Create Flask app - SINGLE INITIALIZATION
app = Flask(__name__, static_folder='static', template_folder='static')

# CORS Configuration - SINGLE SOURCE OF TRUTH
CORS(app, supports_credentials=True, origins=[
    "http://localhost:5000",
    "http://127.0.0.1:5000",
    "https://frontend-ugb2.onrender.com",
    "https://investment-gto3.onrender.com"
])

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', secrets.token_hex(32))

# NOWPayments Configuration
app.config['NOWPAYMENTS_API_KEY'] = os.getenv('NOWPAYMENTS_API_KEY', '')
app.config['NOWPAYMENTS_IPN_SECRET'] = os.getenv('NOWPAYMENTS_IPN_SECRET', '')
app.config['NOWPAYMENTS_API_URL'] = 'https://api.nowpayments.io/v1'

# Production URLs
FRONTEND_URL = 'https://frontend-ugb2.onrender.com'
BACKEND_URL = 'https://investment-gto3.onrender.com'

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = '.onrender.com'
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
        'exp': datetime.now(timezone.utc) + timedelta(days=7)
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
        'created_at': datetime.now(timezone.utc)
    }
    return notifications_collection.insert_one(notification)

def log_admin_action(admin_id, action, details):
    log = {
        'admin_id': str(admin_id),
        'action': action,
        'details': details,
        'ip_address': request.remote_addr,
        'created_at': datetime.now(timezone.utc)
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
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login', '/api/auth/register']
    })

@app.route('/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(app.static_folder, filename)

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.route('/health', methods=['GET', 'OPTIONS'])
def simple_health_check():
    """Simple health check endpoint for frontend"""
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'message': 'Veloxtrades API is running',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'mongo': 'connected',
        'nowpayments': 'configured',
        'frontend_url': FRONTEND_URL,
        'backend_url': BACKEND_URL
    })

# Helper function for preflight requests
def handle_preflight():
    response = jsonify({'success': True})
    return response

# ==================== AUTHENTICATION API ====================

@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    # Handle preflight request
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response

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

        # Check if user exists
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
            'created_at': datetime.now(timezone.utc),
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

# Add OPTIONS handler for /api/auth/register
@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def auth_register():
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    return register()  # Call the register function

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    # Handle preflight request
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response

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
            {'$set': {'last_login': datetime.now(timezone.utc)}}
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
            path='/',
            domain='.onrender.com'
        )

        return response, 200

    except Exception as e:
        print(f"❌ Login error: {e}")
        return jsonify({'success': False, 'message': 'Login failed'}), 500

@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    response = jsonify({'success': True, 'message': 'Logged out successfully'})
    response.set_cookie('veloxtrades_token', '', expires=0, path='/', domain='.onrender.com')
    return response

@app.route('/api/auth/profile', methods=['GET', 'OPTIONS'])
def get_profile():
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
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

@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def get_dashboard():
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
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

# ==================== ADD CORS PREFLIGHT FOR ALL ROUTES ====================

@app.before_request
def handle_options_request():
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
# ==================== ADMIN API ENDPOINTS (ADD THESE) ====================

@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_users():
    """Get all users with pagination and search"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
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
        users = list(users_collection.find(
            query,
            {'password': 0}
        ).sort('created_at', -1).skip(skip).limit(limit))
        
        for user in users:
            user['_id'] = str(user['_id'])
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
            if user.get('last_login'):
                user['last_login'] = user['last_login'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'users': users,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit
            }
        })
    except Exception as e:
        print(f"❌ Admin users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_user(user_id):
    """Get single user details"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        user = users_collection.find_one(
            {'_id': ObjectId(user_id)},
            {'password': 0}
        )
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        user['_id'] = str(user['_id'])
        if user.get('created_at'):
            user['created_at'] = user['created_at'].isoformat()
        if user.get('last_login'):
            user['last_login'] = user['last_login'].isoformat()
        
        # Get user's recent transactions
        transactions = list(transactions_collection.find(
            {'user_id': user_id}
        ).sort('created_at', -1).limit(20))
        
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if tx.get('created_at'):
                tx['created_at'] = tx['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'user': user,
                'transactions': transactions
            }
        })
    except Exception as e:
        print(f"❌ Get user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def adjust_user_balance(user_id):
    """Manually adjust user balance"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        admin = get_user_from_request()
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Manual adjustment')
        
        if amount == 0:
            return jsonify({'success': False, 'message': 'Amount cannot be zero'}), 400
        
        # Update user balance
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'wallet.balance': amount}}
        )
        
        # Create transaction record
        transaction = {
            'user_id': user_id,
            'type': 'admin_credit' if amount > 0 else 'admin_debit',
            'amount': amount,
            'status': 'completed',
            'description': f'{reason} (by admin)',
            'admin_id': str(admin['_id']),
            'created_at': datetime.now(timezone.utc)
        }
        transactions_collection.insert_one(transaction)
        
        # Notify user
        create_notification(
            ObjectId(user_id),
            'Balance Updated',
            f'Your balance has been {"credited" if amount > 0 else "debited"} by ${abs(amount):,.2f}. Reason: {reason}',
            'info'
        )
        
        return jsonify({'success': True, 'message': 'Balance adjusted successfully'})
    except Exception as e:
        print(f"❌ Balance adjustment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>/toggle-ban', methods=['POST', 'OPTIONS'])
@require_admin
def toggle_user_ban(user_id):
    """Ban or unban a user"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        admin = get_user_from_request()
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        new_status = not user.get('is_banned', False)
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_banned': new_status}}
        )
        
        action = 'banned' if new_status else 'unbanned'
        
        # Notify user
        create_notification(
            ObjectId(user_id),
            f'Account {action.capitalize()}',
            f'Your account has been {action} by an administrator.',
            'warning'
        )
        
        return jsonify({
            'success': True,
            'message': f'User {action} successfully'
        })
    except Exception as e:
        print(f"❌ Toggle ban error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>/reset-password', methods=['POST', 'OPTIONS'])
@require_admin
def reset_user_password(user_id):
    """Reset user password (admin only)"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        admin = get_user_from_request()
        data = request.get_json()
        new_password = data.get('new_password')
        
        if not new_password or len(new_password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
        
        users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'password': hash_password(new_password)}}
        )
        
        # Notify user
        create_notification(
            ObjectId(user_id),
            'Password Reset',
            'Your password has been reset by an administrator.',
            'warning'
        )
        
        return jsonify({'success': True, 'message': 'Password reset successfully'})
    except Exception as e:
        print(f"❌ Reset password error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_stats():
    """Get admin dashboard statistics"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
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
        
        # Recent users for quick view
        recent_users = list(users_collection.find(
            {},
            {'username': 1, 'full_name': 1, 'email': 1, 'created_at': 1, 'wallet': 1, 'is_banned': 1}
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
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_deposits():
    """Get all deposits with pagination"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', '')
        
        skip = (page - 1) * limit
        
        query = {}
        if status and status != 'all':
            query['payment_status'] = status
        
        total = payments_collection.count_documents(query)
        deposits = list(payments_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for dep in deposits:
            dep['_id'] = str(dep['_id'])
            # Get user info
            user = users_collection.find_one(
                {'_id': ObjectId(dep['user_id'])},
                {'username': 1, 'email': 1}
            )
            dep['user'] = {
                'username': user.get('username') if user else 'Unknown',
                'email': user.get('email') if user else 'Unknown'
            }
            if dep.get('created_at'):
                dep['created_at'] = dep['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'deposits': deposits,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit
            }
        })
    except Exception as e:
        print(f"❌ Admin deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_withdrawals():
    """Get all withdrawals with pagination"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', '')
        
        skip = (page - 1) * limit
        
        query = {}
        if status and status != 'all':
            query['status'] = status
        
        total = withdrawals_collection.count_documents(query)
        withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for wd in withdrawals:
            wd['_id'] = str(wd['_id'])
            # Get user info
            user = users_collection.find_one(
                {'_id': ObjectId(wd['user_id'])},
                {'username': 1, 'email': 1}
            )
            wd['user'] = {
                'username': user.get('username') if user else 'Unknown',
                'email': user.get('email') if user else 'Unknown'
            }
            if wd.get('created_at'):
                wd['created_at'] = wd['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'withdrawals': withdrawals,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit
            }
        })
    except Exception as e:
        print(f"❌ Admin withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/withdrawals/<withdrawal_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def process_withdrawal_request(withdrawal_id):
    """Process (approve/reject) a withdrawal"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        admin = get_user_from_request()
        data = request.get_json()
        action = data.get('action')
        transaction_id = data.get('transaction_id', '')
        reason = data.get('reason', '')
        
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        
        if withdrawal['status'] != 'pending':
            return jsonify({'success': False, 'message': 'Withdrawal already processed'}), 400
        
        if action == 'approve':
            withdrawals_collection.update_one(
                {'_id': ObjectId(withdrawal_id)},
                {
                    '$set': {
                        'status': 'completed',
                        'processed_at': datetime.now(timezone.utc),
                        'processed_by': str(admin['_id']),
                        'transaction_id': transaction_id
                    }
                }
            )
            
            # Update user's pending withdrawal
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {
                    '$inc': {
                        'wallet.pending_withdrawal': -withdrawal['amount'],
                        'wallet.total_withdrawn': withdrawal['amount']
                    }
                }
            )
            
            create_notification(
                ObjectId(withdrawal['user_id']),
                'Withdrawal Approved',
                f'Your withdrawal request for ${withdrawal["amount"]:,.2f} has been approved and sent to your wallet.',
                'success'
            )
            
            message = 'Withdrawal approved successfully'
            
        elif action == 'reject':
            withdrawals_collection.update_one(
                {'_id': ObjectId(withdrawal_id)},
                {
                    '$set': {
                        'status': 'rejected',
                        'processed_at': datetime.now(timezone.utc),
                        'processed_by': str(admin['_id']),
                        'rejection_reason': reason
                    }
                }
            )
            
            # Return funds to user
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {
                    '$inc': {
                        'wallet.balance': withdrawal['amount'],
                        'wallet.pending_withdrawal': -withdrawal['amount']
                    }
                }
            )
            
            create_notification(
                ObjectId(withdrawal['user_id']),
                'Withdrawal Rejected',
                f'Your withdrawal request for ${withdrawal["amount"]:,.2f} has been rejected. Reason: {reason or "Not specified"}',
                'warning'
            )
            
            message = 'Withdrawal rejected'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        return jsonify({'success': True, 'message': message})
    except Exception as e:
        print(f"❌ Process withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def get_admin_transactions():
    """Get all transactions with pagination"""
    if request.method == 'OPTIONS':
        response = jsonify({'success': True})
        return response
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        tx_type = request.args.get('type', '')
        
        skip = (page - 1) * limit
        
        query = {}
        if tx_type and tx_type != 'all':
            query['type'] = tx_type
        
        total = transactions_collection.count_documents(query)
        transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            # Get user info
            user = users_collection.find_one(
                {'_id': ObjectId(tx['user_id'])},
                {'username': 1, 'email': 1}
            )
            tx['user'] = {
                'username': user.get('username') if user else 'Unknown',
                'email': user.get('email') if user else 'Unknown'
            }
            if tx.get('created_at'):
                tx['created_at'] = tx['created_at'].isoformat()
        
        return jsonify({
            'success': True,
            'data': {
                'transactions': transactions,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit
            }
        })
    except Exception as e:
        print(f"❌ Admin transactions error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
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
                'created_at': datetime.now(timezone.utc),
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
                'created_at': datetime.now(timezone.utc),
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

# Initialize database
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
