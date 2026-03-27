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

# Configure CORS
CORS(app, 
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken", "Origin"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=86400)

# Add this after CORS - IMPORTANT FOR ALL RESPONSES
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to every response"""
    origin = request.headers.get('Origin', '')
    
    # Allow all your domains
    if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Max-Age'] = '86400'
    
    # Security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    
    return response

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
        try:
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
        except Exception as idx_error:
            logger.warning(f"Index creation warning: {idx_error}")
        
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
    """Check MongoDB connection and handle preflight requests"""
    global mongo_connected
    if not mongo_connected:
        mongo_connected = init_mongo()
    
    # Handle preflight requests - THIS IS CRITICAL FOR CORS
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin', '')
        
        # Allow all your domains
        if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = FRONTEND_URL
        
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'
        
        return response
# Add this AFTER CORS configuration
@app.after_request
def after_request(response):
    """Add security headers and CORS headers"""
    origin = request.headers.get('Origin', '')
    
    # Allow all your domains
    if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Max-Age'] = '86400'
    
    # Security headers
    response.headers.add('X-Content-Type-Options', 'nosniff')
    response.headers.add('X-Frame-Options', 'DENY')
    response.headers.add('X-XSS-Protection', '1; mode=block')
    
    return response

@app.before_request
def handle_preflight():
    """Handle preflight OPTIONS requests"""
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin', '')
        
        if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = FRONTEND_URL
        
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Max-Age'] = '86400'
        
        return response
# ==================== EMAIL CONFIGURATION ====================
# ==================== EMAIL CONFIGURATION ====================
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'Veloxtrades')

def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email with logging and retry logic"""
    for attempt in range(max_retries):
        try:
            if not to_email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
                logger.error(f"❌ Invalid email format: {to_email}")
                return False
            
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{EMAIL_FROM} <{EMAIL_USER}>"
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
            
            if email_logs_collection is not None:
                try:
                    email_logs_collection.insert_one({
                        'to': to_email,
                        'subject': subject,
                        'status': 'sent',
                        'created_at': datetime.now(timezone.utc)
                    })
                except Exception as log_error:
                    logger.error(f"Failed to log email: {log_error}")
            
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"❌ SMTP Authentication Error: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP Error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return False
        except Exception as e:
            logger.error(f"❌ Email error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return False
    
    return False
# ==================== SUPPORT TICKET ENDPOINTS ====================

@app.route('/api/support/tickets', methods=['POST', 'OPTIONS'])
def create_ticket():
    """Create a new support ticket"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        category = data.get('category', 'general')
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message are required'}), 400
        
        # Generate ticket ID
        ticket_id = 'TKT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=10))
        
        ticket_data = {
            'ticket_id': ticket_id,
            'user_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'subject': subject,
            'message': message,
            'category': category,
            'priority': data.get('priority', 'medium'),
            'status': 'open',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'messages': [
                {
                    'sender': 'user',
                    'sender_name': user['username'],
                    'message': message,
                    'created_at': datetime.now(timezone.utc)
                }
            ]
        }
        
        result = support_tickets_collection.insert_one(ticket_data)
        
        # Create notification
        create_notification(
            user['_id'],
            f'Ticket Created: {ticket_id}',
            f'Your support ticket has been created. We will respond within 24 hours.',
            'info'
        )
        
        response = jsonify({
            'success': True,
            'message': 'Support ticket created successfully',
            'data': {
                'ticket_id': ticket_id,
                'status': 'open'
            }
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"Create ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets', methods=['GET', 'OPTIONS'])
def get_tickets():
    """Get all tickets for logged in user"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if support_tickets_collection is None:
        return jsonify({'success': True, 'data': {'tickets': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        query = {'user_id': str(user['_id'])}
        
        total = support_tickets_collection.count_documents(query)
        tickets = list(support_tickets_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if ticket.get('created_at'):
                ticket['created_at'] = ticket['created_at'].isoformat()
            if ticket.get('updated_at'):
                ticket['updated_at'] = ticket['updated_at'].isoformat()
            # Remove messages from list view
            ticket.pop('messages', None)
        
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
        logger.error(f"Get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>', methods=['GET', 'OPTIONS'])
def get_ticket(ticket_id):
    """Get single ticket details with messages"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        ticket = support_tickets_collection.find_one({
            'ticket_id': ticket_id,
            'user_id': str(user['_id'])
        })
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        if ticket.get('created_at'):
            ticket['created_at'] = ticket['created_at'].isoformat()
        if ticket.get('updated_at'):
            ticket['updated_at'] = ticket['updated_at'].isoformat()
        
        # Format messages
        for msg in ticket.get('messages', []):
            if msg.get('created_at'):
                msg['created_at'] = msg['created_at'].isoformat()
        
        response = jsonify({'success': True, 'data': ticket})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
def reply_ticket(ticket_id):
    """Reply to a support ticket"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        ticket = support_tickets_collection.find_one({
            'ticket_id': ticket_id,
            'user_id': str(user['_id'])
        })
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        if ticket['status'] == 'closed':
            return jsonify({'success': False, 'message': 'Cannot reply to a closed ticket'}), 400
        
        # Add reply
        reply = {
            'sender': 'user',
            'sender_name': user['username'],
            'message': message,
            'created_at': datetime.now(timezone.utc)
        }
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'messages': reply},
                '$set': {
                    'updated_at': datetime.now(timezone.utc),
                    'status': 'open'
                }
            }
        )
        
        response = jsonify({'success': True, 'message': 'Reply sent successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>/close', methods=['POST', 'OPTIONS'])
def close_ticket(ticket_id):
    """Close a support ticket"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        ticket = support_tickets_collection.find_one({
            'ticket_id': ticket_id,
            'user_id': str(user['_id'])
        })
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        if ticket['status'] == 'closed':
            return jsonify({'success': False, 'message': 'Ticket is already closed'}), 400
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$set': {
                    'status': 'closed',
                    'closed_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )
        
        response = jsonify({'success': True, 'message': 'Ticket closed successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Close ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== KYC VERIFICATION ENDPOINTS ====================

@app.route('/api/kyc/submit', methods=['POST', 'OPTIONS'])
def submit_kyc():
    """Submit KYC documents for verification"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if kyc_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        
        # Required fields
        full_name = data.get('full_name', '').strip()
        date_of_birth = data.get('date_of_birth', '')
        country = data.get('country', '')
        id_type = data.get('id_type', '')
        id_number = data.get('id_number', '')
        id_front_url = data.get('id_front_url', '')
        
        if not all([full_name, date_of_birth, country, id_type, id_number, id_front_url]):
            return jsonify({'success': False, 'message': 'Please provide all required KYC information'}), 400
        
        # Check existing KYC
        existing = kyc_collection.find_one({'user_id': str(user['_id'])})
        if existing:
            status = existing.get('status', 'pending')
            if status == 'pending':
                return jsonify({'success': False, 'message': 'You already have a pending KYC application'}), 400
            elif status == 'approved':
                return jsonify({'success': False, 'message': 'Your KYC is already verified'}), 400
        
        # Create KYC record
        kyc_data = {
            'user_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'full_name': full_name,
            'date_of_birth': date_of_birth,
            'country': country,
            'id_type': id_type,
            'id_number': id_number,
            'id_front_url': id_front_url,
            'id_back_url': data.get('id_back_url', ''),
            'selfie_url': data.get('selfie_url', ''),
            'address': data.get('address', ''),
            'status': 'pending',
            'submitted_at': datetime.now(timezone.utc),
            'reviewed_at': None,
            'rejection_reason': None
        }
        
        result = kyc_collection.insert_one(kyc_data)
        
        # Update user status
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'kyc_status': 'pending'}}
        )
        
        # Create notification
        create_notification(
            user['_id'],
            'KYC Application Submitted',
            'Your KYC documents have been submitted. Review typically takes 24-48 hours.',
            'info'
        )
        
        response = jsonify({
            'success': True,
            'message': 'KYC application submitted successfully',
            'data': {
                'kyc_id': str(result.inserted_id),
                'status': 'pending'
            }
        })
        return add_cors_headers(response), 201
        
    except Exception as e:
        logger.error(f"KYC submit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kyc/status', methods=['GET', 'OPTIONS'])
def get_kyc_status():
    """Get KYC verification status"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if kyc_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        kyc = kyc_collection.find_one({'user_id': str(user['_id'])})
        
        if not kyc:
            return jsonify({
                'success': True,
                'data': {
                    'status': 'not_submitted',
                    'message': 'No KYC application found'
                }
            })
        
        result = {
            'status': kyc.get('status'),
            'full_name': kyc.get('full_name'),
            'submitted_at': kyc.get('submitted_at').isoformat() if kyc.get('submitted_at') else None,
            'rejection_reason': kyc.get('rejection_reason')
        }
        
        response = jsonify({'success': True, 'data': result})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get KYC status error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kyc', methods=['GET', 'OPTIONS'])
def get_kyc_details():
    """Get full KYC details"""
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if kyc_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        kyc = kyc_collection.find_one({'user_id': str(user['_id'])})
        
        if not kyc:
            return jsonify({'success': True, 'data': None})
        
        kyc['_id'] = str(kyc['_id'])
        if kyc.get('submitted_at'):
            kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        
        response = jsonify({'success': True, 'data': kyc})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get KYC details error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
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

def add_referral_commission(user_id, deposit_amount):
    """Add referral commission to referrer when a deposit is made"""
    try:
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return False
        
        referred_by_code = user.get('referred_by')
        if not referred_by_code:
            return False
        
        referrer = users_collection.find_one({'referral_code': referred_by_code})
        if not referrer:
            return False
        
        settings = settings_collection.find_one({}) if settings_collection else None
        bonus_percentage = settings.get('referral_bonus', 5) if settings else 5
        commission = deposit_amount * (bonus_percentage / 100)
        
        if commission <= 0:
            return False
        
        users_collection.update_one(
            {'_id': referrer['_id']},
            {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}}
        )
        
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(referrer['_id']),
                'type': 'commission',
                'amount': commission,
                'status': 'completed',
                'description': f'Commission from {user["username"]}\'s deposit of ${deposit_amount:,.2f}',
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(
            referrer['_id'],
            'Referral Commission! 🎉',
            f'You earned ${commission:,.2f} from {user["username"]}\'s deposit of ${deposit_amount:,.2f}!',
            'success'
        )
        
        logger.info(f"✅ Added ${commission} commission to {referrer['username']} from {user['username']}'s deposit")
        return True
        
    except Exception as e:
        logger.error(f"Error adding referral commission: {e}")
        return False

# ==================== INVESTMENT PLANS ====================
INVESTMENT_PLANS = {
    'standard': {'name': 'Standard Plan', 'roi': 8, 'duration_hours': 20, 'min_deposit': 50, 'max_deposit': 999},
    'advanced': {'name': 'Advanced Plan', 'roi': 18, 'duration_hours': 48, 'min_deposit': 1000, 'max_deposit': 5000},
    'professional': {'name': 'Professional Plan', 'roi': 35, 'duration_hours': 96, 'min_deposit': 5001, 'max_deposit': 10000},
    'classic': {'name': 'Classic Plan', 'roi': 50, 'duration_hours': 144, 'min_deposit': 10001, 'max_deposit': float('inf')}
}

# ==================== EMAIL TEMPLATES ====================
def get_email_template(title, content, button_text=None, button_link=None):
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
    try:
        subject = f"✅ Deposit Approved - ${amount:,.2f} added to your Veloxtrades account"
        user_name = user.get('full_name', user.get('username', 'User'))
        
        plain_body = f"""
Dear {user_name},

Your deposit of ${amount:,.2f} has been APPROVED and added to your wallet!

💰 Amount: ${amount:,.2f}
📱 Method: {crypto.upper()}
🔗 Transaction ID: {transaction_hash or 'N/A'}

The funds are now available in your wallet balance. You can start investing immediately.

Thank you for choosing Veloxtrades!

Best regards,
Veloxtrades Team
        """
        
        content = f'''
        <p>Dear <strong>{user_name}</strong>,</p>
        <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
            <p><strong>✅ DEPOSIT APPROVED!</strong></p>
            <p><strong>Amount:</strong> ${amount:,.2f}</p>
            <p><strong>Method:</strong> {crypto.upper()}</p>
            <p><strong>Transaction ID:</strong> {transaction_hash or 'N/A'}</p>
        </div>
        <p>Your deposit has been successfully added to your wallet balance.</p>
        <p>You can now start investing and earning profits with your funds.</p>
        '''
        html_body = get_email_template(subject, content, 'Go to Dashboard', f'{FRONTEND_URL}/dashboard.html')
        
        logger.info(f"Sending deposit approval email to {user['email']}")
        return send_email(user['email'], subject, plain_body, html_body)
    except Exception as e:
        logger.error(f"Error in send_deposit_approved_email: {e}")
        return False

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount:,.2f} deposit was not approved"
    user_name = user.get('full_name', user.get('username', 'User'))
    
    plain_body = f"""
Dear {user_name},

Your deposit request of ${amount:,.2f} has been REJECTED.

💰 Amount: ${amount:,.2f}
📱 Method: {crypto.upper()}
❌ Reason: {reason}

Please contact support if you have any questions or need assistance.

Best regards,
Veloxtrades Team
    """
    
    content = f'''
    <p>Dear <strong>{user_name}</strong>,</p>
    <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
        <p><strong>❌ DEPOSIT REJECTED</strong></p>
        <p><strong>Amount:</strong> ${amount:,.2f}</p>
        <p><strong>Method:</strong> {crypto.upper()}</p>
        <p><strong>Reason:</strong> {reason}</p>
    </div>
    <p>Your deposit request was not approved. Please ensure you followed the deposit instructions correctly.</p>
    <p>You can submit a new deposit request at any time.</p>
    '''
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/deposit.html')
    return send_email(user['email'], subject, plain_body, html_body)

def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount:,.2f} sent to your wallet"
    user_name = user.get('full_name', user.get('username', 'User'))
    
    plain_body = f"""
Dear {user_name},

Your withdrawal request of ${amount:,.2f} has been APPROVED and sent!

💰 Amount: ${amount:,.2f}
📱 Currency: {currency.upper()}
💳 Wallet Address: {wallet_address}

The funds have been sent to your wallet. Please allow 1-24 hours for the transaction to confirm on the blockchain.

Best regards,
Veloxtrades Team
    """
    
    content = f'''
    <p>Dear <strong>{user_name}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ WITHDRAWAL APPROVED!</strong></p>
        <p><strong>Amount:</strong> ${amount:,.2f}</p>
        <p><strong>Currency:</strong> {currency.upper()}</p>
        <p><strong>Wallet Address:</strong> {wallet_address}</p>
    </div>
    <p>Your withdrawal has been processed and sent to your wallet. Funds should reflect within a few hours.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, plain_body, html_body)

def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount:,.2f} withdrawal request"
    user_name = user.get('full_name', user.get('username', 'User'))
    
    plain_body = f"""
Dear {user_name},

Your withdrawal request of ${amount:,.2f} has been REJECTED.

💰 Amount: ${amount:,.2f}
📱 Currency: {currency.upper()}
❌ Reason: {reason}

The funds have been returned to your wallet balance.

Please verify your wallet address and try again.

Best regards,
Veloxtrades Team
    """
    
    content = f'''
    <p>Dear <strong>{user_name}</strong>,</p>
    <div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 15px; margin: 20px 0;">
        <p><strong>❌ WITHDRAWAL REJECTED</strong></p>
        <p><strong>Amount:</strong> ${amount:,.2f}</p>
        <p><strong>Currency:</strong> {currency.upper()}</p>
        <p><strong>Reason:</strong> {reason}</p>
    </div>
    <p>Your withdrawal request was not approved. The funds have been returned to your wallet.</p>
    <p>Please ensure your wallet address is correct and try again.</p>
    '''
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/withdraw.html')
    return send_email(user['email'], subject, plain_body, html_body)

def send_investment_confirmation_email(user, amount, plan_name, roi, expected_profit):
    subject = f"🚀 Investment Confirmed - ${amount:,.2f} invested in {plan_name}"
    user_name = user.get('full_name', user.get('username', 'User'))
    
    plain_body = f"""
Dear {user_name},

Your investment of ${amount:,.2f} in {plan_name} has STARTED!

💰 Amount: ${amount:,.2f}
📈 ROI: {roi}%
🎯 Expected Profit: ${expected_profit:,.2f}
💵 Total Return: ${(amount + expected_profit):,.2f}

Your investment will automatically complete at the end of the duration. You'll receive another email when your investment completes.

Best regards,
Veloxtrades Team
    """
    
    content = f'''
    <p>Dear <strong>{user_name}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>✅ INVESTMENT STARTED!</strong></p>
        <p><strong>Plan:</strong> {plan_name}</p>
        <p><strong>Amount:</strong> ${amount:,.2f}</p>
        <p><strong>ROI:</strong> {roi}%</p>
        <p><strong>Expected Profit:</strong> ${expected_profit:,.2f}</p>
        <p><strong>Total Return:</strong> ${(amount + expected_profit):,.2f}</p>
    </div>
    <p>Your investment is now active and will automatically complete at the end of the duration.</p>
    <p>You will receive another email when your investment completes with your profit.</p>
    '''
    html_body = get_email_template(subject, content, 'View Investments', f'{FRONTEND_URL}/investments.html')
    return send_email(user['email'], subject, plain_body, html_body)

def send_investment_completed_email(user, amount, plan_name, profit):
    subject = f"✅ Investment Completed - You earned ${profit:,.2f}!"
    user_name = user.get('full_name', user.get('username', 'User'))
    
    plain_body = f"""
Dear {user_name},

Your investment has been COMPLETED successfully!

💰 Initial Investment: ${amount:,.2f}
📈 Profit Earned: ${profit:,.2f}
💵 Total Return: ${(amount + profit):,.2f}

The profit has been added to your wallet balance. You can withdraw your funds or start a new investment.

Congratulations on your earnings!

Best regards,
Veloxtrades Team
    """
    
    content = f'''
    <p>Dear <strong>{user_name}</strong>,</p>
    <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 15px; margin: 20px 0;">
        <p><strong>🎉 INVESTMENT COMPLETED!</strong></p>
        <p><strong>Plan:</strong> {plan_name}</p>
        <p><strong>Initial Investment:</strong> ${amount:,.2f}</p>
        <p><strong>Profit Earned:</strong> ${profit:,.2f}</p>
        <p><strong>Total Return:</strong> ${(amount + profit):,.2f}</p>
    </div>
    <p>Your investment has been successfully completed. The profit has been added to your wallet balance.</p>
    <p>You can start a new investment or withdraw your funds.</p>
    '''
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, plain_body, html_body)

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
                    
                    create_notification(user_id, 'Investment Completed! 🎉',
                        f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!', 'success')
                    
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
        referral_code_input = data.get('referral_code', '').strip().upper()

        if not all([full_name, email, username, password]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        if users_collection.find_one({'email': email}):
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        if users_collection.find_one({'username': username}):
            return jsonify({'success': False, 'message': 'Username already taken'}), 400

        # Check referral code
        referred_by = None
        referrer = None
        if referral_code_input:
            referrer = users_collection.find_one({'referral_code': referral_code_input})
            if referrer:
                referred_by = referral_code_input
                logger.info(f"✅ User {username} referred by {referrer['username']} using code {referral_code_input}")

        # Generate user's referral code
        own_referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))
        wallet = {'balance': 0.00, 'total_deposited': 0.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00}

        user_data = {
            'full_name': full_name, 'email': email, 'username': username, 'password': hash_password(password),
            'phone': data.get('phone', ''), 'country': data.get('country', ''), 'wallet': wallet,
            'is_admin': False, 'is_verified': False, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': own_referral_code, 'referred_by': referred_by, 'referrals': [], 'kyc_status': 'pending'
        }

        result = users_collection.insert_one(user_data)
        
        # Add to referrer's referrals list
        if referrer:
            users_collection.update_one(
                {'_id': referrer['_id']},
                {'$push': {'referrals': username}}
            )
            create_notification(referrer['_id'], 'New Referral! 🎉', 
                f'{username} just joined using your referral link!', 'success')
        
        create_notification(result.inserted_id, 'Welcome to Veloxtrades!', 
            'Thank you for joining. Start your investment journey today.', 'success')
        
        response = jsonify({'success': True, 'message': 'Registration successful! You can now login.'})
        return add_cors_headers(response), 201
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'message': 'Registration failed'}), 500

@app.route('/api/verify-referral', methods=['POST', 'OPTIONS'])
def verify_referral():
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        referral_code = data.get('referral_code', '').strip().upper()
        
        if not referral_code:
            return jsonify({'success': False, 'message': 'Referral code required'}), 400
        
        referrer = users_collection.find_one({'referral_code': referral_code})
        
        if referrer:
            return jsonify({
                'success': True,
                'valid': True,
                'message': 'Valid referral code!',
                'referrer': referrer.get('username', 'User')
            })
        else:
            return jsonify({
                'success': True,
                'valid': False,
                'message': 'Invalid referral code'
            })
            
    except Exception as e:
        logger.error(f"Verify referral error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
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
    response = make_response(jsonify({'success': True, 'message': 'Logged out successfully'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    return add_cors_headers(response)

@app.route('/api/auth/profile', methods=['GET', 'OPTIONS'])
def get_profile():
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
        
        users_collection.update_one(
            {'_id': user['_id']},
            {'$inc': {'wallet.balance': -amount}}
        )
        
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
        
        create_notification(user['_id'], 'Investment Started!', 
            f'You have invested ${amount:,.2f} in {plan["name"]}. Expected profit: ${expected_profit:,.2f}', 'success')
        
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
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # Safely get wallet data
        wallet = user.get('wallet', {})
        if not isinstance(wallet, dict):
            wallet = {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0}
        
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
        
        # Format transactions
        formatted_transactions = []
        for tx in recent_transactions:
            formatted_transactions.append({
                '_id': str(tx['_id']),
                'type': tx.get('type', 'unknown'),
                'amount': tx.get('amount', 0),
                'status': tx.get('status', 'pending'),
                'description': tx.get('description', ''),
                'created_at': tx.get('created_at').isoformat() if tx.get('created_at') else None
            })
        
        # Get notification count
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
            'wallet': {
                'balance': wallet.get('balance', 0),
                'total_deposited': wallet.get('total_deposited', 0),
                'total_withdrawn': wallet.get('total_withdrawn', 0),
                'total_invested': wallet.get('total_invested', 0),
                'total_profit': wallet.get('total_profit', 0)
            },
            'investments': {
                'total_active': total_active,
                'total_profit': wallet.get('total_profit', 0),
                'pending_profit': pending_profit,
                'count': len(active_investments)
            },
            'recent_transactions': formatted_transactions,
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
        logger.error(traceback.format_exc())
        # Return default data on error
        return jsonify({
            'success': True,
            'data': {
                'wallet': {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0},
                'investments': {'total_active': 0, 'total_profit': 0, 'pending_profit': 0, 'count': 0},
                'recent_transactions': [],
                'notification_count': 0,
                'kyc_status': user.get('kyc_status', 'pending') if user else 'pending',
                'pending_requests': {'deposits': 0, 'withdrawals': 0}
            }
        }), 200
# ==================== USER NOTIFICATIONS ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
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

def add_referral_commission(user_id, deposit_amount):
    """Add referral commission to referrer when a deposit is made"""
    try:
        if users_collection is None:
            return False
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            logger.warning(f"User {user_id} not found for referral commission")
            return False
        
        referred_by_code = user.get('referred_by')
        if not referred_by_code:
            return False
        
        referrer = users_collection.find_one({'referral_code': referred_by_code})
        if not referrer:
            logger.warning(f"Referrer with code {referred_by_code} not found")
            return False
        
        # Get bonus percentage from settings
        bonus_percentage = 5
        if settings_collection is not None:
            settings = settings_collection.find_one({})
            if settings:
                bonus_percentage = settings.get('referral_bonus', 5)
        
        commission = deposit_amount * (bonus_percentage / 100)
        
        if commission <= 0:
            return False
        
        # Update referrer wallet
        result = users_collection.update_one(
            {'_id': referrer['_id']},
            {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}}
        )
        
        if result.modified_count > 0:
            # Create transaction record
            if transactions_collection is not None:
                try:
                    transactions_collection.insert_one({
                        'user_id': str(referrer['_id']),
                        'type': 'commission',
                        'amount': commission,
                        'status': 'completed',
                        'description': f'Commission from {user["username"]}\'s deposit of ${deposit_amount:,.2f}',
                        'created_at': datetime.now(timezone.utc)
                    })
                except Exception as tx_error:
                    logger.error(f"Failed to create commission transaction: {tx_error}")
            
            # Create notification
            try:
                create_notification(
                    referrer['_id'],
                    'Referral Commission! 🎉',
                    f'You earned ${commission:,.2f} from {user["username"]}\'s deposit of ${deposit_amount:,.2f}!',
                    'success'
                )
            except Exception as notif_error:
                logger.error(f"Failed to create notification: {notif_error}")
            
            logger.info(f"✅ Added ${commission} commission to {referrer['username']} from {user['username']}'s deposit")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error adding referral commission: {e}")
        logger.error(traceback.format_exc())
        return False

@app.route('/api/user/referral-info', methods=['GET', 'OPTIONS'])
def get_user_referral_info():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        referral_code = user.get('referral_code', '')
        
        # Find users who used this referral code
        referred_users = list(users_collection.find(
            {'referred_by': referral_code},
            {'_id': 1, 'username': 1, 'full_name': 1, 'created_at': 1, 'wallet.total_deposited': 1}
        ))
        
        formatted_referrals = []
        total_commission = 0
        
        for ref in referred_users:
            wallet = ref.get('wallet', {})
            total_deposited = wallet.get('total_deposited', 0) if isinstance(wallet, dict) else 0
            commission = total_deposited * 0.05
            total_commission += commission
            
            formatted_referrals.append({
                'id': str(ref['_id']),
                'username': ref.get('username', ''),
                'full_name': ref.get('full_name', ''),
                'joined': ref.get('created_at').isoformat() if ref.get('created_at') else None,
                'total_deposited': total_deposited,
                'commission_earned': commission
            })
        
        # Get referral bonus percentage
        referral_bonus_percentage = 5
        if settings_collection is not None:
            settings = settings_collection.find_one({})
            if settings:
                referral_bonus_percentage = settings.get('referral_bonus', 5)
        
        response_data = {
            'referral_code': referral_code,
            'referral_link': f"{FRONTEND_URL}/register?ref={referral_code}",
            'referral_bonus_percentage': referral_bonus_percentage,
            'total_referrals': len(formatted_referrals),
            'total_commission': total_commission,
            'referred_users': formatted_referrals
        }
        
        response = jsonify({'success': True, 'data': response_data})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get referral info error: {e}")
        logger.error(traceback.format_exc())
        # Return empty data instead of error
        return jsonify({
            'success': True, 
            'data': {
                'referral_code': user.get('referral_code', 'N/A'),
                'referral_link': f"{FRONTEND_URL}/register?ref={user.get('referral_code', '')}",
                'referral_bonus_percentage': 5,
                'total_referrals': 0,
                'total_commission': 0,
                'referred_users': []
            }
        }), 200
# ==================== ADMIN KYC MANAGEMENT ENDPOINTS ====================

@app.route('/api/admin/kyc/applications', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_applications():
    """Get all KYC applications for admin review"""
    if kyc_collection is None:
        return jsonify({'success': True, 'data': {'applications': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'pending')
        search = request.args.get('search', '')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        if search:
            query['$or'] = [
                {'username': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'full_name': {'$regex': search, '$options': 'i'}},
                {'id_number': {'$regex': search, '$options': 'i'}}
            ]
        
        total = kyc_collection.count_documents(query)
        applications = list(kyc_collection.find(query).sort('submitted_at', -1).skip(skip).limit(limit))
        
        result_applications = []
        for app in applications:
            app['_id'] = str(app['_id'])
            if app.get('submitted_at'):
                app['submitted_at'] = app['submitted_at'].isoformat()
            if app.get('reviewed_at'):
                app['reviewed_at'] = app['reviewed_at'].isoformat()
            
            # Get user details
            if users_collection and app.get('user_id'):
                try:
                    user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
                    if user:
                        app['user_details'] = {
                            'username': user.get('username', ''),
                            'email': user.get('email', ''),
                            'phone': user.get('phone', ''),
                            'registered_at': user.get('created_at').isoformat() if user.get('created_at') else None,
                            'total_deposited': user.get('wallet', {}).get('total_deposited', 0),
                            'wallet_balance': user.get('wallet', {}).get('balance', 0)
                        }
                except:
                    app['user_details'] = {'username': 'Unknown', 'email': ''}
            
            result_applications.append(app)
        
        response = jsonify({
            'success': True,
            'data': {
                'applications': result_applications,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get KYC applications error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_application(kyc_id):
    """Get single KYC application details"""
    if kyc_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC application not found'}), 404
        
        kyc['_id'] = str(kyc['_id'])
        if kyc.get('submitted_at'):
            kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        if kyc.get('reviewed_at'):
            kyc['reviewed_at'] = kyc['reviewed_at'].isoformat()
        
        # Get full user details
        if users_collection and kyc.get('user_id'):
            user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
            if user:
                kyc['user_details'] = {
                    '_id': str(user['_id']),
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'full_name': user.get('full_name', ''),
                    'phone': user.get('phone', ''),
                    'country': user.get('country', ''),
                    'wallet': user.get('wallet', {}),
                    'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
                    'last_login': user.get('last_login').isoformat() if user.get('last_login') else None
                }
        
        response = jsonify({'success': True, 'data': kyc})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get KYC application error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>/approve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_approve_kyc(kyc_id):
    """Approve KYC application"""
    if kyc_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json() or {}
        notes = data.get('notes', '')
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC application not found'}), 404
        
        if kyc['status'] != 'pending':
            return jsonify({'success': False, 'message': f'This application has already been {kyc["status"]}'}), 400
        
        admin_user = get_user_from_request()
        
        # Update KYC status
        kyc_collection.update_one(
            {'_id': ObjectId(kyc_id)},
            {
                '$set': {
                    'status': 'approved',
                    'reviewed_at': datetime.now(timezone.utc),
                    'reviewed_by': str(admin_user['_id']),
                    'reviewer_username': admin_user.get('username', 'Admin'),
                    'reviewer_notes': notes
                }
            }
        )
        
        # Update user's KYC status
        users_collection.update_one(
            {'_id': ObjectId(kyc['user_id'])},
            {'$set': {'kyc_status': 'verified', 'is_verified': True}}
        )
        
        # Create notification
        create_notification(
            kyc['user_id'],
            'KYC Approved! ✅',
            'Congratulations! Your KYC verification has been approved. You now have full access to all features.',
            'success'
        )
        
        # Send email
        user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
        if user:
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #10b981; padding: 20px; text-align: center; color: white;">
                    <h1>KYC Approved!</h1>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0;">
                    <p>Dear {user.get('full_name', user.get('username', 'User'))},</p>
                    <p>Congratulations! Your KYC verification has been <strong style="color: #10b981;">APPROVED</strong>.</p>
                    <p>You now have full access to all Veloxtrades features including deposits, withdrawals, and investments.</p>
                    <p>Thank you for choosing Veloxtrades!</p>
                    <br>
                    <p>Best regards,<br>Veloxtrades Team</p>
                </div>
            </div>
            """
            send_email(user['email'], 'KYC Verification Approved', f"Dear {user.get('full_name', user.get('username', 'User'))},\n\nYour KYC has been approved.\n\nBest regards,\nVeloxtrades Team", html_body)
        
        # Log admin action
        log_admin_action(admin_user['_id'], 'KYC Approved', f'Approved KYC for user {kyc["username"]}')
        
        response = jsonify({'success': True, 'message': 'KYC application approved successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin approve KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>/reject', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reject_kyc(kyc_id):
    """Reject KYC application"""
    if kyc_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        notes = data.get('notes', '')
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC application not found'}), 404
        
        if kyc['status'] != 'pending':
            return jsonify({'success': False, 'message': f'This application has already been {kyc["status"]}'}), 400
        
        admin_user = get_user_from_request()
        
        # Update KYC status
        kyc_collection.update_one(
            {'_id': ObjectId(kyc_id)},
            {
                '$set': {
                    'status': 'rejected',
                    'reviewed_at': datetime.now(timezone.utc),
                    'reviewed_by': str(admin_user['_id']),
                    'reviewer_username': admin_user.get('username', 'Admin'),
                    'rejection_reason': reason,
                    'reviewer_notes': notes
                }
            }
        )
        
        # Update user's KYC status
        users_collection.update_one(
            {'_id': ObjectId(kyc['user_id'])},
            {'$set': {'kyc_status': 'rejected'}}
        )
        
        # Create notification
        create_notification(
            kyc['user_id'],
            'KYC Rejected ❌',
            f'Your KYC verification was rejected. Reason: {reason}. Please submit new documents.',
            'error'
        )
        
        # Send email
        user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
        if user:
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #ef4444; padding: 20px; text-align: center; color: white;">
                    <h1>KYC Rejected</h1>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0;">
                    <p>Dear {user.get('full_name', user.get('username', 'User'))},</p>
                    <p>Unfortunately, your KYC verification has been <strong style="color: #ef4444;">REJECTED</strong>.</p>
                    <div style="background: #fee2e2; padding: 15px; margin: 15px 0;">
                        <strong>Reason:</strong> {reason}
                    </div>
                    <p>Please submit new verification documents with the correct information.</p>
                    <p>If you have any questions, please contact support.</p>
                    <br>
                    <p>Best regards,<br>Veloxtrades Team</p>
                </div>
            </div>
            """
            send_email(user['email'], 'KYC Verification Rejected', f"Dear {user.get('full_name', user.get('username', 'User'))},\n\nYour KYC was rejected.\nReason: {reason}\n\nPlease submit new documents.\n\nBest regards,\nVeloxtrades Team", html_body)
        
        # Log admin action
        log_admin_action(admin_user['_id'], 'KYC Rejected', f'Rejected KYC for user {kyc["username"]}. Reason: {reason}')
        
        response = jsonify({'success': True, 'message': 'KYC application rejected successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin reject KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_stats():
    """Get KYC statistics"""
    if kyc_collection is None:
        return jsonify({'success': True, 'data': {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}}), 200
    
    try:
        pending = kyc_collection.count_documents({'status': 'pending'})
        approved = kyc_collection.count_documents({'status': 'approved'})
        rejected = kyc_collection.count_documents({'status': 'rejected'})
        total = pending + approved + rejected
        
        # Get today's submissions
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_submissions = kyc_collection.count_documents({'submitted_at': {'$gte': today_start}})
        
        response = jsonify({
            'success': True,
            'data': {
                'pending': pending,
                'approved': approved,
                'rejected': rejected,
                'total': total,
                'today_submissions': today_submissions
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get KYC stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN SUPPORT TICKET MANAGEMENT ENDPOINTS ====================

@app.route('/api/admin/support/tickets', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_tickets():
    """Get all support tickets for admin"""
    if support_tickets_collection is None:
        return jsonify({'success': True, 'data': {'tickets': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        category = request.args.get('category', 'all')
        priority = request.args.get('priority', 'all')
        search = request.args.get('search', '')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        if category != 'all':
            query['category'] = category
        if priority != 'all':
            query['priority'] = priority
        
        if search:
            query['$or'] = [
                {'ticket_id': {'$regex': search, '$options': 'i'}},
                {'username': {'$regex': search, '$options': 'i'}},
                {'email': {'$regex': search, '$options': 'i'}},
                {'subject': {'$regex': search, '$options': 'i'}}
            ]
        
        total = support_tickets_collection.count_documents(query)
        tickets = list(support_tickets_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
        result_tickets = []
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if ticket.get('created_at'):
                ticket['created_at'] = ticket['created_at'].isoformat()
            if ticket.get('updated_at'):
                ticket['updated_at'] = ticket['updated_at'].isoformat()
            if ticket.get('closed_at'):
                ticket['closed_at'] = ticket['closed_at'].isoformat()
            
            # Get message count
            ticket['message_count'] = len(ticket.get('messages', []))
            # Get last message
            if ticket.get('messages'):
                last_msg = ticket['messages'][-1]
                ticket['last_message'] = {
                    'sender': last_msg.get('sender'),
                    'sender_name': last_msg.get('sender_name'),
                    'message': last_msg.get('message')[:100],
                    'created_at': last_msg.get('created_at').isoformat() if last_msg.get('created_at') else None
                }
            # Remove full messages from list view
            ticket.pop('messages', None)
            
            result_tickets.append(ticket)
        
        response = jsonify({
            'success': True,
            'data': {
                'tickets': result_tickets,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_ticket(ticket_id):
    """Get single ticket details with full conversation"""
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        if ticket.get('created_at'):
            ticket['created_at'] = ticket['created_at'].isoformat()
        if ticket.get('updated_at'):
            ticket['updated_at'] = ticket['updated_at'].isoformat()
        if ticket.get('closed_at'):
            ticket['closed_at'] = ticket['closed_at'].isoformat()
        
        # Format messages
        for msg in ticket.get('messages', []):
            if msg.get('created_at'):
                msg['created_at'] = msg['created_at'].isoformat()
        
        # Get user details
        if users_collection and ticket.get('user_id'):
            user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
            if user:
                ticket['user_details'] = {
                    '_id': str(user['_id']),
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'full_name': user.get('full_name', ''),
                    'phone': user.get('phone', ''),
                    'wallet_balance': user.get('wallet', {}).get('balance', 0),
                    'kyc_status': user.get('kyc_status', 'pending'),
                    'is_banned': user.get('is_banned', False)
                }
        
        response = jsonify({'success': True, 'data': ticket})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reply_ticket(ticket_id):
    """Admin reply to a support ticket"""
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'message': 'Message is required'}), 400
        
        admin_user = get_user_from_request()
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        # Add admin reply
        reply = {
            'sender': 'admin',
            'sender_id': str(admin_user['_id']),
            'sender_name': admin_user.get('username', 'Admin'),
            'message': message,
            'created_at': datetime.now(timezone.utc)
        }
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$push': {'messages': reply},
                '$set': {
                    'updated_at': datetime.now(timezone.utc),
                    'status': 'pending'  # Waiting for user response
                }
            }
        )
        
        # Send email notification to user
        user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
        if user:
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #10b981; padding: 20px; text-align: center; color: white;">
                    <h1>New Reply to Your Ticket</h1>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0;">
                    <p>Dear {user.get('full_name', user.get('username', 'User'))},</p>
                    <p>You have a new reply to your support ticket <strong>{ticket_id}</strong>.</p>
                    <div style="background: #f3f4f6; padding: 15px; margin: 15px 0;">
                        <strong>Admin Reply:</strong><br>
                        {message.replace(chr(10), '<br>')}
                    </div>
                    <p>Please login to your dashboard to view and reply.</p>
                    <a href="{FRONTEND_URL}/support.html" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">View Ticket</a>
                    <br><br>
                    <p>Best regards,<br>Veloxtrades Support Team</p>
                </div>
            </div>
            """
            send_email(user['email'], f'New Reply to Ticket #{ticket_id}', f"Dear {user.get('full_name', user.get('username', 'User'))},\n\nYou have a new reply to your ticket.\n\nAdmin Reply:\n{message}\n\nLogin to view.\n\nBest regards,\nVeloxtrades Team", html_body)
            
            # Create notification
            create_notification(
                ticket['user_id'],
                f'Support Ticket Updated: {ticket_id}',
                f'Admin has replied to your ticket. Please check your dashboard.',
                'info'
            )
        
        # Log admin action
        log_admin_action(admin_user['_id'], 'Ticket Reply', f'Replied to ticket {ticket_id}')
        
        response = jsonify({'success': True, 'message': 'Reply sent successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>/resolve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resolve_ticket(ticket_id):
    """Resolve/close a support ticket"""
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json() or {}
        resolution_notes = data.get('resolution_notes', '')
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        admin_user = get_user_from_request()
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$set': {
                    'status': 'resolved',
                    'closed_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc),
                    'resolved_by': str(admin_user['_id']),
                    'resolution_notes': resolution_notes
                }
            }
        )
        
        # Notify user
        user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
        if user:
            create_notification(
                ticket['user_id'],
                f'Ticket Resolved: {ticket_id}',
                f'Your support ticket has been marked as resolved. If you need further assistance, please open a new ticket.',
                'success'
            )
            
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #10b981; padding: 20px; text-align: center; color: white;">
                    <h1>Ticket Resolved</h1>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0;">
                    <p>Dear {user.get('full_name', user.get('username', 'User'))},</p>
                    <p>Your support ticket <strong>{ticket_id}</strong> has been marked as <strong style="color: #10b981;">RESOLVED</strong>.</p>
                    {f'<div style="background: #f3f4f6; padding: 15px;"><strong>Resolution Notes:</strong><br>{resolution_notes}</div>' if resolution_notes else ''}
                    <p>If you need further assistance, please open a new ticket.</p>
                    <p>Thank you for choosing Veloxtrades!</p>
                    <br>
                    <p>Best regards,<br>Veloxtrades Support Team</p>
                </div>
            </div>
            """
            send_email(user['email'], f'Ticket #{ticket_id} Resolved', f"Dear {user.get('full_name', user.get('username', 'User'))},\n\nYour ticket {ticket_id} has been resolved.\n\nThank you.\n\nVeloxtrades Team", html_body)
        
        # Log admin action
        log_admin_action(admin_user['_id'], 'Ticket Resolved', f'Resolved ticket {ticket_id}')
        
        response = jsonify({'success': True, 'message': 'Ticket resolved successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin resolve ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>/priority', methods=['PUT', 'OPTIONS'])
@require_admin
def admin_update_ticket_priority(ticket_id):
    """Update ticket priority"""
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        priority = data.get('priority', 'medium')
        
        if priority not in ['low', 'medium', 'high', 'urgent']:
            return jsonify({'success': False, 'message': 'Invalid priority value'}), 400
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        admin_user = get_user_from_request()
        
        support_tickets_collection.update_one(
            {'ticket_id': ticket_id},
            {
                '$set': {
                    'priority': priority,
                    'updated_at': datetime.now(timezone.utc)
                }
            }
        )
        
        # Log admin action
        log_admin_action(admin_user['_id'], 'Ticket Priority Updated', f'Updated ticket {ticket_id} priority to {priority}')
        
        response = jsonify({'success': True, 'message': f'Ticket priority updated to {priority}'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin update ticket priority error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_ticket_stats():
    """Get support ticket statistics"""
    if support_tickets_collection is None:
        return jsonify({'success': True, 'data': {'open': 0, 'pending': 0, 'resolved': 0, 'closed': 0, 'total': 0}}), 200
    
    try:
        open_tickets = support_tickets_collection.count_documents({'status': 'open'})
        pending_tickets = support_tickets_collection.count_documents({'status': 'pending'})
        resolved_tickets = support_tickets_collection.count_documents({'status': 'resolved'})
        closed_tickets = support_tickets_collection.count_documents({'status': 'closed'})
        total = open_tickets + pending_tickets + resolved_tickets + closed_tickets
        
        # Get today's tickets
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_tickets = support_tickets_collection.count_documents({'created_at': {'$gte': today_start}})
        
        # Get tickets by category
        categories = {}
        for cat in ['general', 'deposit', 'withdrawal', 'investment', 'account', 'kyc']:
            categories[cat] = support_tickets_collection.count_documents({'category': cat})
        
        # Get tickets by priority
        priorities = {}
        for pri in ['low', 'medium', 'high', 'urgent']:
            priorities[pri] = support_tickets_collection.count_documents({'priority': pri})
        
        response = jsonify({
            'success': True,
            'data': {
                'open': open_tickets,
                'pending': pending_tickets,
                'resolved': resolved_tickets,
                'closed': closed_tickets,
                'total': total,
                'today_tickets': today_tickets,
                'by_category': categories,
                'by_priority': priorities
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get ticket stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
        
@app.route('/api/admin/referral-stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_referral_stats():
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        all_users = list(users_collection.find(
            {},
            {'_id': 1, 'username': 1, 'email': 1, 'full_name': 1, 'referral_code': 1, 'referred_by': 1, 'created_at': 1, 'wallet.total_deposited': 1}
        ))
        
        referral_network = []
        for user in all_users:
            referral_code = user.get('referral_code', '')
            referrals = [u for u in all_users if u.get('referred_by') == referral_code]
            
            total_commission = 0
            for ref in referrals:
                total_deposited = ref.get('wallet', {}).get('total_deposited', 0)
                total_commission += total_deposited * 0.05
            
            referral_network.append({
                'user_id': str(user['_id']),
                'username': user.get('username', ''),
                'email': user.get('email', ''),
                'full_name': user.get('full_name', ''),
                'referral_code': referral_code,
                'referred_by': user.get('referred_by', 'None'),
                'joined': user.get('created_at').isoformat() if user.get('created_at') else None,
                'total_deposited': user.get('wallet', {}).get('total_deposited', 0),
                'referrals_count': len(referrals),
                'total_commission': total_commission,
                'referrals': [{
                    'username': r.get('username', ''),
                    'email': r.get('email', ''),
                    'joined': r.get('created_at').isoformat() if r.get('created_at') else None,
                    'total_deposited': r.get('wallet', {}).get('total_deposited', 0)
                } for r in referrals]
            })
        
        referral_network.sort(key=lambda x: x['referrals_count'], reverse=True)
        top_referrers = referral_network[:10]
        
        total_users = len(all_users)
        users_with_referrals = len([u for u in referral_network if u['referrals_count'] > 0])
        total_referrals = sum(u['referrals_count'] for u in referral_network)
        total_commission_paid = sum(u['total_commission'] for u in referral_network)
        
        response = jsonify({
            'success': True,
            'data': {
                'stats': {
                    'total_users': total_users,
                    'users_with_referrals': users_with_referrals,
                    'total_referrals': total_referrals,
                    'total_commission_paid': total_commission_paid,
                    'top_referrer': top_referrers[0] if top_referrers else None
                },
                'top_referrers': top_referrers,
                'referral_network': referral_network
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get referral stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
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
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            users_collection.update_one(
                {'_id': ObjectId(deposit['user_id'])},
                {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}}
            )
            deposits_collection.update_one(
                {'_id': ObjectId(deposit_id)}, 
                {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}}
            )
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'deposit_id': deposit['deposit_id'], 'type': 'deposit', 'status': 'pending'},
                    {'$set': {'status': 'completed', 'description': f'Deposit of ${deposit["amount"]} via {deposit["crypto"]} approved'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(deposit['user_id'], 'Deposit Approved! ✅', 
                f'Your deposit of ${deposit["amount"]:,.2f} via {deposit["crypto"]} has been approved and added to your wallet.', 'success')
            
            # Send email notification
            try:
                email_sent = send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
                logger.info(f"Deposit approval email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send deposit approval email: {e}")
            
            # Add referral commission
            try:
                add_referral_commission(deposit['user_id'], deposit['amount'])
            except Exception as e:
                logger.error(f"Failed to add referral commission: {e}")
            
            message = 'Deposit approved successfully and email sent to user'
            
        elif action == 'reject':
            deposits_collection.update_one(
                {'_id': ObjectId(deposit_id)}, 
                {'$set': {'status': 'rejected', 'rejection_reason': reason, 'rejected_at': datetime.now(timezone.utc)}}
            )
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'deposit_id': deposit['deposit_id'], 'type': 'deposit', 'status': 'pending'},
                    {'$set': {'status': 'failed', 'description': f'Deposit of ${deposit["amount"]} rejected: {reason}'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(deposit['user_id'], 'Deposit Rejected ❌', 
                f'Your deposit of ${deposit["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            
            # Send rejection email
            try:
                email_sent = send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], reason)
                logger.info(f"Deposit rejection email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send deposit rejection email: {e}")
            
            message = 'Deposit rejected and email sent to user'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process deposit error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits/<deposit_id>/resend-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_email(deposit_id):
    if deposits_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        email_sent = False
        if deposit['status'] == 'approved':
            email_sent = send_deposit_approved_email(
                user, 
                deposit['amount'], 
                deposit['crypto'], 
                deposit.get('transaction_hash', '')
            )
        elif deposit['status'] == 'rejected':
            email_sent = send_deposit_rejected_email(
                user, 
                deposit['amount'], 
                deposit['crypto'], 
                deposit.get('rejection_reason', 'Not specified')
            )
        else:
            return jsonify({'success': False, 'message': 'Deposit not processed yet (status: ' + deposit['status'] + ')'}), 400
        
        if email_sent:
            response = jsonify({'success': True, 'message': 'Email resent successfully'})
        else:
            response = jsonify({'success': False, 'message': 'Failed to send email'}), 500
        
        return add_cors_headers(response)
            
    except Exception as e:
        logger.error(f"Resend email error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN BROADCAST ENDPOINTS ====================

@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast_email():
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
        
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #10b981, #059669); padding: 20px; text-align: center; color: white;">
                <h1>Veloxtrades</h1>
            </div>
            <div style="padding: 20px; border: 1px solid #e2e8f0; border-top: none;">
                <h2>{subject}</h2>
                <p>{message.replace(chr(10), '<br>')}</p>
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">This is an automated broadcast message from Veloxtrades.</p>
            </div>
        </div>
        """
        
        sent_count = 0
        for user in users:
            try:
                if send_email(user['email'], subject, message, html_body):
                    create_notification(user['_id'], subject, message, 'info')
                    sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user['email']}: {e}")
        
        response = jsonify({
            'success': True, 
            'message': f'Broadcast sent to {sent_count} out of {len(users)} users', 
            'data': {'sent': sent_count, 'total': len(users)}
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/resend-deposit-emails', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_emails():
    if deposits_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json() or {}
        status_filter = data.get('status', 'approved')
        
        query = {}
        if status_filter == 'approved':
            query['status'] = 'approved'
        elif status_filter == 'rejected':
            query['status'] = 'rejected'
        elif status_filter == 'all':
            query['status'] = {'$in': ['approved', 'rejected']}
        else:
            query['status'] = 'approved'
        
        deposits = list(deposits_collection.find(query))
        
        if not deposits:
            response = jsonify({
                'success': True,
                'message': 'No deposits found to resend emails',
                'data': {'sent': 0, 'failed': 0}
            })
            return add_cors_headers(response)
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        for deposit in deposits:
            try:
                user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
                if not user:
                    failed_count += 1
                    errors.append(f"User not found for deposit {deposit.get('deposit_id', 'unknown')}")
                    continue
                
                email_sent = False
                if deposit['status'] == 'approved':
                    email_sent = send_deposit_approved_email(
                        user, 
                        deposit['amount'], 
                        deposit['crypto'], 
                        deposit.get('transaction_hash', '')
                    )
                elif deposit['status'] == 'rejected':
                    email_sent = send_deposit_rejected_email(
                        user, 
                        deposit['amount'], 
                        deposit['crypto'], 
                        deposit.get('rejection_reason', 'Not specified')
                    )
                
                if email_sent:
                    sent_count += 1
                    logger.info(f"✅ Resent email for deposit {deposit.get('deposit_id', 'unknown')} to {user['email']}")
                else:
                    failed_count += 1
                    errors.append(f"Failed to send email for deposit {deposit.get('deposit_id', 'unknown')}")
                    
            except Exception as e:
                failed_count += 1
                errors.append(f"Error for deposit {deposit.get('deposit_id', 'unknown')}: {str(e)}")
                logger.error(f"Error resending email: {e}")
        
        response = jsonify({
            'success': True,
            'message': f'✅ Emails resent: {sent_count} sent, {failed_count} failed',
            'data': {
                'sent': sent_count,
                'failed': failed_count,
                'errors': errors[:10]
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Resend emails error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_withdrawals():
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
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            withdrawals_collection.update_one(
                {'_id': ObjectId(withdrawal_id)}, 
                {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}}
            )
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'},
                    {'$set': {'status': 'completed', 'description': f'Withdrawal of ${withdrawal["amount"]} approved and sent'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(withdrawal['user_id'], 'Withdrawal Approved! ✅', 
                f'Your withdrawal of ${withdrawal["amount"]:,.2f} has been approved and sent to your wallet.', 'success')
            
            # Send approval email
            try:
                email_sent = send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
                logger.info(f"Withdrawal approval email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send withdrawal approval email: {e}")
            
            message = 'Withdrawal approved successfully and email sent to user'
            
        elif action == 'reject':
            withdrawals_collection.update_one(
                {'_id': ObjectId(withdrawal_id)}, 
                {'$set': {'status': 'rejected', 'rejection_reason': reason, 'rejected_at': datetime.now(timezone.utc)}}
            )
            
            # Return funds to user
            users_collection.update_one(
                {'_id': ObjectId(withdrawal['user_id'])},
                {'$inc': {'wallet.balance': withdrawal['amount']}}
            )
            
            if transactions_collection is not None:
                transactions_collection.update_one(
                    {'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'},
                    {'$set': {'status': 'failed', 'description': f'Withdrawal of ${withdrawal["amount"]} rejected: {reason}'}},
                    sort=[('created_at', -1)]
                )
            
            create_notification(withdrawal['user_id'], 'Withdrawal Rejected ❌', 
                f'Your withdrawal of ${withdrawal["amount"]:,.2f} was rejected. Reason: {reason}', 'error')
            
            # Send rejection email
            try:
                email_sent = send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
                logger.info(f"Withdrawal rejection email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send withdrawal rejection email: {e}")
            
            message = 'Withdrawal rejected, funds returned, and email sent to user'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        response = jsonify({'success': True, 'message': message})
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
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

@app.route('/api/admin/investments/<investment_id>/complete', methods=['POST', 'OPTIONS'])
@require_admin
def admin_complete_investment(investment_id):
    if investments_collection is None or users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        investment = investments_collection.find_one({'_id': ObjectId(investment_id)})
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        
        if investment['status'] != 'active':
            return jsonify({'success': False, 'message': 'Investment already completed'}), 400
        
        user_id = investment['user_id']
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
            
        amount = investment['amount']
        expected_profit = investment.get('expected_profit', 0)
        plan_name = investment.get('plan_name', 'Investment')
        
        result = users_collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'wallet.balance': expected_profit, 'wallet.total_profit': expected_profit}}
        )
        
        if result.modified_count > 0:
            investments_collection.update_one(
                {'_id': ObjectId(investment_id)},
                {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc), 'completed_by_admin': True}}
            )
            
            transactions_collection.insert_one({
                'user_id': user_id,
                'type': 'profit',
                'amount': expected_profit,
                'status': 'completed',
                'description': f'Profit from {plan_name} (Manually completed by admin)',
                'investment_id': str(investment_id),
                'created_at': datetime.now(timezone.utc)
            })
            
            create_notification(user_id, 'Investment Completed! 🎉', 
                f'Your investment of ${amount:,.2f} has been completed. You earned ${expected_profit:,.2f} profit!', 'success')
            
            # Send completion email
            try:
                email_sent = send_investment_completed_email(user, amount, plan_name, expected_profit)
                logger.info(f"Investment completion email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send investment completion email: {e}")
            
            response = jsonify({'success': True, 'message': 'Investment completed successfully and email sent', 'data': {'profit_added': expected_profit}})
        else:
            response = jsonify({'success': False, 'message': 'Failed to update user balance'}), 500
        
        return add_cors_headers(response)
            
    except Exception as e:
        logger.error(f"Complete investment error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/create-investment', methods=['POST', 'OPTIONS'])
@require_admin
def admin_create_investment():
    if investments_collection is None or users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        plan_type = data.get('plan_type')
        amount = float(data.get('amount', 0))
        add_referral_bonus = data.get('add_referral_bonus', True)
        deduct_from_balance = data.get('deduct_from_balance', True)
        
        if not user_id or not plan_type:
            return jsonify({'success': False, 'message': 'User ID and plan type required'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        plan = INVESTMENT_PLANS.get(plan_type)
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid investment plan'}), 400
        
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum investment is ${plan["min_deposit"]}'}), 400
        
        if deduct_from_balance and user['wallet']['balance'] < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        expected_profit = amount * plan['roi'] / 100
        end_date = datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])
        
        if deduct_from_balance:
            users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}}
            )
        
        investment_data = {
            'user_id': user_id,
            'username': user['username'],
            'plan': plan_type,
            'plan_name': plan['name'],
            'amount': amount,
            'roi': plan['roi'],
            'expected_profit': expected_profit,
            'duration_hours': plan['duration_hours'],
            'start_date': datetime.now(timezone.utc),
            'end_date': end_date,
            'status': 'active',
            'created_by_admin': True
        }
        
        result = investments_collection.insert_one(investment_data)
        
        transactions_collection.insert_one({
            'user_id': user_id,
            'type': 'investment',
            'amount': amount,
            'status': 'completed',
            'description': f'Investment in {plan["name"]} (Admin created)',
            'investment_id': str(result.inserted_id),
            'created_at': datetime.now(timezone.utc)
        })
        
        referral_bonus_added = 0
        if add_referral_bonus and user.get('referral_code'):
            settings = settings_collection.find_one({}) if settings_collection else None
            bonus_percentage = settings.get('referral_bonus', 5) if settings else 5
            referral_bonus = amount * bonus_percentage / 100
            
            if referral_bonus > 0:
                referrer = users_collection.find_one({'referral_code': user.get('referred_by')}) if user.get('referred_by') else None
                
                if referrer:
                    users_collection.update_one(
                        {'_id': ObjectId(referrer['_id'])},
                        {'$inc': {'wallet.balance': referral_bonus, 'wallet.total_profit': referral_bonus}}
                    )
                    
                    transactions_collection.insert_one({
                        'user_id': str(referrer['_id']),
                        'type': 'bonus',
                        'amount': referral_bonus,
                        'status': 'completed',
                        'description': f'Referral bonus from {user["username"]}\'s investment of ${amount:,.2f}',
                        'created_at': datetime.now(timezone.utc)
                    })
                    
                    create_notification(referrer['_id'], 'Referral Bonus! 🎉', 
                        f'You earned ${referral_bonus:,.2f} from {user["username"]}\'s investment!', 'success')
                    
                    referral_bonus_added = referral_bonus
        
        create_notification(user_id, 'Investment Created! 🚀', 
            f'Your investment of ${amount:,.2f} in {plan["name"]} has been created. Expected profit: ${expected_profit:,.2f}', 'success')
        
        # Send confirmation email
        try:
            email_sent = send_investment_confirmation_email(user, amount, plan['name'], plan['roi'], expected_profit)
            logger.info(f"Investment confirmation email sent to {user['email']}: {email_sent}")
        except Exception as e:
            logger.error(f"Failed to send investment confirmation email: {e}")
        
        response = jsonify({
            'success': True,
            'message': f'Investment created successfully for {user["username"]}',
            'data': {
                'investment_id': str(result.inserted_id),
                'expected_profit': expected_profit,
                'end_date': end_date.isoformat(),
                'referral_bonus_added': referral_bonus_added
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin create investment error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500
# ==================== ADMIN RESEND EMAILS ENDPOINT ====================

@app.route('/api/admin/resend-deposit-emails', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_emails():
    if deposits_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json() or {}
        status_filter = data.get('status', 'approved')
        
        # Build query based on status filter
        if status_filter == 'approved':
            query = {'status': 'approved'}
        elif status_filter == 'rejected':
            query = {'status': 'rejected'}
        else:
            query = {'status': {'$in': ['approved', 'rejected']}}
        
        deposits = list(deposits_collection.find(query))
        
        if not deposits:
            response = jsonify({
                'success': True,
                'message': 'No deposits found to resend emails',
                'data': {'sent': 0, 'failed': 0}
            })
            return add_cors_headers(response)
        
        sent_count = 0
        failed_count = 0
        
        for deposit in deposits:
            try:
                user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
                if not user:
                    failed_count += 1
                    continue
                
                if deposit['status'] == 'approved':
                    email_sent = send_deposit_approved_email(
                        user, 
                        deposit['amount'], 
                        deposit['crypto'], 
                        deposit.get('transaction_hash', '')
                    )
                else:
                    email_sent = send_deposit_rejected_email(
                        user, 
                        deposit['amount'], 
                        deposit['crypto'], 
                        deposit.get('rejection_reason', 'Not specified')
                    )
                
                if email_sent:
                    sent_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error resending email for deposit {deposit.get('deposit_id')}: {e}")
        
        response = jsonify({
            'success': True,
            'message': f'Emails resent: {sent_count} sent, {failed_count} failed',
            'data': {'sent': sent_count, 'failed': failed_count}
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Resend emails error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/deposits/<deposit_id>/resend-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_single_deposit_email(deposit_id):
    if deposits_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if deposit['status'] == 'approved':
            email_sent = send_deposit_approved_email(
                user, 
                deposit['amount'], 
                deposit['crypto'], 
                deposit.get('transaction_hash', '')
            )
        elif deposit['status'] == 'rejected':
            email_sent = send_deposit_rejected_email(
                user, 
                deposit['amount'], 
                deposit['crypto'], 
                deposit.get('rejection_reason', 'Not specified')
            )
        else:
            return jsonify({'success': False, 'message': 'Deposit not processed yet'}), 400
        
        if email_sent:
            response = jsonify({'success': True, 'message': 'Email resent successfully'})
        else:
            response = jsonify({'success': False, 'message': 'Failed to send email'}), 500
        
        return add_cors_headers(response)
            
    except Exception as e:
        logger.error(f"Resend email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/api/admin/create-transaction', methods=['POST', 'OPTIONS'])
@require_admin
def admin_create_transaction():
    if users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        transaction_type = data.get('type', 'adjustment')
        amount = float(data.get('amount', 0))
        description = data.get('description', 'Manual transaction')
        add_to_balance = data.get('add_to_balance', True)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID required'}), 400
        
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Amount must be greater than 0'}), 400
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        transaction_data = {
            'user_id': user_id,
            'type': transaction_type,
            'amount': amount,
            'status': 'completed',
            'description': f'{description} (Admin created)',
            'created_at': datetime.now(timezone.utc),
            'admin_created': True
        }
        
        result = transactions_collection.insert_one(transaction_data)
        
        if add_to_balance:
            update_result = users_collection.update_one(
                {'_id': ObjectId(user_id)},
                {'$inc': {'wallet.balance': amount}}
            )
            
            if update_result.modified_count > 0:
                create_notification(user_id, f'{transaction_type.capitalize()} Added! 🎉', 
                    f'${amount:,.2f} has been added to your account. Reason: {description}', 'success')
                
                new_balance = user.get('wallet', {}).get('balance', 0) + amount
                
                response = jsonify({
                    'success': True,
                    'message': f'Transaction created and ${amount:,.2f} added to user balance',
                    'data': {
                        'transaction_id': str(result.inserted_id),
                        'new_balance': new_balance
                    }
                })
                return add_cors_headers(response)
            else:
                response = jsonify({'success': False, 'message': 'Failed to update user balance'}), 500
                return add_cors_headers(response)
        else:
            response = jsonify({
                'success': True,
                'message': 'Transaction created (balance not updated)',
                'data': {'transaction_id': str(result.inserted_id)}
            })
            return add_cors_headers(response)
            
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_transactions():
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
        
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #10b981, #059669); padding: 20px; text-align: center; color: white;">
                <h1>Veloxtrades</h1>
            </div>
            <div style="padding: 20px; border: 1px solid #e2e8f0; border-top: none;">
                <h2>{subject}</h2>
                <p>{message.replace(chr(10), '<br>')}</p>
                <hr style="margin: 20px 0;">
                <p style="color: #666; font-size: 12px;">This is an automated message from Veloxtrades.</p>
            </div>
        </div>
        """
        
        email_sent = send_email(user['email'], subject, message, html_body)
        
        if email_sent:
            create_notification(user_id, subject, message, 'info')
            response = jsonify({'success': True, 'message': f'Email sent to {user["email"]}'})
        else:
            response = jsonify({'success': False, 'message': 'Failed to send email'}), 500
        
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Send email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500



@app.route('/api/admin/reset-all', methods=['GET'])
def reset_all_admin():
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
