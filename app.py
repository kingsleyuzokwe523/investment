import os
import bcrypt
import jwt
import random
import string
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__, static_folder='../frontend', template_folder='../frontend')
CORS(app, supports_credentials=True, origins=["http://localhost:5000", "http://127.0.0.1:5000"])

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)


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
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")
    raise


# Helper Functions
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(hashed_password, password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))


def create_jwt_token(user_id, username):
    payload = {
        'user_id': str(user_id),
        'username': username,
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')
    return token


def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, app.config['JWT_SECRET'], algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        print("❌ Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"❌ Invalid token: {e}")
        return None


def get_user_from_request():
    """Get user from request (cookie or header)"""
    # Debug: Print all cookies
    print(f"🍪 Cookies received: {request.cookies}")

    # Try to get token from cookie first
    token = request.cookies.get('veloxtrades_token')
    print(f"🔑 Token from cookie: {token[:20] if token else 'None'}...")

    # If not in cookie, try Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        print(f"📨 Auth header: {auth_header[:30] if auth_header else 'None'}")
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            print(f"🔑 Token from header: {token[:20] if token else 'None'}...")

    if not token:
        print("❌ No token found in request")
        return None

    payload = verify_jwt_token(token)
    if not payload:
        print("❌ Invalid token payload")
        return None

    try:
        user = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
        if user:
            print(f"✅ User found: {user.get('username')}")
        else:
            print(f"❌ User not found for ID: {payload['user_id']}")
        return user
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None


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


# Initialize Database
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
                'balance': 0.00,
                'total_invested': 0.00,
                'total_profit': 0.00,
                'total_loss': 0.00,
                'total_withdrawn': 0.00,
                'is_admin': True,
                'is_verified': True,
                'is_active': True,
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
                'balance': 5000.00,
                'total_invested': 2500.00,
                'total_profit': 375.00,
                'total_loss': 50.00,
                'total_withdrawn': 0.00,
                'is_admin': False,
                'is_verified': True,
                'is_active': True,
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


# ==================== FRONTEND ROUTES ====================

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:filename>')
def serve_frontend(filename):
    return send_from_directory(app.static_folder, filename)


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

        user_data = {
            'full_name': full_name,
            'email': email,
            'username': username,
            'password': hash_password(password),
            'phone': data.get('phone', ''),
            'country': data.get('country', ''),
            'balance': 0.00,
            'total_invested': 0.00,
            'total_profit': 0.00,
            'total_loss': 0.00,
            'total_withdrawn': 0.00,
            'is_admin': False,
            'is_verified': False,
            'is_active': True,
            'two_factor_enabled': False,
            'created_at': datetime.utcnow(),
            'last_login': None,
            'referral_code': referral_code,
            'referred_by': data.get('referral_code', '').upper(),
            'referrals': [],
            'kyc_status': 'pending'
        }

        result = users_collection.insert_one(user_data)
        print(f"✅ User created: {username}")

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
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        print(f"🔑 Login attempt: {username_or_email}")

        # Find user
        user = users_collection.find_one({
            '$or': [
                {'email': username_or_email},
                {'username': username_or_email}
            ]
        })

        if not user:
            print(f"❌ User not found")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        # Verify password
        if not verify_password(user['password'], password):
            print(f"❌ Wrong password")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        # Create token
        token = create_jwt_token(user['_id'], user['username'])
        print(f"✅ Login successful, token created: {token[:30]}...")

        # Update last login
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'last_login': datetime.utcnow()}}
        )

        user_data = {
            'user_id': str(user['_id']),
            'username': user['username'],
            'full_name': user.get('full_name', ''),
            'email': user['email'],
            'balance': float(user.get('balance', 0.00)),
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

        # Set cookie with explicit parameters
        response.set_cookie(
            'veloxtrades_token',
            value=token,
            httponly=True,
            secure=False,  # Set to True in production with HTTPS
            samesite='Lax',
            max_age=7 * 24 * 60 * 60,  # 7 days in seconds
            path='/'
        )

        print(f"🍪 Cookie set in response")

        return response, 200

    except Exception as e:
        print(f"❌ Login error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Login failed'}), 500


@app.route('/api/logout', methods=['POST'])
def logout():
    response = jsonify({'success': True, 'message': 'Logged out successfully'})
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    print("✅ Logout successful, cookie cleared")
    return response


# ==================== USER API ENDPOINTS ====================

@app.route('/api/user/me', methods=['GET'])
def get_user_me():
    """Get current user data"""
    print(f"\n📝 GET /api/user/me - Checking authentication")
    user = get_user_from_request()
    if not user:
        print("❌ Authentication failed")
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    print(f"✅ User authenticated: {user.get('username')}")

    user_data = {
        'user_id': str(user['_id']),
        'full_name': user.get('full_name', ''),
        'username': user.get('username', ''),
        'email': user.get('email', ''),
        'phone': user.get('phone', ''),
        'country': user.get('country', ''),
        'balance': float(user.get('balance', 0)),
        'total_invested': float(user.get('total_invested', 0)),
        'total_profit': float(user.get('total_profit', 0)),
        'total_loss': float(user.get('total_loss', 0)),
        'total_withdrawn': float(user.get('total_withdrawn', 0)),
        'is_admin': user.get('is_admin', False),
        'referral_code': user.get('referral_code', ''),
        'referrals_count': len(user.get('referrals', [])),
    }

    return jsonify({
        'success': True,
        'data': user_data
    })


@app.route('/api/user/update', methods=['POST'])
def update_user():
    """Update user profile"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    updates = {}

    if 'full_name' in data:
        updates['full_name'] = data['full_name'].strip()
    if 'phone' in data:
        updates['phone'] = data['phone'].strip()
    if 'country' in data:
        updates['country'] = data['country'].strip()

    if updates:
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': updates}
        )

    return jsonify({'success': True, 'message': 'Profile updated successfully'})


@app.route('/api/user/change-password', methods=['POST'])
def change_password():
    """Change user password"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'success': False, 'message': 'All fields required'}), 400

    if not verify_password(user['password'], current_password):
        return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400

    users_collection.update_one(
        {'_id': user['_id']},
        {'$set': {'password': hash_password(new_password)}}
    )

    return jsonify({'success': True, 'message': 'Password changed successfully'})


# ==================== INVESTMENT API ENDPOINTS ====================

@app.route('/api/user/investments', methods=['GET'])
def get_user_investments():
    """Get all investments for current user"""
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


@app.route('/api/invest', methods=['POST'])
def make_investment():
    """Create a new investment"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))
    plan = data.get('plan', '')

    if not amount or amount < 100:
        return jsonify({'success': False, 'message': 'Minimum investment is $100'}), 400

    if user['balance'] < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    plans = {
        'basic': {'name': 'Basic Plan', 'roi': 15},
        'premium': {'name': 'Premium Plan', 'roi': 25},
        'vip': {'name': 'VIP Plan', 'roi': 35}
    }

    plan_details = plans.get(plan)
    if not plan_details:
        return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400

    investment = {
        'user_id': str(user['_id']),
        'amount': amount,
        'plan': plan_details['name'],
        'roi': plan_details['roi'],
        'status': 'active',
        'profit_loss': 0,
        'expected_return': amount * (1 + plan_details['roi'] / 100),
        'created_at': datetime.utcnow()
    }

    result = investments_collection.insert_one(investment)

    # Deduct from user balance
    users_collection.update_one(
        {'_id': user['_id']},
        {'$inc': {'balance': -amount, 'total_invested': amount}}
    )

    return jsonify({
        'success': True,
        'message': f'Investment of ${amount:,.2f} created successfully'
    })


# ==================== DEPOSIT API ENDPOINTS ====================

@app.route('/api/deposits', methods=['GET'])
def get_deposits():
    """Get user deposit history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    deposits = list(deposits_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1))

    for dep in deposits:
        dep['_id'] = str(dep['_id'])

    return jsonify({'success': True, 'data': deposits})


@app.route('/api/deposit', methods=['POST'])
def create_deposit():
    """Create a new deposit request"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))
    method = data.get('method', '')

    if not amount or amount < 50:
        return jsonify({'success': False, 'message': 'Minimum deposit is $50'}), 400

    addresses = {
        'Bitcoin': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
        'Ethereum': '0x742d35Cc6634C0532925a3b844Bc454e4438f44e',
        'USDT': 'TXw5J5UqNqH3ZqBqDqKQ9k5QqXqVqLqWqR'
    }

    deposit = {
        'user_id': str(user['_id']),
        'amount': amount,
        'method': method,
        'address': addresses.get(method, ''),
        'status': 'pending',
        'created_at': datetime.utcnow()
    }

    result = deposits_collection.insert_one(deposit)

    return jsonify({
        'success': True,
        'message': 'Deposit request created',
        'data': {
            'deposit_id': str(result.inserted_id),
            'address': addresses.get(method, '')
        }
    })


# ==================== WITHDRAWAL API ENDPOINTS ====================

@app.route('/api/withdrawals', methods=['GET'])
def get_withdrawals():
    """Get user withdrawal history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    withdrawals = list(withdrawals_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1))

    for wd in withdrawals:
        wd['_id'] = str(wd['_id'])

    return jsonify({'success': True, 'data': withdrawals})


@app.route('/api/withdraw', methods=['POST'])
def request_withdrawal():
    """Create a new withdrawal request"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    amount = float(data.get('amount', 0))
    method = data.get('method', '')
    address = data.get('address', '').strip()

    if not amount or amount < 50:
        return jsonify({'success': False, 'message': 'Minimum withdrawal is $50'}), 400

    if not address:
        return jsonify({'success': False, 'message': 'Please provide wallet address'}), 400

    if user['balance'] < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    withdrawal = {
        'user_id': str(user['_id']),
        'amount': amount,
        'method': method,
        'address': address,
        'status': 'pending',
        'fee': amount * 0.01,
        'net_amount': amount * 0.99,
        'created_at': datetime.utcnow()
    }

    result = withdrawals_collection.insert_one(withdrawal)

    # Deduct from balance
    users_collection.update_one(
        {'_id': user['_id']},
        {'$inc': {'balance': -amount}}
    )

    return jsonify({
        'success': True,
        'message': 'Withdrawal request submitted'
    })


# ==================== TRANSACTION API ENDPOINTS ====================

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get user transaction history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    transactions = list(transactions_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1).limit(50))

    for tx in transactions:
        tx['_id'] = str(tx['_id'])

    return jsonify({'success': True, 'data': transactions})


# ==================== NOTIFICATION API ENDPOINTS ====================

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Get user notifications"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    notifications = list(notifications_collection.find(
        {'user_id': str(user['_id']), 'read': False}
    ).sort('created_at', -1))

    for notif in notifications:
        notif['_id'] = str(notif['_id'])

    return jsonify({'success': True, 'data': notifications})


@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    """Mark notifications as read"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    notifications_collection.update_many(
        {'user_id': str(user['_id']), 'read': False},
        {'$set': {'read': True}}
    )

    return jsonify({'success': True, 'message': 'Notifications marked as read'})


# ==================== REFERRAL API ENDPOINTS ====================

@app.route('/api/referrals', methods=['GET'])
def get_referrals():
    """Get user referrals"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    referrals = list(users_collection.find(
        {'referred_by': user.get('referral_code')},
        {'username': 1, 'created_at': 1}
    ))

    for ref in referrals:
        ref['_id'] = str(ref['_id'])

    return jsonify({
        'success': True,
        'data': {
            'referral_code': user.get('referral_code'),
            'referrals': referrals
        }
    })


# ==================== HEALTH CHECK ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'success': True,
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat()
    })


# Initialize database
with app.app_context():
    init_database()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 VELOXTRADES API SERVER")
    print("=" * 60)
    print("📊 MongoDB Connected")
    print("🌐 Server: http://localhost:5000")
    print("\n📝 Debug mode: ON - Check console for logs")
    print("=" * 60)
    print("🔑 Test Accounts:")
    print("   Admin: admin@veloxtrades.com / admin123")
    print("   Demo:  demo@veloxtrades.com / demo123")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)