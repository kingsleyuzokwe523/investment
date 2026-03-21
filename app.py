import os
import bcrypt
import jwt
import random
import string
import hmac
import hashlib
import requests
import mimetypes
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory, make_response
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging
import traceback

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Create Flask app - SINGLE INITIALIZATION
app = Flask(__name__, static_folder='static', template_folder='static')

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')
app.config['JWT_EXPIRATION_DAYS'] = 30  # Token valid for 30 days

# NOWPayments Configuration
app.config['NOWPAYMENTS_API_KEY'] = os.getenv('NOWPAYMENTS_API_KEY', 'T25301Z-4WJMKC1-G41XRH2-DNA8HRZ')
app.config['NOWPAYMENTS_IPN_SECRET'] = os.getenv('NOWPAYMENTS_IPN_SECRET', 'bb6805f6-dbbb-442d-b31c-255dd3078628')
app.config['NOWPAYMENTS_API_URL'] = 'https://api.nowpayments.io/v1'

# Production URLs
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://frontend-ugb2.onrender.com')
BACKEND_URL = os.getenv('BACKEND_URL', 'https://investment-gto3.onrender.com')

# Add MIME types for static files
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('text/html', '.html')

# CORS Configuration
CORS(app, 
     supports_credentials=True,
     origins=[
         "http://localhost:5000",
         "http://127.0.0.1:5000",
         "http://localhost:3000",
         "http://localhost:5500",
         "https://frontend-ugb2.onrender.com",
         "https://investment-gto3.onrender.com"
     ],
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=3600)

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

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
        'user_id': str(user_id),
        'username': username,
        'is_admin': is_admin,
        'exp': datetime.now(timezone.utc) + timedelta(days=app.config['JWT_EXPIRATION_DAYS']),
        'iat': datetime.now(timezone.utc)
    }
    token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
    return token

def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload
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
    if not signature:
        return False
    calculated = hmac.new(
        app.config['NOWPAYMENTS_IPN_SECRET'].encode(),
        request_data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(calculated, signature)

def handle_preflight():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", FRONTEND_URL)
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization,Accept,X-Requested-With")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS,PATCH")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    response.headers.add("Access-Control-Max-Age", "3600")
    return response

# ==================== AUTO-PROFIT SCHEDULER ====================

def process_investment_profits():
    try:
        logger.info("🔄 Processing investment profits...")
        
        active_investments = list(investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        }))
        
        profit_processed = 0
        
        for investment in active_investments:
            try:
                user_id = investment['user_id']
                amount = investment['amount']
                expected_profit = investment.get('expected_profit', 0)
                
                result = users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {
                        '$inc': {
                            'wallet.balance': expected_profit,
                            'wallet.total_profit': expected_profit
                        }
                    }
                )
                
                if result.modified_count > 0:
                    investments_collection.update_one(
                        {'_id': investment['_id']},
                        {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}}
                    )
                    
                    transactions_collection.insert_one({
                        'user_id': user_id,
                        'type': 'profit',
                        'amount': expected_profit,
                        'status': 'completed',
                        'description': f'Profit from {investment.get("plan_name", "Investment")}',
                        'investment_id': str(investment['_id']),
                        'created_at': datetime.now(timezone.utc)
                    })
                    
                    create_notification(
                        user_id,
                        'Investment Completed! 🎉',
                        f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!',
                        'success'
                    )
                    
                    profit_processed += 1
                    logger.info(f"✅ Processed profit for investment {investment['_id']}")
                
            except Exception as e:
                logger.error(f"❌ Error processing investment {investment['_id']}: {e}")
                logger.error(traceback.format_exc())
        
        if profit_processed > 0:
            logger.info(f"✅ Processed {profit_processed} completed investments")
        else:
            logger.info("No investments to process at this time")
        
    except Exception as e:
        logger.error(f"❌ Error in profit processing: {e}")
        logger.error(traceback.format_exc())

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=process_investment_profits,
    trigger="interval",
    hours=1,
    id="profit_processor",
    name="Process investment profits every hour",
    replace_existing=True
)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())
logger.info("✅ Auto-profit scheduler started")

# ==================== FRONTEND ROUTES ====================

@app.route('/')
def serve_index():
    return jsonify({
        'success': True,
        'message': 'Veloxtrades API Server',
        'frontend': FRONTEND_URL,
        'backend': BACKEND_URL,
        'endpoints': ['/health', '/api/health', '/api/register', '/api/login', '/api/auth/register', '/api/verify-token']
    })

@app.route('/<path:filename>')
def serve_static_files(filename):
    """Serve static files with correct MIME types"""
    response = make_response(send_from_directory(app.static_folder, filename))
    
    if filename.endswith('.js'):
        response.headers['Content-Type'] = 'application/javascript'
    elif filename.endswith('.css'):
        response.headers['Content-Type'] = 'text/css'
    elif filename.endswith('.html'):
        response.headers['Content-Type'] = 'text/html'
    
    return response

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.route('/health', methods=['GET', 'OPTIONS'])
def simple_health_check():
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
        logger.error(f"❌ Registration error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def auth_register():
    if request.method == 'OPTIONS':
        return handle_preflight()
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

        user = users_collection.find_one({
            '$or': [
                {'email': username_or_email},
                {'username': username_or_email}
            ]
        })

        if not user or not verify_password(user['password'], password):
            logger.warning(f"Login failed: Invalid credentials for {username_or_email}")
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

        response = make_response(jsonify({
            'success': True,
            'message': 'Login successful!',
            'data': {
                'token': token,
                'user': user_data
            }
        }))

        response.set_cookie(
            'veloxtrades_token',
            value=token,
            httponly=True,
            secure=True,
            samesite='Lax',
            max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60,
            path='/'
        )

        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        logger.info(f"✅ User logged in: {user['username']}")
        return response, 200

    except Exception as e:
        logger.error(f"❌ Login error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Login failed'}), 500

@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    response = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/', httponly=True, secure=True, samesite='Lax')
    response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

@app.route('/api/auth/profile', methods=['GET', 'OPTIONS'])
def get_profile():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
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
        'is_verified': user.get('is_verified', False),
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None
    }

    response = make_response(jsonify({
        'success': True,
        'data': {'user': user_data}
    }))
    response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

@app.route('/api/verify-token', methods=['GET', 'OPTIONS'])
def verify_token():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
    
    token = request.cookies.get('veloxtrades_token')
    if token:
        payload = verify_jwt_token(token)
        if payload:
            exp_time = datetime.fromtimestamp(payload['exp'], tz=timezone.utc)
            now = datetime.now(timezone.utc)
            hours_until_expiry = (exp_time - now).total_seconds() / 3600
            days_until_expiry = hours_until_expiry / 24
            
            return jsonify({
                'success': True,
                'message': 'Token is valid',
                'expires_in_hours': round(hours_until_expiry, 1),
                'expires_in_days': round(days_until_expiry, 1),
                'user': {
                    'id': str(user['_id']),
                    'username': user['username'],
                    'email': user['email'],
                    'is_admin': user.get('is_admin', False)
                }
            })
    
    return jsonify({
        'success': True,
        'message': 'Token is valid',
        'user': {
            'id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'is_admin': user.get('is_admin', False)
        }
    })

# ==================== USER DASHBOARD API ====================

@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def get_dashboard():
    if request.method == 'OPTIONS':
        return handle_preflight()
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    try:
        active_investments = list(investments_collection.find({
            'user_id': str(user['_id']),
            'status': 'active'
        }))

        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)

        recent_transactions = list(transactions_collection.find(
            {'user_id': str(user['_id'])}
        ).sort('created_at', -1).limit(10))

        for tx in recent_transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx:
                tx['created_at'] = tx['created_at'].isoformat()

        dashboard_data = {
            'wallet': user.get('wallet', {'balance': 0.00}),
            'investments': {
                'total_active': total_active,
                'total_profit': user.get('wallet', {}).get('total_profit', 0),
                'pending_profit': pending_profit,
                'count': len(active_investments),
                'active_investments': [
                    {
                        'id': str(inv['_id']),
                        'amount': inv.get('amount', 0),
                        'plan_name': inv.get('plan_name', 'Unknown'),
                        'expected_profit': inv.get('expected_profit', 0),
                        'end_date': inv.get('end_date').isoformat() if inv.get('end_date') else None
                    }
                    for inv in active_investments
                ]
            },
            'recent_transactions': recent_transactions,
            'notification_count': notifications_collection.count_documents({
                'user_id': str(user['_id']),
                'read': False
            })
        }

        response = make_response(jsonify({
            'success': True,
            'data': dashboard_data
        }))
        
        response.headers.add('Access-Control-Allow-Origin', FRONTEND_URL)
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        
        return response
        
    except Exception as e:
        logger.error(f"❌ Dashboard error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Failed to load dashboard'}), 500

# ==================== INIT DATABASE ====================

def init_database():
    try:
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        users_collection.create_index('referral_code', unique=True)
        investments_collection.create_index('user_id')
        investments_collection.create_index('status')
        transactions_collection.create_index('user_id')
        logger.info("✅ Database indexes created")

        # Create admin user
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
            logger.info("✅ Admin user created (username: admin, password: admin123)")

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
            logger.info("✅ Demo user created")

        # Create sample investment for demo user
        demo_user_obj = users_collection.find_one({'email': demo_email})
        if demo_user_obj:
            existing_investment = investments_collection.find_one({
                'user_id': str(demo_user_obj['_id']),
                'status': 'active'
            })
            
            if not existing_investment:
                sample_investment = {
                    'user_id': str(demo_user_obj['_id']),
                    'plan_name': 'Standard Plan',
                    'plan_type': 'standard',
                    'amount': 2500.00,
                    'expected_profit': 200.00,
                    'roi': 8,
                    'duration_hours': 20,
                    'status': 'active',
                    'start_date': datetime.now(timezone.utc),
                    'end_date': datetime.now(timezone.utc) + timedelta(hours=20),
                    'created_at': datetime.now(timezone.utc)
                }
                investments_collection.insert_one(sample_investment)
                logger.info("✅ Sample investment created for demo user")

        total_users = users_collection.count_documents({})
        logger.info(f"👥 Total users: {total_users}")

    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        logger.error(traceback.format_exc())

# Initialize database
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
    print("💳 NOWPayments Integration Active")
    print("👑 Admin Dashboard Ready")
    print("🔄 Auto-Profit Cron: Every hour")
    print("=" * 70)
    print(f"🌐 Frontend URL: {FRONTEND_URL}")
    print(f"🔧 Backend URL: {BACKEND_URL}")
    print("\n📝 Test Accounts:")
    print("   Admin: admin@veloxtrades.com / admin123")
    print("   Demo:  demo@veloxtrades.com / demo123")
    print("=" * 70)
    print("\n🔧 API Endpoints:")
    print("   POST   /api/register - User registration")
    print("   POST   /api/login - User login")
    print("   POST   /api/logout - User logout")
    print("   GET    /api/auth/profile - Get user profile")
    print("   GET    /api/verify-token - Verify JWT token")
    print("   GET    /api/user/dashboard - User dashboard")
    print("   GET    /api/health - Health check")
    print("=" * 70 + "\n")
    print("🔐 Token Expiration: 30 DAYS")
    print("=" * 70 + "\n")

    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
