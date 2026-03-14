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
CORS(app, supports_credentials=True)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')

# Session configuration
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)


# Helper function for UTC now (fixes deprecation warning)
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
    print(f"📊 Database: {db.name}")
    print(f"📁 Collections: users, investments, transactions, deposits, withdrawals, notifications")
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
        'exp': utc_now() + timedelta(days=7)
    }
    return jwt.encode(payload, app.config['JWT_SECRET'], algorithm='HS256')


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
    """Get user from request (cookie or header) - UNIFIED VERSION"""
    # Try to get token from cookie first
    token = request.cookies.get('veloxtrades_token')

    # If not in cookie, try Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]

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
        'created_at': utc_now()
    }
    return notifications_collection.insert_one(notification)


# Initialize Database
def init_database():
    try:
        # Create indexes
        users_collection.create_index('email', unique=True)
        users_collection.create_index('username', unique=True)
        investments_collection.create_index([('user_id', 1), ('created_at', -1)])
        transactions_collection.create_index([('user_id', 1), ('created_at', -1)])
        deposits_collection.create_index([('user_id', 1), ('created_at', -1)])
        withdrawals_collection.create_index([('user_id', 1), ('created_at', -1)])
        notifications_collection.create_index([('user_id', 1), ('read', 1)])
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
                'created_at': utc_now(),
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
                'created_at': utc_now(),
                'last_login': None,
                'referral_code': 'DEMO123',
                'referrals': [],
                'kyc_status': 'verified'
            }
            result = users_collection.insert_one(demo_user)

            # Create sample investments for demo user
            sample_investments = [
                {
                    'user_id': str(result.inserted_id),
                    'amount': 1000.00,
                    'plan': 'Basic Plan',
                    'roi': 15,
                    'status': 'profit',
                    'profit_loss': 150.00,
                    'final_amount': 1150.00,
                    'created_at': utc_now() - timedelta(days=30),
                    'completed_at': utc_now() - timedelta(days=2)
                },
                {
                    'user_id': str(result.inserted_id),
                    'amount': 1500.00,
                    'plan': 'Premium Plan',
                    'roi': 25,
                    'status': 'active',
                    'profit_loss': 0,
                    'final_amount': 1875.00,
                    'created_at': utc_now() - timedelta(days=10),
                    'completed_at': None
                }
            ]
            investments_collection.insert_many(sample_investments)

            # Create sample transactions
            sample_transactions = [
                {
                    'user_id': str(result.inserted_id),
                    'type': 'deposit',
                    'amount': 5000.00,
                    'method': 'Bitcoin',
                    'status': 'completed',
                    'description': 'Initial deposit',
                    'created_at': utc_now() - timedelta(days=35)
                },
                {
                    'user_id': str(result.inserted_id),
                    'type': 'investment',
                    'amount': 1000.00,
                    'plan': 'Basic Plan',
                    'status': 'completed',
                    'description': 'Investment in Basic Plan',
                    'created_at': utc_now() - timedelta(days=30)
                },
                {
                    'user_id': str(result.inserted_id),
                    'type': 'profit',
                    'amount': 150.00,
                    'status': 'completed',
                    'description': 'Profit from Basic Plan',
                    'created_at': utc_now() - timedelta(days=2)
                }
            ]
            transactions_collection.insert_many(sample_transactions)

            print("✅ Demo user created with sample data")

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

        print(f"📝 Registration attempt: {username} - {email}")

        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        if '@' not in email or '.' not in email:
            return jsonify({'success': False, 'message': 'Invalid email format'}), 400

        if len(password) < 6:
            return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400

        # Check if user exists
        if users_collection.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400

        if users_collection.find_one({'username': username}):
            return jsonify({'success': False, 'message': 'Username already taken'}), 400

        # Generate referral code
        referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))

        # Create user
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
            'created_at': utc_now(),
            'last_login': None,
            'referral_code': referral_code,
            'referred_by': data.get('referral_code', '').upper(),
            'referrals': [],
            'kyc_status': 'pending'
        }

        # Insert user
        result = users_collection.insert_one(user_data)
        print(f"✅ User created: {username} with ID: {result.inserted_id}")

        return jsonify({
            'success': True,
            'message': 'Registration successful! You can now login.'
        }), 201

    except DuplicateKeyError:
        return jsonify({'success': False, 'message': 'Username or email already exists'}), 400
    except Exception as e:
        print(f"❌ Registration error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'}), 500


@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        print(f"🔑 Login attempt: {username_or_email}")

        if not username_or_email or not password:
            return jsonify({'success': False, 'message': 'Username/Email and password required'}), 400

        # Find user
        user = users_collection.find_one({
            '$or': [
                {'email': username_or_email},
                {'username': username_or_email}
            ]
        })

        if not user:
            print(f"❌ User not found: {username_or_email}")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        # Verify password
        if not verify_password(user['password'], password):
            print(f"❌ Wrong password for: {username_or_email}")
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        if not user.get('is_active', True):
            return jsonify({'success': False, 'message': 'Account is deactivated'}), 403

        # Create token
        token = create_jwt_token(user['_id'], user['username'])
        print(f"✅ Login successful: {user['username']}")

        # Update last login
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'last_login': utc_now()}}
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

        # Set cookie
        response.set_cookie(
            'veloxtrades_token',
            token,
            httponly=True,
            max_age=7 * 24 * 60 * 60,
            samesite='Lax',
            path='/',
            secure=False  # Set to True in production with HTTPS
        )

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
    return response


@app.route('/api/check-username', methods=['GET'])
def check_username():
    username = request.args.get('username', '').strip().lower()
    if not username:
        return jsonify({'available': False}), 400
    existing = users_collection.find_one({'username': username})
    return jsonify({'available': not existing})


@app.route('/api/check-email', methods=['GET'])
def check_email():
    email = request.args.get('email', '').strip().lower()
    if not email:
        return jsonify({'available': False}), 400
    existing = users_collection.find_one({'email': email})
    return jsonify({'available': not existing})


# ==================== USER API ENDPOINTS ====================

@app.route('/api/user/me', methods=['GET'])
def get_user_me():
    """Get current user data"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    # Get unread notifications count
    unread_count = notifications_collection.count_documents({
        'user_id': str(user['_id']),
        'read': False
    })

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
        'is_verified': user.get('is_verified', False),
        'two_factor_enabled': user.get('two_factor_enabled', False),
        'kyc_status': user.get('kyc_status', 'pending'),
        'referral_code': user.get('referral_code', ''),
        'referrals_count': len(user.get('referrals', [])),
        'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
        'last_login': user.get('last_login').isoformat() if user.get('last_login') else None,
        'unread_notifications': unread_count
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

    return jsonify({
        'success': True,
        'message': 'Profile updated successfully'
    })


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

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'New password must be at least 6 characters'}), 400

    users_collection.update_one(
        {'_id': user['_id']},
        {'$set': {'password': hash_password(new_password)}}
    )

    return jsonify({
        'success': True,
        'message': 'Password changed successfully'
    })


# ==================== INVESTMENT API ENDPOINTS ====================

@app.route('/api/user/investments', methods=['GET'])
def get_user_investments():
    """Get all investments for current user"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    # Get filter from query params
    status_filter = request.args.get('status', 'all')

    query = {'user_id': str(user['_id'])}
    if status_filter != 'all':
        query['status'] = status_filter

    investments = list(investments_collection.find(query).sort('created_at', -1))

    # Convert ObjectId to string and format dates
    for inv in investments:
        inv['_id'] = str(inv['_id'])
        inv['created_at'] = inv['created_at'].isoformat() if inv.get('created_at') else None
        inv['completed_at'] = inv['completed_at'].isoformat() if inv.get('completed_at') else None

    # Calculate stats
    active_count = investments_collection.count_documents({
        'user_id': str(user['_id']),
        'status': 'active'
    })

    total_profit = sum(inv.get('profit_loss', 0) for inv in investments if inv.get('profit_loss', 0) > 0)
    total_loss = sum(abs(inv.get('profit_loss', 0)) for inv in investments if inv.get('profit_loss', 0) < 0)

    return jsonify({
        'success': True,
        'data': {
            'investments': investments,
            'stats': {
                'total': len(investments),
                'active': active_count,
                'total_profit': total_profit,
                'total_loss': total_loss,
                'net_profit': total_profit - total_loss
            }
        }
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

    if not plan:
        return jsonify({'success': False, 'message': 'Please select an investment plan'}), 400

    # Check user balance
    if user['balance'] < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    # Define plan details
    plans = {
        'basic': {'name': 'Basic Plan', 'roi': 15, 'min': 100},
        'premium': {'name': 'Premium Plan', 'roi': 25, 'min': 1000},
        'vip': {'name': 'VIP Plan', 'roi': 35, 'min': 5000}
    }

    plan_details = plans.get(plan)
    if not plan_details:
        return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400

    if amount < plan_details['min']:
        return jsonify(
            {'success': False, 'message': f'Minimum for {plan_details["name"]} is ${plan_details["min"]}'}), 400

    # Calculate expected return
    expected_return = amount * (1 + plan_details['roi'] / 100)

    # Create investment
    investment = {
        'user_id': str(user['_id']),
        'amount': amount,
        'plan': plan_details['name'],
        'roi': plan_details['roi'],
        'status': 'active',
        'profit_loss': 0,
        'expected_return': expected_return,
        'final_amount': expected_return,
        'created_at': utc_now(),
        'completed_at': None
    }

    result = investments_collection.insert_one(investment)

    # Deduct from user balance
    users_collection.update_one(
        {'_id': user['_id']},
        {
            '$inc': {
                'balance': -amount,
                'total_invested': amount
            }
        }
    )

    # Create transaction record
    transaction = {
        'user_id': str(user['_id']),
        'type': 'investment',
        'amount': amount,
        'plan': plan_details['name'],
        'status': 'completed',
        'description': f'Investment in {plan_details["name"]}',
        'created_at': utc_now()
    }
    transactions_collection.insert_one(transaction)

    # Create notification
    create_notification(
        user['_id'],
        'Investment Created',
        f'Your investment of ${amount:,.2f} in {plan_details["name"]} is now active.',
        'info'
    )

    return jsonify({
        'success': True,
        'message': f'Investment of ${amount:,.2f} in {plan_details["name"]} created successfully',
        'data': {
            'investment_id': str(result.inserted_id),
            'amount': amount,
            'plan': plan_details['name'],
            'expected_return': expected_return
        }
    })


@app.route('/api/investment/<investment_id>', methods=['GET'])
def get_investment_details(investment_id):
    """Get details of a specific investment"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    investment = investments_collection.find_one({
        '_id': ObjectId(investment_id),
        'user_id': str(user['_id'])
    })

    if not investment:
        return jsonify({'success': False, 'message': 'Investment not found'}), 404

    investment['_id'] = str(investment['_id'])
    investment['created_at'] = investment['created_at'].isoformat() if investment.get('created_at') else None
    investment['completed_at'] = investment['completed_at'].isoformat() if investment.get('completed_at') else None

    return jsonify({
        'success': True,
        'data': investment
    })


# ==================== DEPOSIT API ENDPOINTS ====================

@app.route('/api/deposits', methods=['GET'])
def get_deposits():
    """Get user deposit history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    deposits = list(deposits_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))

    for dep in deposits:
        dep['_id'] = str(dep['_id'])
        dep['created_at'] = dep['created_at'].isoformat() if dep.get('created_at') else None

    return jsonify({
        'success': True,
        'data': deposits
    })


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

    if not method:
        return jsonify({'success': False, 'message': 'Please select a deposit method'}), 400

    # Generate deposit address based on method
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
        'txid': None,
        'confirmations': 0,
        'created_at': utc_now(),
        'completed_at': None
    }

    result = deposits_collection.insert_one(deposit)

    # Create transaction record
    transaction = {
        'user_id': str(user['_id']),
        'type': 'deposit',
        'amount': amount,
        'method': method,
        'status': 'pending',
        'description': f'Deposit via {method}',
        'created_at': utc_now()
    }
    transactions_collection.insert_one(transaction)

    # Create notification
    create_notification(
        user['_id'],
        'Deposit Initiated',
        f'Your deposit request of ${amount:,.2f} via {method} has been created. Please send the funds to the provided address.',
        'info'
    )

    return jsonify({
        'success': True,
        'message': 'Deposit request created',
        'data': {
            'deposit_id': str(result.inserted_id),
            'amount': amount,
            'method': method,
            'address': addresses.get(method, ''),
            'instructions': f'Send exactly {amount} USD worth of {method} to the provided address'
        }
    })


@app.route('/api/deposit/confirm', methods=['POST'])
def confirm_deposit():
    """Confirm a deposit (webhook - admin only in production)"""
    data = request.get_json()
    deposit_id = data.get('deposit_id')
    txid = data.get('txid')

    if not deposit_id or not txid:
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
    if not deposit:
        return jsonify({'success': False, 'message': 'Deposit not found'}), 404

    # Update deposit
    deposits_collection.update_one(
        {'_id': ObjectId(deposit_id)},
        {
            '$set': {
                'status': 'completed',
                'txid': txid,
                'confirmations': 12,
                'completed_at': utc_now()
            }
        }
    )

    # Add funds to user balance
    users_collection.update_one(
        {'_id': ObjectId(deposit['user_id'])},
        {'$inc': {'balance': deposit['amount']}}
    )

    # Update transaction
    transactions_collection.update_one(
        {'user_id': deposit['user_id'], 'amount': deposit['amount'], 'status': 'pending'},
        {'$set': {'status': 'completed', 'txid': txid}}
    )

    # Create notification
    create_notification(
        deposit['user_id'],
        'Deposit Confirmed',
        f'Your deposit of ${deposit["amount"]:,.2f} has been confirmed and added to your balance.',
        'success'
    )

    return jsonify({'success': True, 'message': 'Deposit confirmed'})


# ==================== WITHDRAWAL API ENDPOINTS ====================

@app.route('/api/withdrawals', methods=['GET'])
def get_withdrawals():
    """Get user withdrawal history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    withdrawals = list(withdrawals_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))

    for wd in withdrawals:
        wd['_id'] = str(wd['_id'])
        wd['created_at'] = wd['created_at'].isoformat() if wd.get('created_at') else None
        wd['processed_at'] = wd['processed_at'].isoformat() if wd.get('processed_at') else None

    return jsonify({
        'success': True,
        'data': withdrawals
    })


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

    if not method or not address:
        return jsonify({'success': False, 'message': 'Please provide withdrawal details'}), 400

    if user['balance'] < amount:
        return jsonify({'success': False, 'message': 'Insufficient balance'}), 400

    # Create withdrawal request
    withdrawal = {
        'user_id': str(user['_id']),
        'amount': amount,
        'method': method,
        'address': address,
        'status': 'pending',
        'fee': amount * 0.01,  # 1% fee
        'net_amount': amount * 0.99,
        'created_at': utc_now(),
        'processed_at': None
    }

    result = withdrawals_collection.insert_one(withdrawal)

    # Deduct from balance (hold funds)
    users_collection.update_one(
        {'_id': user['_id']},
        {'$inc': {'balance': -amount}}
    )

    # Create transaction record
    transaction = {
        'user_id': str(user['_id']),
        'type': 'withdrawal',
        'amount': -amount,
        'method': method,
        'status': 'pending',
        'description': f'Withdrawal request via {method}',
        'created_at': utc_now()
    }
    transactions_collection.insert_one(transaction)

    # Create notification
    create_notification(
        user['_id'],
        'Withdrawal Requested',
        f'Your withdrawal request of ${amount:,.2f} has been submitted for processing.',
        'info'
    )

    return jsonify({
        'success': True,
        'message': 'Withdrawal request submitted',
        'data': {
            'withdrawal_id': str(result.inserted_id),
            'amount': amount,
            'net_amount': amount * 0.99,
            'fee': amount * 0.01,
            'status': 'pending'
        }
    })


@app.route('/api/withdraw/process', methods=['POST'])
def process_withdrawal():
    """Process a withdrawal (admin only in production)"""
    data = request.get_json()
    withdrawal_id = data.get('withdrawal_id')
    action = data.get('action')  # 'approve' or 'reject'

    if not withdrawal_id or not action:
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
    if not withdrawal:
        return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404

    if action == 'approve':
        withdrawals_collection.update_one(
            {'_id': ObjectId(withdrawal_id)},
            {
                '$set': {
                    'status': 'completed',
                    'processed_at': utc_now()
                }
            }
        )

        # Update transaction
        transactions_collection.update_one(
            {'user_id': withdrawal['user_id'], 'amount': -withdrawal['amount'], 'status': 'pending'},
            {'$set': {'status': 'completed'}}
        )

        # Update user total withdrawn
        users_collection.update_one(
            {'_id': ObjectId(withdrawal['user_id'])},
            {'$inc': {'total_withdrawn': withdrawal['amount']}}
        )

        # Create notification
        create_notification(
            withdrawal['user_id'],
            'Withdrawal Processed',
            f'Your withdrawal of ${withdrawal["amount"]:,.2f} has been processed and sent to your wallet.',
            'success'
        )

        message = 'Withdrawal approved and processed'

    else:  # reject
        # Return funds to user
        users_collection.update_one(
            {'_id': ObjectId(withdrawal['user_id'])},
            {'$inc': {'balance': withdrawal['amount']}}
        )

        withdrawals_collection.update_one(
            {'_id': ObjectId(withdrawal_id)},
            {
                '$set': {
                    'status': 'rejected',
                    'processed_at': utc_now()
                }
            }
        )

        # Update transaction
        transactions_collection.update_one(
            {'user_id': withdrawal['user_id'], 'amount': -withdrawal['amount'], 'status': 'pending'},
            {'$set': {'status': 'rejected'}}
        )

        # Create notification
        create_notification(
            withdrawal['user_id'],
            'Withdrawal Rejected',
            f'Your withdrawal request of ${withdrawal["amount"]:,.2f} has been rejected. Funds have been returned to your balance.',
            'error'
        )

        message = 'Withdrawal rejected'

    return jsonify({'success': True, 'message': message})


# ==================== TRANSACTION API ENDPOINTS ====================

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get user transaction history"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    limit = int(request.args.get('limit', 50))

    transactions = list(transactions_collection.find(
        {'user_id': str(user['_id'])}
    ).sort('created_at', -1).limit(limit))

    for tx in transactions:
        tx['_id'] = str(tx['_id'])
        tx['created_at'] = tx['created_at'].isoformat() if tx.get('created_at') else None

    return jsonify({
        'success': True,
        'data': transactions
    })


# ==================== NOTIFICATION API ENDPOINTS ====================

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    """Get user notifications"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    unread_only = request.args.get('unread_only', 'false').lower() == 'true'

    query = {'user_id': str(user['_id'])}
    if unread_only:
        query['read'] = False

    notifications = list(notifications_collection.find(query).sort('created_at', -1))

    for notif in notifications:
        notif['_id'] = str(notif['_id'])
        notif['created_at'] = notif['created_at'].isoformat() if notif.get('created_at') else None

    return jsonify({
        'success': True,
        'data': notifications
    })


@app.route('/api/notifications/mark-read', methods=['POST'])
def mark_notifications_read():
    """Mark notifications as read"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    data = request.get_json()
    notification_id = data.get('notification_id')

    if notification_id:
        # Mark specific notification as read
        notifications_collection.update_one(
            {
                '_id': ObjectId(notification_id),
                'user_id': str(user['_id'])
            },
            {'$set': {'read': True}}
        )
    else:
        # Mark all as read
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
        {'username': 1, 'full_name': 1, 'created_at': 1, 'total_invested': 1}
    ))

    for ref in referrals:
        ref['_id'] = str(ref['_id'])
        ref['created_at'] = ref['created_at'].isoformat() if ref.get('created_at') else None

    return jsonify({
        'success': True,
        'data': {
            'referral_code': user.get('referral_code'),
            'referrals': referrals,
            'total_referrals': len(referrals),
            'total_commission': 0  # Calculate based on referral earnings
        }
    })


# ==================== ADMIN API ENDPOINTS ====================

@app.route('/api/admin/investments/pending', methods=['GET'])
def get_pending_investments():
    """Get pending investments (admin only)"""
    user = get_user_from_request()
    if not user or not user.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    investments = list(investments_collection.find({'status': 'active'}).sort('created_at', -1))

    # Get user details for each investment
    for inv in investments:
        inv['_id'] = str(inv['_id'])
        user_data = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
        inv['username'] = user_data.get('username') if user_data else 'Unknown'
        inv['created_at'] = inv['created_at'].isoformat() if inv.get('created_at') else None

    return jsonify({
        'success': True,
        'data': investments
    })


@app.route('/api/webhook/btc', methods=['POST'])
def btc_webhook():
    """Webhook for Bitcoin payments"""
    data = request.json
    txid = data.get('txid')
    address = data.get('address')
    confirmations = data.get('confirmations', 0)
    value = data.get('value')  # in satoshis

    # Convert to USD
    btc_amount = value / 100000000
    usd_amount = btc_amount * 50000  # Get current BTC price

    # Find pending deposit with this address
    deposit = deposits_collection.find_one({'address': address, 'status': 'pending'})
    if deposit and confirmations >= 3:
        # Credit user
        users_collection.update_one(
            {'_id': ObjectId(deposit['user_id'])},
            {'$inc': {'balance': usd_amount}}
        )
        deposits_collection.update_one(
            {'_id': deposit['_id']},
            {'$set': {'status': 'completed', 'txid': txid}}
        )

    return jsonify({'success': True})


@app.route('/api/admin/investment/update', methods=['POST'])
def update_investment():
    """Update investment status (profit/loss) - admin only"""
    user = get_user_from_request()
    if not user or not user.get('is_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.get_json()
    investment_id = data.get('investment_id')
    status = data.get('status')  # 'profit' or 'loss'
    percentage = float(data.get('percentage', 0))

    if not investment_id or not status:
        return jsonify({'success': False, 'message': 'Missing data'}), 400

    investment = investments_collection.find_one({'_id': ObjectId(investment_id)})
    if not investment:
        return jsonify({'success': False, 'message': 'Investment not found'}), 404

    # Calculate profit/loss
    if status == 'profit':
        profit_amount = investment['amount'] * (percentage / 100)
        final_amount = investment['amount'] + profit_amount

        investments_collection.update_one(
            {'_id': ObjectId(investment_id)},
            {
                '$set': {
                    'status': 'profit',
                    'profit_loss': profit_amount,
                    'final_amount': final_amount,
                    'completed_at': utc_now()
                }
            }
        )

        # Add profit to user balance
        users_collection.update_one(
            {'_id': ObjectId(investment['user_id'])},
            {
                '$inc': {
                    'balance': profit_amount,
                    'total_profit': profit_amount
                }
            }
        )

        # Create transaction
        transactions_collection.insert_one({
            'user_id': investment['user_id'],
            'type': 'profit',
            'amount': profit_amount,
            'description': f'Profit from investment #{investment_id}',
            'created_at': utc_now()
        })

        # Create notification
        create_notification(
            investment['user_id'],
            'Investment Profit',
            f'Your investment of ${investment["amount"]:,.2f} has earned ${profit_amount:,.2f} profit!',
            'success'
        )

    else:  # loss
        loss_amount = investment['amount'] * (percentage / 100)
        final_amount = investment['amount'] - loss_amount

        investments_collection.update_one(
            {'_id': ObjectId(investment_id)},
            {
                '$set': {
                    'status': 'loss',
                    'profit_loss': -loss_amount,
                    'final_amount': final_amount,
                    'completed_at': utc_now()
                }
            }
        )

        # Update user loss
        users_collection.update_one(
            {'_id': ObjectId(investment['user_id'])},
            {'$inc': {'total_loss': loss_amount}}
        )

        # Create notification
        create_notification(
            investment['user_id'],
            'Investment Loss',
            f'Your investment of ${investment["amount"]:,.2f} has incurred a loss of ${loss_amount:,.2f}.',
            'error'
        )

    return jsonify({
        'success': True,
        'message': f'Investment marked as {status}'
    })


# ==================== HEALTH CHECK ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        client.admin.command('ping')
        db_status = 'connected'
    except:
        db_status = 'disconnected'

    return jsonify({
        'success': True,
        'status': 'healthy',
        'database': db_status,
        'timestamp': utc_now().isoformat(),
        'collections': {
            'users': users_collection.count_documents({}),
            'investments': investments_collection.count_documents({}),
            'transactions': transactions_collection.count_documents({}),
            'deposits': deposits_collection.count_documents({}),
            'withdrawals': withdrawals_collection.count_documents({})
        }
    })


# Initialize database
with app.app_context():
    init_database()

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🚀 VELOXTRADES API SERVER")
    print("=" * 60)
    print(f"📊 Database: veloxtrades_db")
    print(f"🌐 API Base URL: http://localhost:5000/api")
    print("\n📡 Available Endpoints:")
    print("   🔐 AUTHENTICATION:")
    print("      • POST   /api/register - Register new user")
    print("      • POST   /api/login - User login")
    print("      • POST   /api/logout - User logout")
    print("      • GET    /api/check-username - Check username availability")
    print("      • GET    /api/check-email - Check email availability")
    print("\n   👤 USER:")
    print("      • GET    /api/user/me - Get current user data")
    print("      • POST   /api/user/update - Update user profile")
    print("      • POST   /api/user/change-password - Change password")
    print("\n   💰 INVESTMENTS:")
    print("      • GET    /api/user/investments - Get user investments")
    print("      • POST   /api/invest - Create new investment")
    print("      • GET    /api/investment/<id> - Get investment details")
    print("\n   💸 DEPOSITS:")
    print("      • GET    /api/deposits - Get deposit history")
    print("      • POST   /api/deposit - Create deposit request")
    print("\n   💳 WITHDRAWALS:")
    print("      • GET    /api/withdrawals - Get withdrawal history")
    print("      • POST   /api/withdraw - Request withdrawal")
    print("\n   📊 TRANSACTIONS:")
    print("      • GET    /api/transactions - Get transaction history")
    print("\n   🔔 NOTIFICATIONS:")
    print("      • GET    /api/notifications - Get notifications")
    print("      • POST   /api/notifications/mark-read - Mark as read")
    print("\n   👥 REFERRALS:")
    print("      • GET    /api/referrals - Get referral info")
    print("\n   👑 ADMIN:")
    print("      • GET    /api/admin/investments/pending - Get pending investments")
    print("      • POST   /api/admin/investment/update - Update investment")
    print("\n   🏥 HEALTH:")
    print("      • GET    /api/health - System health check")
    print("=" * 60)
    print("🔑 Admin credentials: admin / admin123")
    print("👤 Demo user: demo / demo123")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)