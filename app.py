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
import sys
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
from pymongo import MongoClient, errors
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from functools import wraps
from urllib.parse import urlparse

sys.stdout.flush()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='static')

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'veloxtrades-secret-key-2024')
app.config['MONGO_URI'] = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
app.config['JWT_SECRET'] = os.getenv('JWT_SECRET', 'jwt-secret-key-change-this')
app.config['JWT_EXPIRATION_DAYS'] = 30

# ==================== DUAL DATABASE CONFIGURATION ====================
DB_VELOXTRADES = 'veloxtrades_db'
DB_INVESTMENT = 'investment_db'

import certifi

client = None
veloxtrades_db = None
investment_db = None

# veloxtrades_db collections
veloxtrades_users = None
veloxtrades_transactions = None
veloxtrades_notifications = None
veloxtrades_kyc = None
veloxtrades_support_tickets = None
veloxtrades_admin_logs = None
veloxtrades_settings = None
veloxtrades_email_logs = None
veloxtrades_investments = None
veloxtrades_deposits = None
veloxtrades_withdrawals = None
veloxtrades_referral_stats = None

# investment_db collections
investment_users = None
investment_transactions = None
investment_notifications = None
investment_kyc = None
investment_support_tickets = None
investment_admin_logs = None
investment_settings = None
investment_email_logs = None
investment_investments = None
investment_deposits = None
investment_withdrawals = None
investment_referral_stats = None

# Combined collections
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

import signal
import sys

def signal_handler(sig, frame):
    print(f"Signal {sig} received, cleaning up...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)
class DualDatabaseCollection:
    def __init__(self, collections, name):
        # Filter out None collections
        self.collections = [c for c in collections if c is not None]
        self.name = name

    def __bool__(self):
        """Return True only if there are actual database collections"""
        return len(self.collections) > 0

    def __len__(self):
        """Return number of underlying collections"""
        return len(self.collections)
    
    # Rest of your methods remain the same...
    def find(self, query=None, *args, **kwargs):
        results = []
        for collection in self.collections:
            try:
                if collection is not None:
                    results.extend(list(collection.find(query or {}, *args, **kwargs)))
            except Exception as e:
                logger.error(f"Error searching {self.name}: {e}")
        return results

    def find_one(self, query=None, *args, **kwargs):
        for collection in self.collections:
            try:
                if collection is not None:
                    result = collection.find_one(query or {}, *args, **kwargs)
                    if result:
                        return result
            except Exception:
                continue
        return None

    def insert_one(self, document, *args, **kwargs):
        for collection in self.collections:
            try:
                if collection is not None:
                    return collection.insert_one(document, *args, **kwargs)
            except Exception:
                continue
        raise Exception(f"Failed to insert into any {self.name} collection")

    def update_one(self, filter, update, *args, **kwargs):
        updated = False
        for collection in self.collections:
            try:
                if collection is not None:
                    if collection.update_one(filter, update, *args, **kwargs).modified_count > 0:
                        updated = True
            except Exception as e:
                logger.error(f"Error updating {self.name}: {e}")
        return updated

    def update_many(self, filter, update, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                if collection is not None:
                    total += collection.update_many(filter, update, *args, **kwargs).modified_count
            except Exception as e:
                logger.error(f"Error updating many {self.name}: {e}")
        return total

    def delete_one(self, filter, *args, **kwargs):
        deleted = False
        for collection in self.collections:
            try:
                if collection is not None:
                    if collection.delete_one(filter, *args, **kwargs).deleted_count > 0:
                        deleted = True
            except Exception as e:
                logger.error(f"Error deleting from {self.name}: {e}")
        return deleted

    def delete_many(self, filter, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                if collection is not None:
                    total += collection.delete_many(filter, *args, **kwargs).deleted_count
            except Exception as e:
                logger.error(f"Error deleting many from {self.name}: {e}")
        return total

    def count_documents(self, filter=None, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                if collection is not None:
                    total += collection.count_documents(filter or {}, *args, **kwargs)
            except Exception:
                continue
        return total

    def distinct(self, key, filter=None, *args, **kwargs):
        all_values = []
        for collection in self.collections:
            try:
                if collection is not None:
                    all_values.extend(collection.distinct(key, filter or {}, *args, **kwargs))
            except Exception:
                continue
        return list(dict.fromkeys(all_values))

    def aggregate(self, pipeline, *args, **kwargs):
        all_results = []
        for collection in self.collections:
            try:
                if collection is not None:
                    all_results.extend(list(collection.aggregate(pipeline, *args, **kwargs)))
            except Exception as e:
                logger.error(f"Error aggregating in {self.name}: {e}")
        return all_results

    def create_index(self, keys, *args, **kwargs):
        for collection in self.collections:
            try:
                if collection is not None:
                    collection.create_index(keys, *args, **kwargs)
            except Exception:
                continue


def connect_to_databases():
    global client, veloxtrades_db, investment_db
    global veloxtrades_users, veloxtrades_transactions, veloxtrades_notifications, veloxtrades_kyc
    global veloxtrades_support_tickets, veloxtrades_admin_logs, veloxtrades_settings, veloxtrades_email_logs
    global veloxtrades_investments, veloxtrades_deposits, veloxtrades_withdrawals, veloxtrades_referral_stats
    global investment_users, investment_transactions, investment_notifications, investment_kyc
    global investment_support_tickets, investment_admin_logs, investment_settings, investment_email_logs
    global investment_investments, investment_deposits, investment_withdrawals, investment_referral_stats
    global users_collection, investments_collection, transactions_collection, deposits_collection
    global withdrawals_collection, notifications_collection, kyc_collection, support_tickets_collection
    global admin_logs_collection, settings_collection, email_logs_collection, referral_stats_collection

    try:
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        logger.info("✅ MongoDB connection successful")

        veloxtrades_db = client[DB_VELOXTRADES]
        investment_db = client[DB_INVESTMENT]

        # Initialize veloxtrades_db collections
        veloxtrades_users = veloxtrades_db['users']
        veloxtrades_transactions = veloxtrades_db['transactions']
        veloxtrades_notifications = veloxtrades_db['notifications']
        veloxtrades_kyc = veloxtrades_db['kyc']
        veloxtrades_support_tickets = veloxtrades_db['support_tickets']
        veloxtrades_admin_logs = veloxtrades_db['admin_logs']
        veloxtrades_settings = veloxtrades_db['settings']
        veloxtrades_email_logs = veloxtrades_db['email_logs']
        veloxtrades_investments = veloxtrades_db['investments']
        veloxtrades_deposits = veloxtrades_db['deposits']
        veloxtrades_withdrawals = veloxtrades_db['withdrawals']
        veloxtrades_referral_stats = veloxtrades_db['referral_stats']

        # Initialize investment_db collections
        investment_users = investment_db['users']
        investment_transactions = investment_db['transactions']
        investment_notifications = investment_db['notifications']
        investment_kyc = investment_db['kyc']
        investment_support_tickets = investment_db['support_tickets']
        investment_admin_logs = investment_db['admin_logs']
        investment_settings = investment_db['settings']
        investment_email_logs = investment_db['email_logs']
        investment_investments = investment_db['investments']
        investment_deposits = investment_db['deposits']
        investment_withdrawals = investment_db['withdrawals']
        investment_referral_stats = investment_db['referral_stats']

        # Create combined collections (search across both databases)
        users_collection = DualDatabaseCollection([veloxtrades_users, investment_users], 'users')
        investments_collection = DualDatabaseCollection([veloxtrades_investments, investment_investments], 'investments')
        transactions_collection = DualDatabaseCollection([veloxtrades_transactions, investment_transactions], 'transactions')
        deposits_collection = DualDatabaseCollection([veloxtrades_deposits, investment_deposits], 'deposits')
        withdrawals_collection = DualDatabaseCollection([veloxtrades_withdrawals, investment_withdrawals], 'withdrawals')
        notifications_collection = DualDatabaseCollection([veloxtrades_notifications, investment_notifications], 'notifications')
        kyc_collection = DualDatabaseCollection([veloxtrades_kyc, investment_kyc], 'kyc')
        support_tickets_collection = DualDatabaseCollection([veloxtrades_support_tickets, investment_support_tickets], 'support_tickets')
        admin_logs_collection = DualDatabaseCollection([veloxtrades_admin_logs, investment_admin_logs], 'admin_logs')
        settings_collection = DualDatabaseCollection([veloxtrades_settings, investment_settings], 'settings')
        email_logs_collection = DualDatabaseCollection([veloxtrades_email_logs, investment_email_logs], 'email_logs')
        referral_stats_collection = DualDatabaseCollection([veloxtrades_referral_stats, investment_referral_stats], 'referral_stats')

        logger.info("✅ DUAL DATABASE CONFIGURATION: Both databases connected")
        return True
    except Exception as e:
        logger.error(f"❌ MongoDB connection error: {e}")
        return False


db_connected = connect_to_databases()
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://www.veloxtrades.com.ng')
BACKEND_URL = os.getenv('BACKEND_URL', 'https://investment-gto3.onrender.com')
ADMIN_RESET_SECRET = os.getenv('ADMIN_RESET_SECRET', 'veloxtrades-admin-reset-2025')

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

# ==================== SINGLE CORS CONFIGURATION ====================
# Handle OPTIONS preflight requests
@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        origin = request.headers.get('Origin', '')
        
        # Set allowed origin
        if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
        response.headers['Access-Control-Max-Age'] = '86400'  # Cache preflight for 24 hours
        
        return response


# Handle CORS headers for all responses
@app.after_request
def add_cors_headers(response):
    # Skip if it's an OPTIONS request (already handled)
    if request.method == "OPTIONS":
        return response
    
    origin = request.headers.get('Origin', '')
    
    # Set allowed origin
    if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
    
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
    
    return response
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
        user_id = payload.get('user_id')
        if not user_id:
            return None
        
        # Convert to ObjectId if possible
        try:
            obj_id = ObjectId(user_id)
        except:
            obj_id = user_id
        
        # Search in veloxtrades_users first
        if veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'_id': obj_id})
                if user:
                    print(f"✅ Found user in veloxtrades_users: {user.get('username')}")
                    return user
            except Exception as e:
                print(f"Error searching veloxtrades_users: {e}")
        
        # Search in investment_users
        if investment_users is not None:
            try:
                user = investment_users.find_one({'_id': obj_id})
                if user:
                    print(f"✅ Found user in investment_users: {user.get('username')}")
                    return user
            except Exception as e:
                print(f"Error searching investment_users: {e}")
        
        # Search in combined collection as last resort
        if users_collection is not None:
            try:
                user = users_collection.find_one({'_id': obj_id})
                if user:
                    print(f"✅ Found user in combined collection: {user.get('username')}")
                    return user
            except Exception as e:
                print(f"Error searching combined collection: {e}")
        
        print(f"❌ User with ID {user_id} not found in any database")
        return None
    except Exception as e:
        logger.error(f"Error getting user: {e}")
        return None
# ==================== EMAIL CONFIGURATION ====================
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'Veloxtrades')
EMAIL_CONFIGURED = bool(EMAIL_USER and EMAIL_PASSWORD and EMAIL_HOST)


def send_email(to_email, subject, body, html_body=None, max_retries=3):
    if not EMAIL_CONFIGURED:
        logger.error("❌ Email not configured")
        return False
    if not to_email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
        return False
    for attempt in range(max_retries):
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{EMAIL_FROM} <{EMAIL_USER}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=30) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASSWORD)
                server.send_message(msg)
            logger.info(f"✅ Email sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Email error (attempt {attempt+1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return False


def check_email_configuration():
    if not EMAIL_CONFIGURED:
        return False, "Email credentials not configured"
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
        return True, "Email configuration is valid"
    except Exception as e:
        return False, f"Email error: {str(e)}"

def send_investment_rejected_email(user, amount, plan_name, reason):
    try:
        subject = f"❌ Investment Request Rejected - ${amount:,.2f}"
        user_name = user.get('full_name', user.get('username', 'User'))
        user_email = user.get('email')
        
        plain_body = f"""Dear {user_name},

Your investment request of ${amount:,.2f} in {plan_name} was REJECTED.

Reason: {reason}

The amount of ${amount:,.2f} has been refunded to your balance.

Best regards,
Veloxtrades Team"""
        
        content = f'<p>Dear {user_name},</p><div style="background:#fee2e2;padding:15px;"><p><strong>❌ INVESTMENT REJECTED</strong></p><p>Amount: ${amount:,.2f}<br>Plan: {plan_name}<br>Reason: {reason}</p><p>Your funds have been refunded.</p></div>'
        html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
        
        return send_email(user_email, subject, plain_body, html_body)
    except Exception as e:
        print(f"❌ Error in send_investment_rejected_email: {e}")
        return False
# ==================== HELPER FUNCTIONS ====================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def collection_has_data(collection):
    """Check if a DualDatabaseCollection has any actual database collections"""
    if collection is None:
        return False
    if hasattr(collection, 'collections'):
        return len(collection.collections) > 0
    return collection is not None
def verify_password(hashed_password, password):
    try:
        if not hashed_password:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def safe_collection(collection):
    """Safely check if a collection exists"""
    return collection is not None
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
    except Exception:
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
        user_id = payload.get('user_id')
        if not user_id:
            return None
        # Search in combined collections first
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if user:
                return user
        # Fallback to individual databases
        if veloxtrades_users is not None:
            user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
            if user:
                return user
        if investment_users is not None:
            return investment_users.find_one({'_id': ObjectId(user_id)})
        return None
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
    notification_data = {
        'user_id': str(user_id), 'title': title, 'message': message,
        'type': type, 'read': False, 'created_at': datetime.now(timezone.utc)
    }
    if veloxtrades_notifications is not None:
        try:
            veloxtrades_notifications.insert_one(notification_data)
        except Exception as e:
            logger.error(f"Failed to create notification in veloxtrades_db: {e}")
    if investment_notifications is not None:
        try:
            investment_notifications.insert_one(notification_data)
        except Exception as e:
            logger.error(f"Failed to create notification in investment_db: {e}")


def log_admin_action(admin_id, action, details):
    log_data = {
        'admin_id': str(admin_id), 'action': action, 'details': details,
        'ip_address': request.remote_addr, 'created_at': datetime.now(timezone.utc)
    }
    if veloxtrades_admin_logs is not None:
        try:
            veloxtrades_admin_logs.insert_one(log_data)
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")
    if investment_admin_logs is not None:
        try:
            investment_admin_logs.insert_one(log_data)
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")


def add_referral_commission(user_id, deposit_amount):
    try:
        logger.info(f"Adding referral commission for user {user_id}, amount ${deposit_amount}")
        
        if users_collection is None:
            logger.warning("users_collection is None, skipping referral commission")
            return False
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            logger.warning(f"User {user_id} not found")
            return False
        
        referred_by_code = user.get('referred_by')
        if not referred_by_code:
            logger.info(f"User {user_id} has no referrer")
            return False
        
        referrer = users_collection.find_one({'referral_code': referred_by_code})
        if not referrer:
            logger.warning(f"Referrer with code {referred_by_code} not found")
            return False
        
        if settings_collection is not None:
            settings = settings_collection.find_one({})
            bonus_percentage = settings.get('referral_bonus', 5) if settings else 5
        else:
            bonus_percentage = 5
        
        commission = deposit_amount * (bonus_percentage / 100)
        if commission <= 0:
            logger.info(f"Commission ${commission} is zero or negative")
            return False
        
        logger.info(f"Adding commission ${commission} to referrer {referrer.get('username')}")
        
        # Update referrer balance
        if veloxtrades_users is not None:
            veloxtrades_users.update_one(
                {'_id': referrer['_id']}, 
                {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}}
            )
        if investment_users is not None:
            investment_users.update_one(
                {'_id': referrer['_id']}, 
                {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}}
            )
        
        # Create transaction record
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(referrer['_id']), 
                'type': 'commission', 
                'amount': commission, 
                'status': 'completed',
                'description': f'Commission from {user["username"]}\'s deposit of ${deposit_amount:,.2f}',
                'created_at': datetime.now(timezone.utc)
            })
        
        # Create notification
        create_notification(
            referrer['_id'], 
            'Referral Commission! 🎉', 
            f'Earned ${commission:,.2f} from {user["username"]}\'s deposit!', 
            'success'
        )
        
        logger.info(f"Successfully added referral commission")
        return True
        
    except Exception as e:
        logger.error(f"Error adding referral commission: {e}", exc_info=True)
        return False


# ==================== EMAIL TEMPLATES ====================
def get_email_template(title, content, button_text=None, button_link=None):
    button_html = ''
    if button_text and button_link:
        button_html = f'<div style="text-align:center;margin:30px 0;"><a href="{button_link}" style="background:#10b981;color:white;padding:12px 30px;text-decoration:none;border-radius:5px;">{button_text}</a></div>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title>
    <style>body{{font-family:Arial,sans-serif;background:#f5f5f5;margin:0;padding:0;}} .container{{max-width:600px;margin:0 auto;padding:20px;}} .header{{background:linear-gradient(135deg,#10b981,#059669);color:white;padding:30px;text-align:center;border-radius:10px 10px 0 0;}} .content{{background:white;padding:30px;border-radius:0 0 10px 10px;}} .footer{{text-align:center;padding:20px;font-size:12px;color:#666;}}</style>
    </head><body><div class="container"><div class="header"><h1>VELOXTRADES</h1></div><div class="content"><h2>{title}</h2>{content}{button_html}</div><div class="footer"><p>© 2025 Veloxtrades</p></div></div></body></html>'''

def send_deposit_approved_email(user, amount, crypto, transaction_hash):
    try:
        subject = f"✅ Deposit Approved - ${amount:,.2f} added"
        user_name = user.get('full_name', user.get('username', 'User'))
        user_email = user.get('email')
        
        print(f"📧 Sending approval email to: {user_email}")
        
        plain_body = f"""Dear {user_name},

Your deposit of ${amount:,.2f} has been APPROVED!

Amount: ${amount:,.2f}
Method: {crypto.upper()}
Transaction: {transaction_hash or 'N/A'}

Thank you for choosing Veloxtrades!

Best regards,
Veloxtrades Team"""
        
        content = f'<p>Dear {user_name},</p><div style="background:#d1fae5;padding:15px;"><p><strong>✅ DEPOSIT APPROVED!</strong></p><p>Amount: ${amount:,.2f}</p><p>Method: {crypto.upper()}</p></div>'
        html_body = get_email_template(subject, content, 'Go to Dashboard', f'{FRONTEND_URL}/dashboard.html')
        
        result = send_email(user_email, subject, plain_body, html_body)
        print(f"📧 Email send result: {result}")
        return result
    except Exception as e:
        print(f"❌ Error in send_deposit_approved_email: {e}")
        import traceback
        traceback.print_exc()
        return False

def send_deposit_rejected_email(user, amount, crypto, reason):
    subject = f"❌ Deposit Rejected - ${amount:,.2f}"
    user_name = user.get('full_name', user.get('username', 'User'))
    plain_body = f"Dear {user_name},\n\nYour deposit of ${amount:,.2f} was REJECTED.\n\nReason: {reason}\n\nPlease contact support."
    content = f'<p>Dear {user_name},</p><div style="background:#fee2e2;padding:15px;"><p><strong>❌ DEPOSIT REJECTED</strong></p><p>Reason: {reason}</p></div>'
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/deposit.html')
    return send_email(user['email'], subject, plain_body, html_body)


def send_withdrawal_approved_email(user, amount, currency, wallet_address):
    subject = f"✅ Withdrawal Approved - ${amount:,.2f}"
    user_name = user.get('full_name', user.get('username', 'User'))
    plain_body = f"Dear {user_name},\n\nYour withdrawal of ${amount:,.2f} has been APPROVED!\n\nAmount: ${amount:,.2f}\nWallet: {wallet_address}"
    content = f'<p>Dear {user_name},</p><div style="background:#d1fae5;padding:15px;"><p><strong>✅ WITHDRAWAL APPROVED!</strong></p><p>Amount: ${amount:,.2f}</p></div>'
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, plain_body, html_body)


def send_withdrawal_rejected_email(user, amount, currency, reason):
    subject = f"❌ Withdrawal Rejected - ${amount:,.2f}"
    user_name = user.get('full_name', user.get('username', 'User'))
    plain_body = f"Dear {user_name},\n\nYour withdrawal of ${amount:,.2f} was REJECTED.\n\nReason: {reason}"
    content = f'<p>Dear {user_name},</p><div style="background:#fee2e2;padding:15px;"><p><strong>❌ WITHDRAWAL REJECTED</strong></p><p>Reason: {reason}</p></div>'
    html_body = get_email_template(subject, content, 'Try Again', f'{FRONTEND_URL}/withdraw.html')
    return send_email(user['email'], subject, plain_body, html_body)


def send_investment_confirmation_email(user, amount, plan_name, roi, expected_profit):
    subject = f"🚀 Investment Confirmed - ${amount:,.2f}"
    user_name = user.get('full_name', user.get('username', 'User'))
    plain_body = f"Dear {user_name},\n\nYour investment of ${amount:,.2f} in {plan_name} has STARTED!\n\nROI: {roi}%\nExpected Profit: ${expected_profit:,.2f}"
    content = f'<p>Dear {user_name},</p><div style="background:#d1fae5;padding:15px;"><p><strong>✅ INVESTMENT STARTED!</strong></p><p>Amount: ${amount:,.2f}<br>ROI: {roi}%</p></div>'
    html_body = get_email_template(subject, content, 'View Investments', f'{FRONTEND_URL}/investments.html')
    return send_email(user['email'], subject, plain_body, html_body)


def send_investment_completed_email(user, amount, plan_name, profit):
    subject = f"✅ Investment Completed - You earned ${profit:,.2f}!"
    user_name = user.get('full_name', user.get('username', 'User'))
    plain_body = f"Dear {user_name},\n\nYour investment has been COMPLETED!\n\nProfit Earned: ${profit:,.2f}\nTotal Return: ${amount + profit:,.2f}"
    content = f'<p>Dear {user_name},</p><div style="background:#d1fae5;padding:15px;"><p><strong>🎉 INVESTMENT COMPLETED!</strong></p><p>Profit: ${profit:,.2f}</p></div>'
    html_body = get_email_template(subject, content, 'View Dashboard', f'{FRONTEND_URL}/dashboard.html')
    return send_email(user['email'], subject, plain_body, html_body)


# ==================== INVESTMENT PLANS ====================
INVESTMENT_PLANS = {
    'standard': {
        'name': 'Standard Plan',
        'roi': 8,  # 8% profit
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

# ==================== AUTO-PROFIT SCHEDULER ====================

def process_investment_profits():
    if investments_collection is None:
        return
    try:
        logger.info("🔄 Processing investment profits...")
        cursor = investments_collection.find({'status': 'active', 'end_date': {'$lte': datetime.now(timezone.utc)}})
        processed = 0
        for inv in cursor:
            try:
                if users_collection is None:
                    continue
                user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
                if not user:
                    continue
                profit = inv.get('expected_profit', 0)
                if users_collection is not None:
                    users_collection.update_one({'_id': ObjectId(inv['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
                if investments_collection is not None:
                    investments_collection.update_one({'_id': inv['_id']}, {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}})
                if transactions_collection is not None:
                    transactions_collection.insert_one({
                        'user_id': inv['user_id'], 'type': 'profit', 'amount': profit, 'status': 'completed',
                        'description': f'Profit from {inv.get("plan_name", "Investment")}',
                        'created_at': datetime.now(timezone.utc)
                    })
                create_notification(inv['user_id'], 'Investment Completed! 🎉', f'You earned ${profit:,.2f} profit!', 'success')
                send_investment_completed_email(user, inv['amount'], inv.get('plan_name', 'Investment'), profit)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing investment: {e}")
        logger.info(f"✅ Processed {processed} investments")
    except Exception as e:
        logger.error(f"Error in profit processing: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(func=process_investment_profits, trigger="interval", hours=1, id="profit_processor", replace_existing=True)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())


# ==================== AUTHENTICATION ENDPOINTS ====================
@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == "OPTIONS":
        return add_cors_headers(make_response())
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
        existing = None
        if users_collection is not None:
            existing = users_collection.find_one({'$or': [{'email': email}, {'username': username}]})
        if not existing and veloxtrades_users is not None:
            existing = veloxtrades_users.find_one({'$or': [{'email': email}, {'username': username}]})
        if not existing and investment_users is not None:
            existing = investment_users.find_one({'$or': [{'email': email}, {'username': username}]})
        if existing:
            if existing.get('email') == email:
                return jsonify({'success': False, 'message': 'Email already registered'}), 400
            return jsonify({'success': False, 'message': 'Username already taken'}), 400
        referred_by = None
        referrer = None
        if referral_code_input:
            if users_collection is not None:
                referrer = users_collection.find_one({'referral_code': referral_code_input})
            if not referrer and veloxtrades_users is not None:
                referrer = veloxtrades_users.find_one({'referral_code': referral_code_input})
            if not referrer and investment_users is not None:
                referrer = investment_users.find_one({'referral_code': referral_code_input})
            if referrer:
                referred_by = referral_code_input
        own_referral_code = username.upper() + ''.join(random.choices(string.digits, k=4))
        wallet = {'balance': 0.00, 'total_deposited': 0.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00}
        user_data = {
            'full_name': full_name, 'email': email, 'username': username,
            'password': hash_password(password), 'phone': data.get('phone', ''), 'country': data.get('country', ''),
            'wallet': wallet, 'is_admin': False, 'is_verified': False, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': own_referral_code, 'referred_by': referred_by, 'referrals': [], 'kyc_status': 'pending'
        }
        user_id = None
        if veloxtrades_users is not None:
            result = veloxtrades_users.insert_one(user_data)
            user_id = result.inserted_id
        if investment_users is not None:
            investment_users.insert_one(user_data)
        if referrer:
            if veloxtrades_users is not None:
                veloxtrades_users.update_one({'_id': referrer['_id']}, {'$push': {'referrals': username}})
            if investment_users is not None:
                investment_users.update_one({'_id': referrer['_id']}, {'$push': {'referrals': username}})
            create_notification(referrer['_id'], 'New Referral! 🎉', f'{username} joined using your link!', 'success')
        create_notification(user_id, 'Welcome to Veloxtrades!', 'Start your investment journey today.', 'success')
        return add_cors_headers(jsonify({'success': True, 'message': 'Registration successful!'})), 201
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/verify-referral', methods=['POST', 'OPTIONS'])
def verify_referral():
    if request.method == "OPTIONS":
        return add_cors_headers(make_response())
    try:
        data = request.get_json()
        referral_code = data.get('referral_code', '').strip().upper()
        if not referral_code:
            return jsonify({'success': False, 'message': 'Referral code required'}), 400
        referrer = None
        if users_collection is not None:
            referrer = users_collection.find_one({'referral_code': referral_code})
        if not referrer and veloxtrades_users is not None:
            referrer = veloxtrades_users.find_one({'referral_code': referral_code})
        if not referrer and investment_users is not None:
            referrer = investment_users.find_one({'referral_code': referral_code})
        if referrer:
            return jsonify({'success': True, 'valid': True, 'message': 'Valid referral code!', 'referrer': referrer.get('username', 'User')})
        else:
            return jsonify({'success': True, 'valid': False, 'message': 'Invalid referral code'})
    except Exception as e:
        logger.error(f"Verify referral error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    response = make_response(jsonify({'success': True, 'message': 'Logged out'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    return add_cors_headers(response)


@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == "OPTIONS":
        response = make_response()
        return add_cors_headers(response)
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No credentials provided'}), 400
            
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')

        if not username_or_email or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400

        user = None
        
        # Search in combined collection
        if users_collection is not None:
            try:
                user = users_collection.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
                if user:
                    print(f"✅ User found in combined collection: {username_or_email}")
            except Exception as e:
                print(f"Error searching combined collection: {e}")
        
        # Search in veloxtrades_db
        if user is None and veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
                if user:
                    print(f"✅ User found in veloxtrades_db: {username_or_email}")
            except Exception as e:
                print(f"Error searching veloxtrades_db: {e}")
        
        # Search in investment_db
        if user is None and investment_users is not None:
            try:
                user = investment_users.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
                if user:
                    print(f"✅ User found in investment_db: {username_or_email}")
            except Exception as e:
                print(f"Error searching investment_db: {e}")
        
        if user is None:
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        # Verify password
        try:
            stored_password = user.get('password', '')
            if not stored_password:
                return jsonify({'success': False, 'message': 'Account error'}), 500
            
            password_valid = bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
            if not password_valid:
                return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        except Exception as e:
            print(f"Password verification error: {e}")
            return jsonify({'success': False, 'message': 'Authentication error'}), 500

        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account suspended'}), 403

        # Create token
        try:
            token = create_jwt_token(user['_id'], user.get('username', ''), user.get('is_admin', False))
        except Exception as e:
            print(f"Token creation error: {e}")
            return jsonify({'success': False, 'message': 'Session error'}), 500

        # Update last login
        try:
            if veloxtrades_users is not None:
                veloxtrades_users.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})
            if investment_users is not None:
                investment_users.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})
        except Exception as e:
            print(f"Last login update error (non-critical): {e}")

        wallet = user.get('wallet', {})
        if not isinstance(wallet, dict):
            wallet = {'balance': 0.00}
        
        user_data = {
            'id': str(user['_id']), 
            'username': user.get('username', ''), 
            'full_name': user.get('full_name', ''),
            'email': user.get('email', ''), 
            'balance': wallet.get('balance', 0.00),
            'is_admin': user.get('is_admin', False), 
            'kyc_status': user.get('kyc_status', 'pending')
        }

        response_data = {
            'success': True, 
            'message': 'Login successful!', 
            'data': {'token': token, 'user': user_data}
        }
        
        response = make_response(jsonify(response_data))
        
        response.set_cookie(
            'veloxtrades_token', 
            value=token, 
            httponly=True, 
            secure=True, 
            samesite='None',
            max_age=30 * 24 * 60 * 60, 
            path='/'
        )
        
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"❌ LOGIN ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': 'Login failed. Please try again.'}), 500


@app.route('/api/auth/profile', methods=['GET', 'OPTIONS'])
def get_profile():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    wallet = user.get('wallet', {})
    user_data = {
        'id': str(user['_id']), 'full_name': user.get('full_name', ''), 'username': user.get('username', ''),
        'email': user.get('email', ''), 'phone': user.get('phone', ''), 'country': user.get('country', ''),
        'wallet': wallet, 'is_admin': user.get('is_admin', False), 'kyc_status': user.get('kyc_status', 'pending'),
        'is_verified': user.get('is_verified', False), 'referral_code': user.get('referral_code', ''),
        'referrals': user.get('referrals', []), 'created_at': user.get('created_at').isoformat() if user.get('created_at') else None
    }
    return add_cors_headers(jsonify({'success': True, 'data': {'user': user_data}}))


@app.route('/api/verify-token', methods=['GET', 'OPTIONS'])
def verify_token():
    if request.method == "OPTIONS":
        return add_cors_headers(make_response())
    try:
        user = get_user_from_request()
        if not user:
            return jsonify({'success': False, 'message': 'Invalid or expired token'}), 401
        wallet = user.get('wallet', {})
        user_data = {
            'id': str(user['_id']), 'username': user.get('username', ''), 'email': user.get('email', ''),
            'full_name': user.get('full_name', ''), 'is_admin': user.get('is_admin', False),
            'kyc_status': user.get('kyc_status', 'pending'), 'balance': wallet.get('balance', 0.00)
        }
        return add_cors_headers(jsonify({'success': True, 'message': 'Token is valid', 'user': user_data}))
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return jsonify({'success': False, 'message': 'Token verification failed'}), 500


# ==================== DEPOSIT ENDPOINTS ====================
@app.route('/api/deposits', methods=['POST', 'OPTIONS'])
def create_deposit():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if deposits_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        crypto = data.get('crypto', 'usdt')
        transaction_hash = data.get('transaction_hash', '').strip()
        
        # Get settings
        settings = None
        if settings_collection is not None:
            settings = settings_collection.find_one({})
        min_deposit = settings.get('min_deposit', 10) if settings else 10
        max_deposit = settings.get('max_deposit', 100000) if settings else 100000
        
        if amount < min_deposit:
            return jsonify({'success': False, 'message': f'Minimum deposit is ${min_deposit}'}), 400
        if amount > max_deposit:
            return jsonify({'success': False, 'message': f'Maximum deposit is ${max_deposit}'}), 400
        
        deposit_id = 'DEP-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))
        deposit_data = {
            'deposit_id': deposit_id, 'user_id': str(user['_id']), 'username': user['username'],
            'amount': amount, 'crypto': crypto, 'transaction_hash': transaction_hash,
            'status': 'pending', 'created_at': datetime.now(timezone.utc)
        }
        deposits_collection.insert_one(deposit_data)
        
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']), 'type': 'deposit', 'amount': amount, 'status': 'pending',
                'description': f'Deposit of ${amount:,.2f} via {crypto.upper()}', 'deposit_id': deposit_id,
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user['_id'], 'Deposit Request Submitted', f'Deposit of ${amount:,.2f} pending approval.', 'info')
        return add_cors_headers(jsonify({'success': True, 'message': 'Deposit submitted', 'data': {'deposit_id': deposit_id}})), 201
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
            deposits = list(deposits_collection.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]))
        for d in deposits:
            d['_id'] = str(d['_id'])
            if d.get('created_at'):
                d['created_at'] = d['created_at'].isoformat()
        return add_cors_headers(jsonify({'success': True, 'data': {'deposits': deposits}}))
    except Exception as e:
        logger.error(f"Get deposits error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== WITHDRAWAL ENDPOINTS ====================
@app.route('/api/withdrawals', methods=['POST', 'OPTIONS'])
def create_withdrawal():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if withdrawals_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        currency = data.get('currency', 'usdt')
        wallet_address = data.get('wallet_address', '').strip()
        
        if not wallet_address:
            return jsonify({'success': False, 'message': 'Wallet address required'}), 400
        
        settings = None
        if settings_collection is not None:
            settings = settings_collection.find_one({})
        min_withdrawal = settings.get('min_withdrawal', 50) if settings else 50
        max_withdrawal = settings.get('max_withdrawal', 50000) if settings else 50000
        withdrawal_fee = settings.get('withdrawal_fee', 0) if settings else 0
        
        if amount < min_withdrawal:
            return jsonify({'success': False, 'message': f'Minimum withdrawal is ${min_withdrawal}'}), 400
        if amount > max_withdrawal:
            return jsonify({'success': False, 'message': f'Maximum withdrawal is ${max_withdrawal}'}), 400
        
        fee_amount = amount * (withdrawal_fee / 100)
        net_amount = amount - fee_amount
        
        wallet_balance = user.get('wallet', {}).get('balance', 0)
        if wallet_balance < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        withdrawal_id = 'WIT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))
        withdrawal_data = {
            'withdrawal_id': withdrawal_id, 'user_id': str(user['_id']), 'username': user['username'],
            'amount': amount, 'fee': fee_amount, 'net_amount': net_amount, 'currency': currency,
            'wallet_address': wallet_address, 'status': 'pending', 'created_at': datetime.now(timezone.utc)
        }
        withdrawals_collection.insert_one(withdrawal_data)
        
        # Deduct from user balance
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount}})
        if investment_users is not None:
            investment_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount}})
        
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']), 'type': 'withdrawal', 'amount': amount, 'status': 'pending',
                'description': f'Withdrawal of ${amount:,.2f} to {currency.upper()}', 'withdrawal_id': withdrawal_id,
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user['_id'], 'Withdrawal Request Submitted', f'Withdrawal of ${amount:,.2f} pending approval.', 'info')
        return add_cors_headers(jsonify({'success': True, 'message': 'Withdrawal submitted', 'data': {'withdrawal_id': withdrawal_id}})), 201
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
           withdrawals = list(withdrawals_collection.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]))
        for w in withdrawals:
            w['_id'] = str(w['_id'])
            if w.get('created_at'):
                w['created_at'] = w['created_at'].isoformat()
        return add_cors_headers(jsonify({'success': True, 'data': {'withdrawals': withdrawals}}))
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== INVESTMENT ENDPOINTS ====================
@app.route('/api/invest', methods=['POST', 'OPTIONS'])
def create_investment():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if investments_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        plan_type = data.get('plan') or data.get('plan_type')
        amount = float(data.get('amount', 0))
        plan = INVESTMENT_PLANS.get(plan_type)
        
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid plan'}), 400
        
        # Check amount limits
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum investment for {plan["name"]} is ${plan["min_deposit"]}'}), 400
        if amount > plan['max_deposit']:
            return jsonify({'success': False, 'message': f'Maximum investment for {plan["name"]} is ${plan["max_deposit"]}'}), 400
        
        # Check balance
        wallet_balance = user.get('wallet', {}).get('balance', 0)
        if wallet_balance < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        
        # Calculate expected profit
        expected_profit = amount * plan['roi'] / 100
        end_date = datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])
        
        # ========== DEDUCT BALANCE IMMEDIATELY ==========
        if veloxtrades_users is not None:
            veloxtrades_users.update_one(
                {'_id': user['_id']}, 
                {'$inc': {'wallet.balance': -amount}}
            )
        if investment_users is not None:
            investment_users.update_one(
                {'_id': user['_id']}, 
                {'$inc': {'wallet.balance': -amount}}
            )
        
        # Create investment request (PENDING status)
        investment_data = {
            'investment_id': 'INV-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12)),
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
            'status': 'pending',  # PENDING - waiting for admin approval
            'created_at': datetime.now(timezone.utc)
        }
        
        result = investments_collection.insert_one(investment_data)
        
        # Create transaction record
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user['_id']),
                'type': 'investment_request',
                'amount': amount,
                'status': 'pending',
                'description': f'Investment request for {plan["name"]} - ${amount:,.2f} (Pending Approval)',
                'investment_id': str(result.inserted_id),
                'created_at': datetime.now(timezone.utc)
            })
        
        # Notify user
        create_notification(
            user['_id'],
            'Investment Request Submitted 📝',
            f'Your investment request of ${amount:,.2f} in {plan["name"]} has been submitted. Expected profit: ${expected_profit:,.2f}',
            'info'
        )
        
        return add_cors_headers(jsonify({
            'success': True,
            'message': f'Investment request submitted! Awaiting admin approval.',
            'data': {
                'investment_id': str(result.inserted_id),
                'amount': amount,
                'plan': plan['name'],
                'expected_profit': expected_profit,
                'status': 'pending'
            }
        }))
        
    except Exception as e:
        logger.error(f"Investment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

def process_investment_profits():
    """Auto-process completed investments and add profit to user balance"""
    if investments_collection is None:
        return
    
    try:
        logger.info("🔄 Processing investment profits...")
        
        # Find all active investments that have ended
        cursor = investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        })
        
        processed = 0
        for inv in cursor:
            try:
                user_id = inv['user_id']
                profit = inv.get('expected_profit', 0)
                amount = inv.get('amount', 0)
                
                # ========== ADD PROFIT TO USER BALANCE ==========
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {
                            'wallet.balance': profit,
                            'wallet.total_profit': profit
                        }}
                    )
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {
                            'wallet.balance': profit,
                            'wallet.total_profit': profit
                        }}
                    )
                
                # ========== MARK INVESTMENT AS COMPLETED ==========
                investments_collection.update_one(
                    {'_id': inv['_id']},
                    {'$set': {
                        'status': 'completed',
                        'completed_at': datetime.now(timezone.utc)
                    }}
                )
                
                # ========== CREATE PROFIT TRANSACTION ==========
                if transactions_collection is not None:
                    transactions_collection.insert_one({
                        'user_id': user_id,
                        'type': 'profit',
                        'amount': profit,
                        'status': 'completed',
                        'description': f'Profit from {inv.get("plan_name", "Investment")} - ${profit:,.2f}',
                        'investment_id': str(inv['_id']),
                        'created_at': datetime.now(timezone.utc)
                    })
                
                # ========== NOTIFY USER ==========
                create_notification(
                    user_id,
                    'Investment Completed! 🎉',
                    f'Your investment of ${amount:,.2f} in {inv.get("plan_name", "Investment")} has completed! You earned ${profit:,.2f} profit!',
                    'success'
                )
                
                # ========== GET USER FOR EMAIL ==========
                user = None
                if veloxtrades_users is not None:
                    user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if user is None and investment_users is not None:
                    user = investment_users.find_one({'_id': ObjectId(user_id)})
                
                # ========== SEND COMPLETION EMAIL ==========
                if user:
                    send_investment_completed_email(user, amount, inv.get('plan_name', 'Investment'), profit)
                
                processed += 1
                logger.info(f"✅ Processed investment profit for {user.get('username')}: +${profit}")
                
            except Exception as e:
                logger.error(f"Error processing investment {inv.get('_id')}: {e}")
        
        logger.info(f"✅ Processed {processed} completed investments")
        
    except Exception as e:
        logger.error(f"Error in profit processing: {e}")
# ==================== TRANSACTION ENDPOINTS ====================
@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        transactions = []
        
        # Try veloxtrades_transactions
        if veloxtrades_transactions is not None:
            try:
                veloxtrades_tx = list(veloxtrades_transactions.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]))
                transactions.extend(veloxtrades_tx)
                print(f"Found {len(veloxtrades_tx)} transactions in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_transactions: {e}")
        
        # Try investment_transactions
        if investment_transactions is not None:
            try:
                investment_tx = list(investment_transactions.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]))
                # Avoid duplicates
                existing_ids = {str(tx.get('_id')) for tx in transactions}
                for tx in investment_tx:
                    if str(tx.get('_id')) not in existing_ids:
                        transactions.append(tx)
                print(f"Found {len(investment_tx)} transactions in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_transactions: {e}")
        
        # Format transactions
        formatted_transactions = []
        for tx in transactions:
            try:
                tx_copy = dict(tx)
                tx_copy['_id'] = str(tx_copy['_id'])
                if tx_copy.get('created_at'):
                    tx_copy['created_at'] = tx_copy['created_at'].isoformat()
                formatted_transactions.append(tx_copy)
            except Exception as e:
                print(f"Error formatting transaction: {e}")
                continue
        
        response = jsonify({'success': True, 'data': {'transactions': formatted_transactions}})
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    except Exception as e:
        print(f"Transactions error: {e}")
        response = jsonify({'success': True, 'data': {'transactions': []}})
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response

# ==================== DASHBOARD ENDPOINTS ====================
@app.route('/api/user/dashboard', methods=['GET', 'OPTIONS'])
def user_dashboard():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        print(f"🔵 Loading dashboard for user: {user.get('username')} (ID: {user.get('_id')})")
        
        # Get wallet - check both database structures
        wallet = user.get('wallet', {})
        if not isinstance(wallet, dict):
            wallet = {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0}
        
        print(f"💰 User balance from user object: ${wallet.get('balance', 0)}")
        
        # ========== GET ACTIVE INVESTMENTS FROM BOTH DATABASES ==========
        active_investments = []
        
        # Search in veloxtrades_investments
        if veloxtrades_investments is not None:
            try:
                veloxtrades_inv = list(veloxtrades_investments.find({
                    'user_id': str(user['_id']), 
                    'status': 'active'
                }))
                active_investments.extend(veloxtrades_inv)
                print(f"📊 Found {len(veloxtrades_inv)} active investments in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_investments: {e}")
        
        # Search in investment_investments
        if investment_investments is not None:
            try:
                investment_inv = list(investment_investments.find({
                    'user_id': str(user['_id']), 
                    'status': 'active'
                }))
                # Avoid duplicates
                existing_ids = {str(inv.get('_id')) for inv in active_investments}
                for inv in investment_inv:
                    if str(inv.get('_id')) not in existing_ids:
                        active_investments.append(inv)
                print(f"📊 Found {len(investment_inv)} active investments in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_investments: {e}")
        
        # Calculate totals
        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)
        
        print(f"💰 Total active investments: ${total_active}")
        print(f"💰 Pending profit: ${pending_profit}")
        
        # ========== GET RECENT TRANSACTIONS FROM BOTH DATABASES ==========
        all_transactions = []
        
        # Search in veloxtrades_transactions
        if veloxtrades_transactions is not None:
            try:
                veloxtrades_tx = list(veloxtrades_transactions.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]).limit(10))
                all_transactions.extend(veloxtrades_tx)
                print(f"📝 Found {len(veloxtrades_tx)} transactions in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_transactions: {e}")
        
        # Search in investment_transactions
        if investment_transactions is not None:
            try:
                investment_tx = list(investment_transactions.find({'user_id': str(user['_id'])}).sort([('created_at', -1)]).limit(10))
                # Avoid duplicates
                existing_ids = {str(tx.get('_id')) for tx in all_transactions}
                for tx in investment_tx:
                    if str(tx.get('_id')) not in existing_ids:
                        all_transactions.append(tx)
                print(f"📝 Found {len(investment_tx)} transactions in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_transactions: {e}")
        
        # Sort by date and take top 10
        all_transactions.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
        recent_transactions = all_transactions[:10]
        
        # Format transactions
        formatted_transactions = []
        for tx in recent_transactions:
            try:
                formatted_transactions.append({
                    '_id': str(tx['_id']),
                    'type': tx.get('type', 'unknown'),
                    'amount': tx.get('amount', 0),
                    'status': tx.get('status', 'pending'),
                    'description': tx.get('description', ''),
                    'created_at': tx.get('created_at').isoformat() if tx.get('created_at') else None
                })
            except Exception as e:
                print(f"Error formatting transaction: {e}")
                continue
        
        # ========== GET NOTIFICATION COUNT ==========
        unread_count = 0
        if veloxtrades_notifications is not None:
            try:
                unread_count += veloxtrades_notifications.count_documents({'user_id': str(user['_id']), 'read': False})
            except Exception as e:
                print(f"Error counting veloxtrades notifications: {e}")
        
        if investment_notifications is not None:
            try:
                unread_count += investment_notifications.count_documents({'user_id': str(user['_id']), 'read': False})
            except Exception as e:
                print(f"Error counting investment notifications: {e}")
        
        # ========== GET PENDING REQUESTS ==========
        pending_deposits = 0
        if veloxtrades_deposits is not None:
            try:
                pending_deposits += veloxtrades_deposits.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
            except Exception as e:
                print(f"Error counting veloxtrades deposits: {e}")
        
        if investment_deposits is not None:
            try:
                pending_deposits += investment_deposits.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
            except Exception as e:
                print(f"Error counting investment deposits: {e}")
        
        pending_withdrawals = 0
        if veloxtrades_withdrawals is not None:
            try:
                pending_withdrawals += veloxtrades_withdrawals.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
            except Exception as e:
                print(f"Error counting veloxtrades withdrawals: {e}")
        
        if investment_withdrawals is not None:
            try:
                pending_withdrawals += investment_withdrawals.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
            except Exception as e:
                print(f"Error counting investment withdrawals: {e}")
        
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
        
        print(f"✅ Dashboard data prepared successfully")
        print(f"   Balance: ${dashboard_data['wallet']['balance']}")
        print(f"   Active investments: ${dashboard_data['investments']['total_active']}")
        print(f"   Transactions: {len(formatted_transactions)}")
        
        response = jsonify({'success': True, 'data': dashboard_data})
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
        
    except Exception as e:
        print(f"🔥 Dashboard error: {e}")
        import traceback
        traceback.print_exc()
        
        error_response = jsonify({'success': False, 'message': str(e)})
        error_response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        error_response.headers['Access-Control-Allow-Credentials'] = 'true'
        return error_response, 500
@app.route('/api/user/referral-info', methods=['GET', 'OPTIONS'])
def get_user_referral_info():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        referral_code = user.get('referral_code', '')
        referred_users = []
        if users_collection is not None:
            referred_users = list(users_collection.find({'referred_by': referral_code}, {'username': 1, 'full_name': 1, 'created_at': 1, 'wallet.total_deposited': 1}))
        formatted_referrals = []
        total_commission = 0
        for ref in referred_users:
            wallet = ref.get('wallet', {})
            total_deposited = wallet.get('total_deposited', 0) if isinstance(wallet, dict) else 0
            commission = total_deposited * 0.05
            total_commission += commission
            formatted_referrals.append({
                'id': str(ref['_id']), 'username': ref.get('username', ''), 'full_name': ref.get('full_name', ''),
                'joined': ref.get('created_at').isoformat() if ref.get('created_at') else None,
                'total_deposited': total_deposited, 'commission_earned': commission
            })
        settings = None
        if settings_collection is not None:
            settings = settings_collection.find_one({})
        bonus_percentage = settings.get('referral_bonus', 5) if settings else 5
        return add_cors_headers(jsonify({'success': True, 'data': {
            'referral_code': referral_code, 'referral_link': f"{FRONTEND_URL}/register?ref={referral_code}",
            'referral_bonus_percentage': bonus_percentage, 'total_referrals': len(formatted_referrals),
            'total_commission': total_commission, 'referred_users': formatted_referrals
        }}))
    except Exception as e:
        logger.error(f"Get referral info error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {
            'referral_code': user.get('referral_code', 'N/A'), 'referral_link': f"{FRONTEND_URL}/register?ref={user.get('referral_code', '')}",
            'referral_bonus_percentage': 5, 'total_referrals': 0, 'total_commission': 0, 'referred_users': []
        }})), 200


# ==================== NOTIFICATION ENDPOINTS ====================
@app.route('/api/notifications', methods=['GET', 'OPTIONS'])
def get_notifications():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        notifications = []
        
        # Search in veloxtrades_notifications
        if veloxtrades_notifications is not None:
            try:
                veloxtrades_notif = list(veloxtrades_notifications.find(
                    {'user_id': str(user['_id'])}
                ).sort([('created_at', -1)]).skip(skip).limit(limit))
                notifications.extend(veloxtrades_notif)
                print(f"📬 Found {len(veloxtrades_notif)} notifications in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_notifications: {e}")
        
        # Search in investment_notifications
        if investment_notifications is not None:
            try:
                investment_notif = list(investment_notifications.find(
                    {'user_id': str(user['_id'])}
                ).sort([('created_at', -1)]).skip(skip).limit(limit))
                # Avoid duplicates
                existing_ids = {str(n.get('_id')) for n in notifications}
                for n in investment_notif:
                    if str(n.get('_id')) not in existing_ids:
                        notifications.append(n)
                print(f"📬 Found {len(investment_notif)} notifications in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_notifications: {e}")
        
        # Sort by date
        notifications.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        # Format notifications
        formatted_notifications = []
        for n in notifications:
            try:
                n_copy = {
                    '_id': str(n['_id']),
                    'user_id': str(n.get('user_id', '')),
                    'title': n.get('title', ''),
                    'message': n.get('message', ''),
                    'type': n.get('type', 'info'),
                    'read': n.get('read', False),
                    'created_at': n.get('created_at').isoformat() if n.get('created_at') else None
                }
                formatted_notifications.append(n_copy)
            except Exception as e:
                print(f"Error formatting notification: {e}")
                continue
        
        # Count total and unread
        total = 0
        unread = 0
        
        if veloxtrades_notifications is not None:
            try:
                total += veloxtrades_notifications.count_documents({'user_id': str(user['_id'])})
                unread += veloxtrades_notifications.count_documents({'user_id': str(user['_id']), 'read': False})
            except Exception as e:
                print(f"Error counting veloxtrades notifications: {e}")
        
        if investment_notifications is not None:
            try:
                total += investment_notifications.count_documents({'user_id': str(user['_id'])})
                unread += investment_notifications.count_documents({'user_id': str(user['_id']), 'read': False})
            except Exception as e:
                print(f"Error counting investment notifications: {e}")
        
        pages = (total + limit - 1) // limit if total > 0 else 1
        
        print(f"✅ Returning {len(formatted_notifications)} notifications (total: {total}, unread: {unread})")
        
        response = jsonify({
            'success': True,
            'data': {
                'notifications': formatted_notifications,
                'total': total,
                'unread': unread,
                'page': page,
                'pages': pages
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"🔥 Get notifications error: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': True,
            'data': {
                'notifications': [],
                'total': 0,
                'unread': 0,
                'page': 1,
                'pages': 1
            }
        })
        return add_cors_headers(response)
@app.route('/api/notifications/<notification_id>/read', methods=['PUT', 'OPTIONS'])
def mark_notification_read(notification_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        if notifications_collection is not None:
            notifications_collection.update_one({'_id': ObjectId(notification_id), 'user_id': str(user['_id'])}, {'$set': {'read': True}})
        return add_cors_headers(jsonify({'success': True, 'message': 'Marked as read'}))
    except Exception as e:
        logger.error(f"Mark read error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== KYC ENDPOINTS ====================
@app.route('/api/kyc/submit', methods=['POST', 'OPTIONS'])
def submit_kyc():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    if kyc_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        full_name = data.get('full_name', '').strip()
        date_of_birth = data.get('date_of_birth', '')
        country = data.get('country', '')
        id_type = data.get('id_type', '')
        id_number = data.get('id_number', '')
        id_front_url = data.get('id_front_url', '')
        
        if not all([full_name, date_of_birth, country, id_type, id_number, id_front_url]):
            return jsonify({'success': False, 'message': 'All KYC fields required'}), 400
        
        existing = None
        if kyc_collection is not None:
            existing = kyc_collection.find_one({'user_id': str(user['_id'])})
        if existing:
            if existing.get('status') == 'pending':
                return jsonify({'success': False, 'message': 'KYC already pending'}), 400
            if existing.get('status') == 'approved':
                return jsonify({'success': False, 'message': 'KYC already verified'}), 400
        
        kyc_data = {
            'user_id': str(user['_id']), 'username': user['username'], 'email': user['email'],
            'full_name': full_name, 'date_of_birth': date_of_birth, 'country': country,
            'id_type': id_type, 'id_number': id_number, 'id_front_url': id_front_url,
            'id_back_url': data.get('id_back_url', ''), 'selfie_url': data.get('selfie_url', ''),
            'address': data.get('address', ''), 'status': 'pending', 'submitted_at': datetime.now(timezone.utc)
        }
        kyc_collection.insert_one(kyc_data)
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$set': {'kyc_status': 'pending'}})
        if investment_users is not None:
            investment_users.update_one({'_id': user['_id']}, {'$set': {'kyc_status': 'pending'}})
        
        create_notification(user['_id'], 'KYC Application Submitted', 'Your KYC application is pending review.', 'info')
        return add_cors_headers(jsonify({'success': True, 'message': 'KYC submitted successfully'})), 201
    except Exception as e:
        logger.error(f"KYC submit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kyc/status', methods=['GET', 'OPTIONS'])
def get_kyc_status():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        kyc = None
        if kyc_collection is not None:
            kyc = kyc_collection.find_one({'user_id': str(user['_id'])})
        if not kyc:
            return add_cors_headers(jsonify({'success': True, 'data': {'status': 'not_submitted'}}))
        return add_cors_headers(jsonify({'success': True, 'data': {
            'status': kyc.get('status'), 'full_name': kyc.get('full_name'),
            'submitted_at': kyc.get('submitted_at').isoformat() if kyc.get('submitted_at') else None,
            'rejection_reason': kyc.get('rejection_reason')
        }}))
    except Exception as e:
        logger.error(f"Get KYC status error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/kyc', methods=['GET', 'OPTIONS'])
def get_kyc_details():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        kyc = None
        if kyc_collection is not None:
            kyc = kyc_collection.find_one({'user_id': str(user['_id'])})
        if not kyc:
            return add_cors_headers(jsonify({'success': True, 'data': None}))
        kyc['_id'] = str(kyc['_id'])
        if kyc.get('submitted_at'):
            kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        return add_cors_headers(jsonify({'success': True, 'data': kyc}))
    except Exception as e:
        logger.error(f"Get KYC details error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== SUPPORT TICKET ENDPOINTS ====================
@app.route('/api/support/tickets', methods=['POST', 'OPTIONS'])
def create_ticket():
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
        priority = data.get('priority', 'medium')
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message required'}), 400
        
        ticket_id = 'TKT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=10))
        ticket_data = {
            'ticket_id': ticket_id,
            'user_id': str(user['_id']),
            'username': user.get('username', ''),
            'email': user.get('email', ''),
            'subject': subject,
            'message': message,
            'category': category,
            'priority': priority,
            'status': 'open',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc),
            'messages': [{
                'sender': 'user',
                'sender_name': user.get('username', 'User'),
                'message': message,
                'created_at': datetime.now(timezone.utc)
            }]
        }
        
        support_tickets_collection.insert_one(ticket_data)
        
        # Create notification for user
        create_notification(
            user['_id'],
            f'Ticket Created: {ticket_id}',
            f'Your ticket "{subject}" has been created. We\'ll respond within 24 hours.',
            'info'
        )
        
        return add_cors_headers(jsonify({
            'success': True,
            'message': 'Ticket created successfully',
            'data': {'ticket_id': ticket_id}
        })), 201
        
    except Exception as e:
        logger.error(f"Create ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
@app.route('/api/investments', methods=['GET', 'OPTIONS'])
def get_user_investments():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        investments = []
        
        # Search in veloxtrades_investments
        if veloxtrades_investments is not None:
            try:
                veloxtrades_inv = list(veloxtrades_investments.find(
                    {'user_id': str(user['_id'])}
                ).sort([('start_date', -1)]))
                investments.extend(veloxtrades_inv)
                print(f"📊 Found {len(veloxtrades_inv)} investments in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_investments: {e}")
        
        # Search in investment_investments
        if investment_investments is not None:
            try:
                investment_inv = list(investment_investments.find(
                    {'user_id': str(user['_id'])}
                ).sort([('start_date', -1)]))
                # Avoid duplicates
                existing_ids = {str(inv.get('_id')) for inv in investments}
                for inv in investment_inv:
                    if str(inv.get('_id')) not in existing_ids:
                        investments.append(inv)
                print(f"📊 Found {len(investment_inv)} investments in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_investments: {e}")
        
        # Format investments
        formatted_investments = []
        for inv in investments:
            try:
                inv_copy = {
                    '_id': str(inv['_id']),
                    'user_id': str(inv.get('user_id', '')),
                    'username': inv.get('username', ''),
                    'plan': inv.get('plan', ''),
                    'plan_name': inv.get('plan_name', 'Investment'),
                    'amount': inv.get('amount', 0),
                    'roi': inv.get('roi', 0),
                    'expected_profit': inv.get('expected_profit', 0),
                    'duration_hours': inv.get('duration_hours', 0),
                    'status': inv.get('status', 'pending'),
                    'start_date': inv.get('start_date').isoformat() if inv.get('start_date') else None,
                    'end_date': inv.get('end_date').isoformat() if inv.get('end_date') else None,
                    'created_at': inv.get('created_at').isoformat() if inv.get('created_at') else None,
                    'approved_at': inv.get('approved_at').isoformat() if inv.get('approved_at') else None
                }
                formatted_investments.append(inv_copy)
            except Exception as e:
                print(f"Error formatting investment: {e}")
                continue
        
        print(f"✅ Returning {len(formatted_investments)} investments for user {user.get('username')}")
        
        response = jsonify({'success': True, 'data': {'investments': formatted_investments}})
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"🔥 Get investments error: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({'success': True, 'data': {'investments': []}})
        return add_cors_headers(response) 
@app.route('/api/support/tickets/<ticket_id>', methods=['GET', 'OPTIONS'])
def get_ticket(ticket_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        if support_tickets_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id, 'user_id': str(user['_id'])})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        # Format ticket
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

@app.route('/api/support/tickets', methods=['GET', 'OPTIONS'])
def get_tickets():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        skip = (page - 1) * limit
        
        tickets = []
        
        # Search in veloxtrades_support_tickets
        if veloxtrades_support_tickets is not None:
            try:
                veloxtrades_tickets = list(veloxtrades_support_tickets.find(
                    {'user_id': str(user['_id'])}
                ).sort([('created_at', -1)]).skip(skip).limit(limit))
                tickets.extend(veloxtrades_tickets)
                print(f"🎫 Found {len(veloxtrades_tickets)} tickets in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_support_tickets: {e}")
        
        # Search in investment_support_tickets
        if investment_support_tickets is not None:
            try:
                investment_tickets = list(investment_support_tickets.find(
                    {'user_id': str(user['_id'])}
                ).sort([('created_at', -1)]).skip(skip).limit(limit))
                # Avoid duplicates
                existing_ids = {str(t.get('_id')) for t in tickets}
                for t in investment_tickets:
                    if str(t.get('_id')) not in existing_ids:
                        tickets.append(t)
                print(f"🎫 Found {len(investment_tickets)} tickets in investment_db")
            except Exception as e:
                print(f"Error fetching from investment_support_tickets: {e}")
        
        # Sort by date
        tickets.sort(key=lambda x: x.get('created_at', datetime.min), reverse=True)
        
        # Format tickets
        formatted_tickets = []
        for t in tickets:
            try:
                t_copy = {
                    '_id': str(t['_id']),
                    'ticket_id': t.get('ticket_id', ''),
                    'user_id': str(t.get('user_id', '')),
                    'username': t.get('username', ''),
                    'subject': t.get('subject', ''),
                    'category': t.get('category', 'general'),
                    'priority': t.get('priority', 'medium'),
                    'status': t.get('status', 'open'),
                    'message_count': len(t.get('messages', [])),
                    'created_at': t.get('created_at').isoformat() if t.get('created_at') else None,
                    'updated_at': t.get('updated_at').isoformat() if t.get('updated_at') else None
                }
                formatted_tickets.append(t_copy)
            except Exception as e:
                print(f"Error formatting ticket: {e}")
                continue
        
        # Count total
        total = 0
        if veloxtrades_support_tickets is not None:
            try:
                total += veloxtrades_support_tickets.count_documents({'user_id': str(user['_id'])})
            except Exception as e:
                print(f"Error counting veloxtrades tickets: {e}")
        
        if investment_support_tickets is not None:
            try:
                total += investment_support_tickets.count_documents({'user_id': str(user['_id'])})
            except Exception as e:
                print(f"Error counting investment tickets: {e}")
        
        pages = (total + limit - 1) // limit if total > 0 else 1
        
        print(f"✅ Returning {len(formatted_tickets)} tickets (total: {total})")
        
        response = jsonify({
            'success': True,
            'data': {
                'tickets': formatted_tickets,
                'total': total,
                'page': page,
                'pages': pages
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"🔥 Get tickets error: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({
            'success': True,
            'data': {
                'tickets': [],
                'total': 0,
                'page': 1,
                'pages': 1
            }
        })
        return add_cors_headers(response)

@app.route('/api/support/tickets/<ticket_id>/close', methods=['POST', 'OPTIONS'])
def close_ticket(ticket_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        if support_tickets_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id, 'user_id': str(user['_id'])})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
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
        
        create_notification(
            user['_id'],
            f'Ticket Closed: {ticket_id}',
            f'Your ticket "{ticket.get("subject")}" has been closed.',
            'info'
        )
        
        return add_cors_headers(jsonify({'success': True, 'message': 'Ticket closed successfully'}))
        
    except Exception as e:
        logger.error(f"Close ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - STATISTICS ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    try:
        total_users = 0
        banned_users = 0
        
        # Try to get users from veloxtrades_db first (primary)
        if veloxtrades_users is not None:
            try:
                total_users = veloxtrades_users.count_documents({})
                banned_users = veloxtrades_users.count_documents({'is_banned': True})
                logger.info(f"Stats from veloxtrades_users: {total_users} users, {banned_users} banned")
            except Exception as e:
                logger.error(f"Error counting from veloxtrades_users: {e}")
        
        # If no users found, try investment_db
        if total_users == 0 and investment_users is not None:
            try:
                total_users = investment_users.count_documents({})
                banned_users = investment_users.count_documents({'is_banned': True})
                logger.info(f"Stats from investment_users: {total_users} users, {banned_users} banned")
            except Exception as e:
                logger.error(f"Error counting from investment_users: {e}")
        
        # If still no users, try combined collection
        if total_users == 0 and users_collection is not None:
            try:
                total_users = users_collection.count_documents({})
                banned_users = users_collection.count_documents({'is_banned': True})
                logger.info(f"Stats from combined collection: {total_users} users, {banned_users} banned")
            except Exception as e:
                logger.error(f"Error counting from combined collection: {e}")
        
        total_deposit_amount = 0
        pending_deposits = 0
        
        # Try to get deposit stats from deposits_collection
        if deposits_collection is not None:
            try:
                approved_deposits = list(deposits_collection.find({'status': 'approved'}))
                total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
                pending_deposits = deposits_collection.count_documents({'status': 'pending'})
                logger.info(f"Deposit stats: approved amount=${total_deposit_amount}, pending={pending_deposits}")
            except Exception as e:
                logger.error(f"Error getting deposit stats: {e}")
        
        total_withdrawal_amount = 0
        pending_withdrawals = 0
        
        # Try to get withdrawal stats from withdrawals_collection
        if withdrawals_collection is not None:
            try:
                approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
                total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
                pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
                logger.info(f"Withdrawal stats: approved amount=${total_withdrawal_amount}, pending={pending_withdrawals}")
            except Exception as e:
                logger.error(f"Error getting withdrawal stats: {e}")
        
        active_investments = 0
        
        # Try to get investment stats from investments_collection
        if investments_collection is not None:
            try:
                active_investments = investments_collection.count_documents({'status': 'active'})
                logger.info(f"Active investments: {active_investments}")
            except Exception as e:
                logger.error(f"Error getting investment stats: {e}")
        
        return add_cors_headers(jsonify({'success': True, 'data': {
            'total_users': total_users,
            'total_deposit_amount': total_deposit_amount,
            'total_withdrawal_amount': total_withdrawal_amount,
            'active_investments': active_investments,
            'pending_deposits': pending_deposits,
            'pending_withdrawals': pending_withdrawals,
            'banned_users': banned_users
        }}))
        
    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        return add_cors_headers(jsonify({'success': True, 'data': {
            'total_users': 0, 
            'total_deposit_amount': 0, 
            'total_withdrawal_amount': 0,
            'active_investments': 0, 
            'pending_deposits': 0, 
            'pending_withdrawals': 0, 
            'banned_users': 0
        }})), 200

# ==================== ADMIN - USERS ====================
@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    """Get users with pagination - supports up to 100 per page"""
    
    try:
        # Get pagination parameters with safe defaults
        try:
            page = int(request.args.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
            
        try:
            limit = int(request.args.get('limit', 60))
            if limit < 1:
                limit = 60
            elif limit > 100:
                limit = 100
        except (ValueError, TypeError):
            limit = 60
            
        search = request.args.get('search', '').strip()
        skip = (page - 1) * limit
        
        logger.info(f"Admin fetching users - page: {page}, limit: {limit}, search: '{search}'")
        
        # Build query
        query = {}
        if search:
            try:
                escaped_search = re.escape(search)
                query['$or'] = [
                    {'username': {'$regex': escaped_search, '$options': 'i'}},
                    {'email': {'$regex': escaped_search, '$options': 'i'}},
                    {'full_name': {'$regex': escaped_search, '$options': 'i'}}
                ]
            except Exception as regex_error:
                logger.error(f"Regex error in search: {regex_error}")
                query = {
                    '$or': [
                        {'username': {'$eq': search}},
                        {'email': {'$eq': search}}
                    ]
                }
        
        # CRITICAL FIX: Try veloxtrades_users directly first
        users = []
        total = 0
        
        # Try veloxtrades_users (primary database)
        if veloxtrades_users is not None:
            try:
                total = veloxtrades_users.count_documents(query)
                cursor = veloxtrades_users.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                users = list(cursor)
                logger.info(f"Fetched {len(users)} users from veloxtrades_users, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from veloxtrades_users: {e}", exc_info=True)
        
        # If no users found, try investment_users
        if len(users) == 0 and investment_users is not None:
            try:
                total = investment_users.count_documents(query)
                cursor = investment_users.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                users = list(cursor)
                logger.info(f"Fetched {len(users)} users from investment_users, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from investment_users: {e}", exc_info=True)
        
        # If still no users, try combined collection as last resort
        if len(users) == 0 and users_collection is not None:
            try:
                total = users_collection.count_documents(query)
                cursor = users_collection.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                users = list(cursor)
                logger.info(f"Fetched {len(users)} users from combined collection, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from combined collection: {e}", exc_info=True)
        
        # If still no users and total is 0, try to get a raw count to debug
        if len(users) == 0 and total == 0:
            # Emergency debug - get raw count from veloxtrades_users
            if veloxtrades_users is not None:
                try:
                    raw_total = veloxtrades_users.count_documents({})
                    logger.warning(f"Emergency check - raw total in veloxtrades_users: {raw_total}")
                    if raw_total > 0:
                        # Force fetch without query
                        cursor = veloxtrades_users.find({}).sort([('created_at', -1)]).skip(skip).limit(limit)
                        users = list(cursor)
                        total = raw_total
                        logger.info(f"Emergency fetch: got {len(users)} users")
                except Exception as e:
                    logger.error(f"Emergency fetch failed: {e}")
        
        # Format users safely
        formatted_users = []
        for idx, user in enumerate(users):
            try:
                if not isinstance(user, dict):
                    logger.warning(f"User at index {idx} is not a dict: {type(user)}")
                    continue
                
                wallet = user.get('wallet', {}) or {}
                if not isinstance(wallet, dict):
                    wallet = {}
                
                wallet_data = {
                    'balance': float(wallet.get('balance', 0) or 0),
                    'total_deposited': float(wallet.get('total_deposited', 0) or 0),
                    'total_profit': float(wallet.get('total_profit', 0) or 0),
                    'total_withdrawn': float(wallet.get('total_withdrawn', 0) or 0),
                    'total_invested': float(wallet.get('total_invested', 0) or 0)
                }
                
                def format_date(date_field):
                    if not date_field:
                        return None
                    try:
                        if isinstance(date_field, datetime):
                            return date_field.isoformat()
                        elif isinstance(date_field, str):
                            return date_field
                        else:
                            return str(date_field)
                    except:
                        return None
                
                created_at = format_date(user.get('created_at'))
                last_login = format_date(user.get('last_login'))
                
                def safe_str(value, default=''):
                    if value is None:
                        return default
                    try:
                        return str(value)
                    except:
                        return default
                
                user_data = {
                    '_id': str(user.get('_id')) if user.get('_id') else f'unknown_{idx}',
                    'username': safe_str(user.get('username')),
                    'email': safe_str(user.get('email')),
                    'full_name': safe_str(user.get('full_name')),
                    'phone': safe_str(user.get('phone')),
                    'country': safe_str(user.get('country')),
                    'wallet': wallet_data,
                    'is_admin': bool(user.get('is_admin', False)),
                    'is_banned': bool(user.get('is_banned', False)),
                    'is_verified': bool(user.get('is_verified', False)),
                    'kyc_status': safe_str(user.get('kyc_status'), 'pending'),
                    'created_at': created_at,
                    'last_login': last_login,
                    'referral_code': safe_str(user.get('referral_code')),
                    'referrals': user.get('referrals', []) or []
                }
                formatted_users.append(user_data)
                
            except Exception as format_error:
                logger.error(f"Error formatting user at index {idx}: {format_error}")
                continue
        
        total_pages = max(1, (total + limit - 1) // limit) if total > 0 else 1
        
        logger.info(f"Returning {len(formatted_users)} formatted users, page {page} of {total_pages}, total: {total}")
        
        response_data = {
            'success': True,
            'data': {
                'users': formatted_users,
                'total': total,
                'page': page,
                'pages': total_pages,
                'limit': limit
            }
        }
        
        response = jsonify(response_data)
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Get users error: {e}", exc_info=True)
        return jsonify({
            'success': False, 
            'message': f'Server error: {str(e)}', 
            'data': {
                'users': [], 
                'total': 0, 
                'page': 1, 
                'pages': 1,
                'limit': 60
            }
        }), 500
@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Admin adjustment')
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        if investment_users is not None:
            investment_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': str(user_id), 'type': 'adjustment', 'amount': abs(amount),
                'status': 'completed', 'description': f'Balance adjustment: {reason} (${amount:+,.2f})',
                'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(user_id, 'Balance Adjusted', f'Balance adjusted by ${amount:+,.2f}. Reason: {reason}', 'info')
        return add_cors_headers(jsonify({'success': True, 'message': f'Balance adjusted by ${amount:+,.2f}'}))
    except Exception as e:
        logger.error(f"Balance adjustment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>/toggle-ban', methods=['POST', 'OPTIONS'])
@require_admin
def admin_toggle_ban(user_id):
    try:
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        new_ban_status = not user.get('is_banned', False)
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status}})
        if investment_users is not None:
            investment_users.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status}})
        
        action = 'banned' if new_ban_status else 'unbanned'
        create_notification(user_id, f'Account {action.capitalize()}', f'Your account has been {action}.', 'warning' if new_ban_status else 'success')
        return add_cors_headers(jsonify({'success': True, 'message': f'User {action} successfully'}))
    except Exception as e:
        logger.error(f"Toggle ban error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>', methods=['DELETE', 'OPTIONS'])
@require_admin
def admin_delete_user(user_id):
    try:
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        username = user.get('username', 'Unknown')
        
        if veloxtrades_users is not None:
            veloxtrades_users.delete_one({'_id': ObjectId(user_id)})
        if investment_users is not None:
            investment_users.delete_one({'_id': ObjectId(user_id)})
        
        # Delete user's data from all collections
        for collection in [investments_collection, transactions_collection, deposits_collection, withdrawals_collection, notifications_collection, kyc_collection, support_tickets_collection]:
            if collection is not None:
                collection.delete_many({'user_id': str(user_id)})
        
        return add_cors_headers(jsonify({'success': True, 'message': f'User {username} deleted'}))
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - DEPOSITS ====================
# ==================== ADMIN - DEPOSITS ====================
@app.route('/api/admin/deposits', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_deposits():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        deposits = []
        total = 0
        
        # Try veloxtrades_deposits first (primary)
        if veloxtrades_deposits is not None:
            try:
                total = veloxtrades_deposits.count_documents(query)
                cursor = veloxtrades_deposits.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                deposits = list(cursor)
                logger.info(f"Fetched {len(deposits)} deposits from veloxtrades_deposits, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from veloxtrades_deposits: {e}", exc_info=True)
        
        # If no deposits found, try investment_deposits
        if len(deposits) == 0 and investment_deposits is not None:
            try:
                total = investment_deposits.count_documents(query)
                cursor = investment_deposits.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                deposits = list(cursor)
                logger.info(f"Fetched {len(deposits)} deposits from investment_deposits, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from investment_deposits: {e}", exc_info=True)
        
        # If still no deposits, try combined collection as last resort
        if len(deposits) == 0 and deposits_collection is not None:
            try:
                total = deposits_collection.count_documents(query)
                cursor = deposits_collection.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                deposits = list(cursor)
                logger.info(f"Fetched {len(deposits)} deposits from combined collection, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from combined collection: {e}", exc_info=True)
        
        # Format deposits
        result_deposits = []
        for deposit in deposits:
            try:
                deposit_copy = dict(deposit)
                deposit_copy['_id'] = str(deposit_copy['_id'])
                if 'created_at' in deposit_copy and isinstance(deposit_copy['created_at'], datetime):
                    deposit_copy['created_at'] = deposit_copy['created_at'].isoformat()
                if 'approved_at' in deposit_copy and isinstance(deposit_copy['approved_at'], datetime):
                    deposit_copy['approved_at'] = deposit_copy['approved_at'].isoformat()
                if 'rejected_at' in deposit_copy and isinstance(deposit_copy['rejected_at'], datetime):
                    deposit_copy['rejected_at'] = deposit_copy['rejected_at'].isoformat()
                
                # Get username from users collection
                if 'user_id' in deposit_copy and users_collection is not None:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(deposit_copy['user_id'])})
                        deposit_copy['username'] = user.get('username', 'Unknown') if user else 'Unknown'
                    except:
                        deposit_copy['username'] = 'Unknown'
                else:
                    deposit_copy['username'] = deposit.get('username', 'Unknown')
                
                result_deposits.append(deposit_copy)
            except Exception as e:
                logger.error(f"Error formatting deposit: {e}")
                continue
        
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
def admin_process_deposit(deposit_id):
    """Process deposit approval/rejection with email and balance update"""
    
    # Handle OPTIONS preflight request
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        print(f"\n🔵 ===== PROCESSING DEPOSIT =====")
        print(f"Deposit ID: {deposit_id}")
        
        # Get admin user
        user = get_user_from_request()
        if not user:
            print(f"❌ No user found in request")
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        if not user.get('is_admin'):
            print(f"❌ User {user.get('username')} is not admin")
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        print(f"✅ Admin authenticated: {user.get('username')}")
        
        # Get request data
        data = request.get_json()
        if not data:
            print(f"❌ No data provided")
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        action = data.get('action')
        reason = data.get('reason', '')
        
        print(f"Action: {action}, Reason: {reason}")
        
        if action not in ['approve', 'reject']:
            print(f"❌ Invalid action: {action}")
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        # ========== FIND DEPOSIT ==========
        deposit = None
        deposit_collection_used = None
        
        print(f"🔍 Searching for deposit: {deposit_id}")
        
        # Try veloxtrades_deposits
        if veloxtrades_deposits is not None:
            try:
                deposit = veloxtrades_deposits.find_one({'_id': ObjectId(deposit_id)})
                if deposit:
                    deposit_collection_used = veloxtrades_deposits
                    print(f"✅ Found deposit in veloxtrades_deposits")
            except Exception as e:
                print(f"Error in veloxtrades_deposits: {e}")
        
        # Try investment_deposits
        if deposit is None and investment_deposits is not None:
            try:
                deposit = investment_deposits.find_one({'_id': ObjectId(deposit_id)})
                if deposit:
                    deposit_collection_used = investment_deposits
                    print(f"✅ Found deposit in investment_deposits")
            except Exception as e:
                print(f"Error in investment_deposits: {e}")
        
        if not deposit:
            print(f"❌ Deposit {deposit_id} NOT FOUND")
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        print(f"📝 Deposit: Amount=${deposit.get('amount')}, Status={deposit.get('status')}, User={deposit.get('user_id')}")
        
        # ========== FIND USER ==========
        target_user = None
        user_id = deposit.get('user_id')
        
        print(f"🔍 Searching for user: {user_id}")
        
        if veloxtrades_users is not None:
            try:
                target_user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if target_user:
                    print(f"✅ Found user in veloxtrades_users: {target_user.get('username')}")
                    print(f"📧 Email: {target_user.get('email')}")
            except Exception as e:
                print(f"Error in veloxtrades_users: {e}")
        
        if target_user is None and investment_users is not None:
            try:
                target_user = investment_users.find_one({'_id': ObjectId(user_id)})
                if target_user:
                    print(f"✅ Found user in investment_users: {target_user.get('username')}")
                    print(f"📧 Email: {target_user.get('email')}")
            except Exception as e:
                print(f"Error in investment_users: {e}")
        
        if not target_user:
            print(f"❌ User {user_id} NOT FOUND")
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            print(f"💰 APPROVING DEPOSIT for {target_user.get('username')}")
            
            # ========== GET CURRENT BALANCE ==========
            old_balance = target_user.get('wallet', {}).get('balance', 0)
            new_balance = old_balance + deposit['amount']
            old_deposited = target_user.get('wallet', {}).get('total_deposited', 0)
            new_deposited = old_deposited + deposit['amount']
            
            print(f"📊 Old balance: ${old_balance}")
            print(f"📊 Adding: ${deposit['amount']}")
            print(f"📊 New balance: ${new_balance}")
            print(f"📊 Total deposited: ${new_deposited}")
            
            # ========== UPDATE USER BALANCE IN VELOXTRADES_DB ==========
            balance_updated = False
            if veloxtrades_users is not None:
                try:
                    result = veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {
                            '$inc': {
                                'wallet.balance': deposit['amount'],
                                'wallet.total_deposited': deposit['amount']
                            }
                        }
                    )
                    balance_updated = result.modified_count > 0
                    print(f"✅ veloxtrades_users updated: {balance_updated}")
                    
                    # Verify the update
                    verify_user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                    print(f"✅ Verified balance: ${verify_user.get('wallet', {}).get('balance', 0)}")
                except Exception as e:
                    print(f"❌ Error updating veloxtrades_users: {e}")
            
            # ========== UPDATE USER BALANCE IN INVESTMENT_DB ==========
            if investment_users is not None:
                try:
                    result = investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {
                            '$inc': {
                                'wallet.balance': deposit['amount'],
                                'wallet.total_deposited': deposit['amount']
                            }
                        }
                    )
                    print(f"✅ investment_users updated: {result.modified_count > 0}")
                except Exception as e:
                    print(f"❌ Error updating investment_users: {e}")
            
            # ========== UPDATE DEPOSIT STATUS ==========
            if deposit_collection_used is not None:
                try:
                    deposit_collection_used.update_one(
                        {'_id': ObjectId(deposit_id)},
                        {'$set': {
                            'status': 'approved',
                            'approved_at': datetime.now(timezone.utc),
                            'processed_by': str(user.get('_id')),
                            'processed_at': datetime.now(timezone.utc)
                        }}
                    )
                    print(f"✅ Deposit status updated to approved")
                except Exception as e:
                    print(f"❌ Error updating deposit: {e}")
            
            # ========== CREATE TRANSACTION RECORD ==========
            if transactions_collection is not None:
                try:
                    # Update existing pending transaction
                    transactions_collection.update_one(
                        {'deposit_id': deposit.get('deposit_id'), 'type': 'deposit', 'status': 'pending'},
                        {'$set': {
                            'status': 'completed',
                            'description': f'Deposit of ${deposit["amount"]:,.2f} via {deposit.get("crypto", "USDT")} - Approved',
                            'completed_at': datetime.now(timezone.utc)
                        }}
                    )
                    print(f"✅ Transaction updated to completed")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
            
            # ========== CREATE NOTIFICATION ==========
            try:
                create_notification(
                    user_id,
                    'Deposit Approved! ✅',
                    f'Your deposit of ${deposit["amount"]:,.2f} has been approved and added to your balance!',
                    'success'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND APPROVAL EMAIL ==========
            email_sent = False
            try:
                print(f"📧 Sending approval email to: {target_user.get('email')}")
                email_sent = send_deposit_approved_email(
                    target_user,
                    deposit['amount'],
                    deposit.get('crypto', 'USDT'),
                    deposit.get('transaction_hash')
                )
                if email_sent:
                    print(f"✅ Approval email sent successfully to {target_user.get('email')}")
                else:
                    print(f"❌ Failed to send approval email")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
                import traceback
                traceback.print_exc()
            
            # ========== ADD REFERRAL COMMISSION ==========
            try:
                add_referral_commission(user_id, deposit['amount'])
                print(f"✅ Referral commission processed")
            except Exception as e:
                print(f"❌ Error adding referral commission: {e}")
            
            print(f"🎉 ===== DEPOSIT APPROVED SUCCESSFULLY =====")
            print(f"   User: {target_user.get('username')}")
            print(f"   Email: {target_user.get('email')}")
            print(f"   Amount: ${deposit['amount']}")
            print(f"   Balance updated: {balance_updated}")
            print(f"   Email sent: {email_sent}")
            print(f"   New balance: ${new_balance}")
            
            response_data = {
                'success': True,
                'message': f'Deposit approved successfully! ${deposit["amount"]:,.2f} added to {target_user.get("username")}',
                'data': {
                    'amount': deposit['amount'],
                    'user': target_user.get('username'),
                    'email': target_user.get('email'),
                    'old_balance': old_balance,
                    'new_balance': new_balance,
                    'email_sent': email_sent,
                    'balance_updated': balance_updated
                }
            }
            
            response = jsonify(response_data)
            response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response
            
        elif action == 'reject':
            print(f"❌ REJECTING DEPOSIT for {target_user.get('username')}")
            
            # ========== UPDATE DEPOSIT STATUS ==========
            if deposit_collection_used is not None:
                try:
                    deposit_collection_used.update_one(
                        {'_id': ObjectId(deposit_id)},
                        {'$set': {
                            'status': 'rejected',
                            'rejection_reason': reason,
                            'rejected_at': datetime.now(timezone.utc),
                            'processed_by': str(user.get('_id'))
                        }}
                    )
                    print(f"✅ Deposit status updated to rejected")
                except Exception as e:
                    print(f"❌ Error updating deposit: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    transactions_collection.update_one(
                        {'deposit_id': deposit.get('deposit_id'), 'type': 'deposit', 'status': 'pending'},
                        {'$set': {
                            'status': 'failed',
                            'description': f'Deposit rejected: {reason}',
                            'rejected_at': datetime.now(timezone.utc)
                        }}
                    )
                    print(f"✅ Transaction updated to failed")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
            
            # ========== CREATE NOTIFICATION ==========
            try:
                create_notification(
                    user_id,
                    'Deposit Rejected ❌',
                    f'Your deposit of ${deposit["amount"]:,.2f} was rejected. Reason: {reason}',
                    'error'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND REJECTION EMAIL ==========
            email_sent = False
            try:
                print(f"📧 Sending rejection email to: {target_user.get('email')}")
                email_sent = send_deposit_rejected_email(
                    target_user,
                    deposit['amount'],
                    deposit.get('crypto', 'USDT'),
                    reason
                )
                if email_sent:
                    print(f"✅ Rejection email sent successfully")
                else:
                    print(f"❌ Failed to send rejection email")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
                import traceback
                traceback.print_exc()
            
            print(f"❌ ===== DEPOSIT REJECTED =====")
            
            response_data = {
                'success': True,
                'message': f'Deposit rejected! Email sent to {target_user.get("email")}',
                'data': {
                    'amount': deposit['amount'],
                    'user': target_user.get('username'),
                    'email': target_user.get('email'),
                    'email_sent': email_sent
                }
            }
            
            response = jsonify(response_data)
            response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
            response.headers['Access-Control-Allow-Credentials'] = 'true'
            return response
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
    except Exception as e:
        print(f"🔥 ===== DEPOSIT PROCESSING ERROR =====")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
        error_response = jsonify({'success': False, 'message': f'Server error: {str(e)}'})
        error_response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        error_response.headers['Access-Control-Allow-Credentials'] = 'true'
        return error_response, 500


@app.route('/api/admin/investments/<investment_id>/process', methods=['POST', 'OPTIONS'])
def admin_process_investment(investment_id):
    """Admin approves or rejects investment request"""
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        action = data.get('action')
        reason = data.get('reason', '')
        
        print(f"🔵 Processing investment {investment_id}, action: {action}")
        
        # Find investment
        investment = None
        investment_collection_used = None
        
        if veloxtrades_investments is not None:
            try:
                investment = veloxtrades_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = veloxtrades_investments
                    print(f"✅ Found investment in veloxtrades_investments")
            except Exception as e:
                print(f"Error in veloxtrades_investments: {e}")
        
        if investment is None and investment_investments is not None:
            try:
                investment = investment_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = investment_investments
                    print(f"✅ Found investment in investment_investments")
            except Exception as e:
                print(f"Error in investment_investments: {e}")
        
        if investment is None and investments_collection is not None:
            try:
                investment = investments_collection.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = investments_collection
                    print(f"✅ Found investment in combined collection")
            except Exception as e:
                print(f"Error in combined collection: {e}")
        
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        
        # Find user
        user = None
        user_id = investment.get('user_id')
        
        if veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in veloxtrades_users: {user.get('username')}")
            except Exception as e:
                print(f"Error in veloxtrades_users: {e}")
        
        if user is None and investment_users is not None:
            try:
                user = investment_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in investment_users: {user.get('username')}")
            except Exception as e:
                print(f"Error in investment_users: {e}")
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            print(f"💰 Approving investment for {user.get('username')}")
            
            # ========== UPDATE INVESTMENT STATUS ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'active',
                            'approved_at': datetime.now(timezone.utc),
                            'approved_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to active")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE USER'S TOTAL INVESTED ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated veloxtrades_users total_invested")
            except Exception as e:
                print(f"❌ Error updating veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated investment_users total_invested")
            except Exception as e:
                print(f"❌ Error updating investment_users: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    # Update the pending request
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'completed',
                            'description': f'Investment in {investment["plan_name"]} - Active (Profit: ${investment["expected_profit"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    # Add investment record
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'investment',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Investment in {investment["plan_name"]} - ${investment["amount"]:,.2f} at {investment["roi"]}% ROI',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Investment transaction record created")
                except Exception as e:
                    print(f"❌ Error creating investment transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Approved! 🎉',
                    f'Your investment of ${investment["amount"]:,.2f} in {investment["plan_name"]} has been approved! Expected profit: ${investment["expected_profit"]:,.2f} after {investment["duration_hours"]} hours.',
                    'success'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_confirmation_email(
                    user,
                    investment['amount'],
                    investment['plan_name'],
                    investment['roi'],
                    investment['expected_profit']
                )
                print(f"✅ Confirmation email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
            
            return jsonify({
                'success': True,
                'message': f'Investment approved successfully!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'expected_profit': investment['expected_profit'],
                    'duration_hours': investment['duration_hours'],
                    'end_date': investment['end_date'].isoformat() if investment.get('end_date') else None,
                    'email_sent': email_sent
                }
            })
            
        elif action == 'reject':
            print(f"❌ Rejecting investment for {user.get('username')}")
            
            # ========== REFUND USER BALANCE ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in veloxtrades_users")
            except Exception as e:
                print(f"❌ Error refunding in veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in investment_users")
            except Exception as e:
                print(f"❌ Error refunding in investment_users: {e}")
            
            # ========== UPDATE INVESTMENT STATUS ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'rejected',
@app.route('/api/admin/investments/<investment_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_investment(investment_id):
    """Admin approves or rejects investment request"""
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        action = data.get('action')
        reason = data.get('reason', '')
        
        print(f"🔵 Processing investment {investment_id}, action: {action}")
        
        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        # Find investment
        investment = None
        investment_collection_used = None
        
        if veloxtrades_investments is not None:
            try:
                investment = veloxtrades_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = veloxtrades_investments
                    print(f"✅ Found investment in veloxtrades_investments")
            except Exception as e:
                print(f"Error in veloxtrades_investments: {e}")
        
        if investment is None and investment_investments is not None:
            try:
                investment = investment_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = investment_investments
                    print(f"✅ Found investment in investment_investments")
            except Exception as e:
                print(f"Error in investment_investments: {e}")
        
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        
        print(f"📝 Investment: Amount=${investment.get('amount')}, Plan={investment.get('plan_name')}, Status={investment.get('status')}")
        
        # Find user
        user = None
        user_id = investment.get('user_id')
        
        if veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in veloxtrades_users: {user.get('username')}")
                    print(f"📧 Email: {user.get('email')}")
            except Exception as e:
                print(f"Error in veloxtrades_users: {e}")
        
        if user is None and investment_users is not None:
            try:
                user = investment_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in investment_users: {user.get('username')}")
            except Exception as e:
                print(f"Error in investment_users: {e}")
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            print(f"💰 APPROVING INVESTMENT for {user.get('username')}")
            
            # ========== UPDATE INVESTMENT STATUS TO ACTIVE ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'active',
                            'approved_at': datetime.now(timezone.utc),
                            'approved_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to active")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE USER'S TOTAL INVESTED ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated veloxtrades_users total_invested")
            except Exception as e:
                print(f"❌ Error updating veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated investment_users total_invested")
            except Exception as e:
                print(f"❌ Error updating investment_users: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'completed',
                            'description': f'Investment in {investment["plan_name"]} - Active (Profit: ${investment["expected_profit"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'investment',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Investment in {investment["plan_name"]} - ${investment["amount"]:,.2f} at {investment["roi"]}% ROI',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Investment transaction record created")
                except Exception as e:
                    print(f"❌ Error creating investment transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Approved! 🎉',
                    f'Your investment of ${investment["amount"]:,.2f} in {investment["plan_name"]} has been approved! Expected profit: ${investment["expected_profit"]:,.2f} after {investment["duration_hours"]} hours.',
                    'success'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND APPROVAL EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_confirmation_email(
                    user,
                    investment['amount'],
                    investment['plan_name'],
                    investment['roi'],
                    investment['expected_profit']
                )
                print(f"✅ Confirmation email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
            
            print(f"🎉 ===== INVESTMENT APPROVED SUCCESSFULLY =====")
            
            return jsonify({
                'success': True,
                'message': f'Investment approved successfully!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'expected_profit': investment['expected_profit'],
                    'duration_hours': investment['duration_hours'],
                    'email_sent': email_sent
                }
            })
            
        elif action == 'reject':
            print(f"❌ REJECTING INVESTMENT for {user.get('username')}")
            
            # ========== REFUND USER BALANCE ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in veloxtrades_users")
            except Exception as e:
                print(f"❌ Error refunding in veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in investment_users")
            except Exception as e:
                print(f"❌ Error refunding in investment_users: {e}")
            
            # ========== UPDATE INVESTMENT STATUS ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'rejected',
                            'rejection_reason': reason,
                            'rejected_at': datetime.now(timezone.utc),
                            'rejected_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to rejected")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'failed',
                            'description': f'Investment request rejected: {reason} (Refunded ${investment["amount"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'refund',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Refund for rejected investment in {investment["plan_name"]} - Reason: {reason}',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Refund transaction record created")
                except Exception as e:
                    print(f"❌ Error creating refund transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Rejected ❌',
                    f'Your investment request of ${investment["amount"]:,.2f} was rejected. Reason: {reason}. ${investment["amount"]:,.2f} has been refunded to your balance.',
                    'error'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND REJECTION EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_rejected_email(user, investment['amount'], investment['plan_name'], reason)
                print(f"✅ Rejection email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending rejection email: {e}")
            
            print(f"❌ ===== INVESTMENT REJECTED =====")
            
            return jsonify({
                'success': True,
                'message': f'Investment rejected and ${investment["amount"]:,.2f} refunded to user!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'email_sent': email_sent,
                    'refunded': True

# ==================== ADMIN - INVESTMENT PROCESSING ====================
@app.route('/api/admin/investments/<investment_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_investment(investment_id):
    """Admin approves or rejects investment request"""
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        action = data.get('action')
        reason = data.get('reason', '')
        
        print(f"🔵 Processing investment {investment_id}, action: {action}")
        
        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        # Find investment
        investment = None
        investment_collection_used = None
        
        if veloxtrades_investments is not None:
            try:
                investment = veloxtrades_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = veloxtrades_investments
                    print(f"✅ Found investment in veloxtrades_investments")
            except Exception as e:
                print(f"Error in veloxtrades_investments: {e}")
        
        if investment is None and investment_investments is not None:
            try:
                investment = investment_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = investment_investments
                    print(f"✅ Found investment in investment_investments")
            except Exception as e:
                print(f"Error in investment_investments: {e}")
        
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        
        print(f"📝 Investment: Amount=${investment.get('amount')}, Plan={investment.get('plan_name')}, Status={investment.get('status')}")
        
        # Find user
        user = None
        user_id = investment.get('user_id')
        
        if veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in veloxtrades_users: {user.get('username')}")
                    print(f"📧 Email: {user.get('email')}")
            except Exception as e:
                print(f"Error in veloxtrades_users: {e}")
        
        if user is None and investment_users is not None:
            try:
                user = investment_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in investment_users: {user.get('username')}")
            except Exception as e:
                print(f"Error in investment_users: {e}")
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            print(f"💰 APPROVING INVESTMENT for {user.get('username')}")
            
            # ========== UPDATE INVESTMENT STATUS TO ACTIVE ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'active',
                            'approved_at': datetime.now(timezone.utc),
                            'approved_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to active")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE USER'S TOTAL INVESTED ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated veloxtrades_users total_invested")
            except Exception as e:
                print(f"❌ Error updating veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated investment_users total_invested")
            except Exception as e:
                print(f"❌ Error updating investment_users: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'completed',
                            'description': f'Investment in {investment["plan_name"]} - Active (Profit: ${investment["expected_profit"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'investment',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Investment in {investment["plan_name"]} - ${investment["amount"]:,.2f} at {investment["roi"]}% ROI',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Investment transaction record created")
                except Exception as e:
                    print(f"❌ Error creating investment transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Approved! 🎉',
                    f'Your investment of ${investment["amount"]:,.2f} in {investment["plan_name"]} has been approved! Expected profit: ${investment["expected_profit"]:,.2f} after {investment["duration_hours"]} hours.',
                    'success'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND APPROVAL EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_confirmation_email(
                    user,
                    investment['amount'],
                    investment['plan_name'],
                    investment['roi'],
                    investment['expected_profit']
                )
                print(f"✅ Confirmation email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
            
            print(f"🎉 ===== INVESTMENT APPROVED SUCCESSFULLY =====")
            
            return jsonify({
                'success': True,
                'message': f'Investment approved successfully!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'expected_profit': investment['expected_profit'],
                    'duration_hours': investment['duration_hours'],
                    'email_sent': email_sent
                }
            })
            
        elif action == 'reject':
            print(f"❌ REJECTING INVESTMENT for {user.get('username')}")
            
            # ========== REFUND USER BALANCE ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in veloxtrades_users")
            except Exception as e:
                print(f"❌ Error refunding in veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in investment_users")
            except Exception as e:
                print(f"❌ Error refunding in investment_users: {e}")
            
            # ========== UPDATE INVESTMENT STATUS ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'rejected',
                            'rejection_reason': reason,
                            'rejected_at': datetime.now(timezone.utc),
                            'rejected_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to rejected")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'failed',
                            'description': f'Investment request rejected: {reason} (Refunded ${investment["amount"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'refund',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Refund for rejected investment in {investment["plan_name"]} - Reason: {reason}',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Refund transaction record created")
                except Exception as e:
                    print(f"❌ Error creating refund transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Rejected ❌',
                    f'Your investment request of ${investment["amount"]:,.2f} was rejected. Reason: {reason}. ${investment["amount"]:,.2f} has been refunded to your balance.',
                    'error'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND REJECTION EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_rejected_email(user, investment['amount'], investment['plan_name'], reason)
                print(f"✅ Rejection email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending rejection email: {e}")
            
            print(f"❌ ===== INVESTMENT REJECTED =====")
            
            return jsonify({
                'success': True,
                'message': f'Investment rejected and ${investment["amount"]:,.2f} refunded to user!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'email_sent': email_sent,
                    'refunded': True
                }
            })
            
    except Exception as e:
        print(f"🔥 ===== PROCESS INVESTMENT ERROR =====")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500


@app.route('/api/admin/resend-deposit-emails', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_emails():
    """Bulk resend deposit approval/rejection emails"""
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        if deposits_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        data = request.get_json() or {}
        status_filter = data.get('status', 'approved')
        
        # Build query based on status filter
        if status_filter != 'all':
            query = {'status': status_filter}
        else:
            query = {'status': {'$in': ['approved', 'rejected']}}
        
        deposits = list(deposits_collection.find(query).limit(100))
        sent = 0
        failed = 0
        
        print(f"📧 Resending emails for {len(deposits)} deposits with status: {status_filter}")
        
        for deposit in deposits:
            if users_collection is None:
                failed += 1
                continue
            
            # Find user
            user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
            if not user:
                print(f"❌ User not found for deposit: {deposit.get('_id')}")
                failed += 1
                continue
            
            # Send email based on status
            if deposit['status'] == 'approved':
                try:
                    if send_deposit_approved_email(
                        user, 
                        deposit['amount'], 
                        deposit.get('crypto', 'USDT'), 
                        deposit.get('transaction_hash')
                    ):
                        sent += 1
                        print(f"✅ Resent approval email to {user.get('email')} for ${deposit['amount']}")
                    else:
                        failed += 1
                        print(f"❌ Failed to send approval email to {user.get('email')}")
                except Exception as e:
                    print(f"❌ Error sending approval email: {e}")
                    failed += 1
                    
            elif deposit['status'] == 'rejected':
                try:
                    if send_deposit_rejected_email(
                        user, 
                        deposit['amount'], 
                        deposit.get('crypto', 'USDT'), 
                        deposit.get('rejection_reason', 'Not specified')
                    ):
                        sent += 1
                        print(f"✅ Resent rejection email to {user.get('email')} for ${deposit['amount']}")
                    else:
                        failed += 1
                        print(f"❌ Failed to send rejection email to {user.get('email')}")
                except Exception as e:
                    print(f"❌ Error sending rejection email: {e}")
                    failed += 1
            else:
                print(f"⚠️ Skipping deposit with unknown status: {deposit.get('status')}")
        
        print(f"📧 Email resend complete: {sent} sent, {failed} failed")
        
        response = jsonify({
            'success': True, 
            'message': f'Resent {sent} emails, {failed} failed', 
            'data': {'sent': sent, 'failed': failed}
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Bulk resend error: {e}")
        import traceback
        traceback.print_exc()
        response = jsonify({'success': False, 'message': str(e)})
        return add_cors_headers(response), 500

@app.route('/api/admin/deposits/<deposit_id>/resend-email', methods=['POST', 'OPTIONS'])
def admin_resend_single_deposit_email(deposit_id):
    # Handle OPTIONS preflight request
    if request.method == "OPTIONS":
        response = make_response()
        origin = request.headers.get('Origin', 'https://www.veloxtrades.com.ng')
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    # Verify admin
    user = get_user_from_request()
    if not user or not user.get('is_admin'):
        return jsonify({'success': False, 'message': 'Admin access required'}), 403
    
    try:
        print(f"🔵 Resending email for deposit {deposit_id}")
        
        # Find deposit - check with is not None
        deposit = None
        if veloxtrades_deposits is not None:
            try:
                deposit = veloxtrades_deposits.find_one({'_id': ObjectId(deposit_id)})
                if deposit:
                    print(f"✅ Found deposit in veloxtrades_deposits")
            except:
                pass
        
        if deposit is None and investment_deposits is not None:
            try:
                deposit = investment_deposits.find_one({'_id': ObjectId(deposit_id)})
                if deposit:
                    print(f"✅ Found deposit in investment_deposits")
            except:
                pass
        
        if not deposit:
            print(f"❌ Deposit not found")
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        
        # Find user
        target_user = None
        if veloxtrades_users is not None:
            try:
                target_user = veloxtrades_users.find_one({'_id': ObjectId(deposit['user_id'])})
            except:
                pass
        
        if target_user is None and investment_users is not None:
            try:
                target_user = investment_users.find_one({'_id': ObjectId(deposit['user_id'])})
            except:
                pass
        
        if not target_user:
            print(f"❌ User not found")
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Send email based on status
        email_sent = False
        if deposit['status'] == 'approved':
            print(f"📧 Sending approval email to {target_user.get('email')}")
            email_sent = send_deposit_approved_email(
                target_user,
                deposit['amount'],
                deposit.get('crypto', 'USDT'),
                deposit.get('transaction_hash')
            )
        elif deposit['status'] == 'rejected':
            print(f"📧 Sending rejection email to {target_user.get('email')}")
            email_sent = send_deposit_rejected_email(
                target_user,
                deposit['amount'],
                deposit.get('crypto', 'USDT'),
                deposit.get('rejection_reason', 'Not specified')
            )
        
        print(f"✅ Email sent: {email_sent}")
        
        return jsonify({'success': email_sent, 'message': 'Email resent' if email_sent else 'Failed to send'})
        
    except Exception as e:
        print(f"🔥 ERROR in resend-email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

# ==================== ADMIN - WITHDRAWALS ====================
@app.route('/api/admin/withdrawals', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_withdrawals():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        withdrawals = []
        total = 0
        
        # Try veloxtrades_withdrawals first (primary)
        if veloxtrades_withdrawals is not None:
            try:
                total = veloxtrades_withdrawals.count_documents(query)
                cursor = veloxtrades_withdrawals.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                withdrawals = list(cursor)
                logger.info(f"Fetched {len(withdrawals)} withdrawals from veloxtrades_withdrawals, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from veloxtrades_withdrawals: {e}", exc_info=True)
        
        # If no withdrawals found, try investment_withdrawals
        if len(withdrawals) == 0 and investment_withdrawals is not None:
            try:
                total = investment_withdrawals.count_documents(query)
                cursor = investment_withdrawals.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                withdrawals = list(cursor)
                logger.info(f"Fetched {len(withdrawals)} withdrawals from investment_withdrawals, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from investment_withdrawals: {e}", exc_info=True)
        
        # If still no withdrawals, try combined collection
        if len(withdrawals) == 0 and withdrawals_collection is not None:
            try:
                total = withdrawals_collection.count_documents(query)
                cursor = withdrawals_collection.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                withdrawals = list(cursor)
                logger.info(f"Fetched {len(withdrawals)} withdrawals from combined collection, total: {total}")
            except Exception as e:
                logger.error(f"Error fetching from combined collection: {e}", exc_info=True)
        
        # Format withdrawals
        result_withdrawals = []
        for withdrawal in withdrawals:
            try:
                withdrawal_copy = dict(withdrawal)
                withdrawal_copy['_id'] = str(withdrawal_copy['_id'])
                if 'created_at' in withdrawal_copy and isinstance(withdrawal_copy['created_at'], datetime):
                    withdrawal_copy['created_at'] = withdrawal_copy['created_at'].isoformat()
                if 'approved_at' in withdrawal_copy and isinstance(withdrawal_copy['approved_at'], datetime):
                    withdrawal_copy['approved_at'] = withdrawal_copy['approved_at'].isoformat()
                
                # Get username
                if 'user_id' in withdrawal_copy and users_collection is not None:
                    try:
                        user = users_collection.find_one({'_id': ObjectId(withdrawal_copy['user_id'])})
                        withdrawal_copy['username'] = user.get('username', 'Unknown') if user else 'Unknown'
                    except:
                        withdrawal_copy['username'] = 'Unknown'
                else:
                    withdrawal_copy['username'] = withdrawal.get('username', 'Unknown')
                
                result_withdrawals.append(withdrawal_copy)
            except Exception as e:
                logger.error(f"Error formatting withdrawal: {e}")
                continue
        
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

@app.route('/api/admin/test-email', methods=['GET', 'OPTIONS'])
@require_admin
def test_email():
    """Test email configuration"""
    try:
        test_email = "test@example.com"  # Replace with your email to test
        subject = "Test Email from Veloxtrades"
        body = "This is a test email to verify email configuration."
        
        result = send_email(test_email, subject, body)
        
        return jsonify({
            'success': result,
            'message': 'Email sent' if result else 'Email failed',
            'email_configured': EMAIL_CONFIGURED,
            'email_user': EMAIL_USER,
            'email_host': EMAIL_HOST
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/admin/withdrawals/<withdrawal_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_withdrawal(withdrawal_id):
    try:
        if withdrawals_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        data = request.get_json()
        action = data.get('action')
        reason = data.get('reason', '')
        
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}})
            if transactions_collection is not None:
                transactions_collection.update_one({'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'}, {'$set': {'status': 'completed'}})
            create_notification(withdrawal['user_id'], 'Withdrawal Approved! ✅', f'Withdrawal of ${withdrawal["amount"]:,.2f} approved!', 'success')
            send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
        elif action == 'reject':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'rejected_at': datetime.now(timezone.utc)}})
            if veloxtrades_users is not None:
                veloxtrades_users.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': withdrawal['amount']}})
            if investment_users is not None:
                investment_users.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': withdrawal['amount']}})
            if transactions_collection is not None:
                transactions_collection.update_one({'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'}, {'$set': {'status': 'failed'}})
            create_notification(withdrawal['user_id'], 'Withdrawal Rejected ❌', f'Withdrawal of ${withdrawal["amount"]:,.2f} rejected. Reason: {reason}', 'error')
            send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        return add_cors_headers(jsonify({'success': True, 'message': f'Withdrawal {action}d successfully'}))
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - INVESTMENTS ====================
@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
    """Get all investments with filtering"""
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        return response
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')  # all, pending, active, completed, rejected
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        investments = []
        total = 0
        
        # Fetch from veloxtrades_investments
        if veloxtrades_investments is not None:
            try:
                total = veloxtrades_investments.count_documents(query)
                cursor = veloxtrades_investments.find(query).sort([('created_at', -1)]).skip(skip).limit(limit)
                investments = list(cursor)
                print(f"📊 Found {len(investments)} investments in veloxtrades_db")
            except Exception as e:
                print(f"Error fetching from veloxtrades_investments: {e}")
        
        # Format investments with user details
        formatted_investments = []
        for inv in investments:
            try:
                # Get user details
                user = None
                if veloxtrades_users is not None:
                    user = veloxtrades_users.find_one({'_id': ObjectId(inv['user_id'])})
                if user is None and investment_users is not None:
                    user = investment_users.find_one({'_id': ObjectId(inv['user_id'])})
                
                inv_copy = {
                    '_id': str(inv['_id']),
                    'investment_id': inv.get('investment_id', str(inv['_id'])),
                    'user_id': str(inv['user_id']),
                    'username': user.get('username', 'Unknown') if user else 'Unknown',
                    'user_email': user.get('email', '') if user else '',
                    'plan': inv.get('plan', ''),
                    'plan_name': inv.get('plan_name', 'Investment'),
                    'amount': inv.get('amount', 0),
                    'roi': inv.get('roi', 0),
                    'expected_profit': inv.get('expected_profit', 0),
                    'duration_hours': inv.get('duration_hours', 0),
                    'status': inv.get('status', 'pending'),
                    'created_at': inv.get('created_at').isoformat() if inv.get('created_at') else None,
                    'start_date': inv.get('start_date').isoformat() if inv.get('start_date') else None,
                    'end_date': inv.get('end_date').isoformat() if inv.get('end_date') else None,
                    'approved_at': inv.get('approved_at').isoformat() if inv.get('approved_at') else None,
                    'rejected_at': inv.get('rejected_at').isoformat() if inv.get('rejected_at') else None,
                    'rejection_reason': inv.get('rejection_reason', '')
                }
                formatted_investments.append(inv_copy)
            except Exception as e:
                print(f"Error formatting investment: {e}")
                continue
        
        response = jsonify({
            'success': True,
            'data': {
                'investments': formatted_investments,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        print(f"🔥 Get investments error: {e}")
        import traceback
        traceback.print_exc()
        return add_cors_headers(jsonify({'success': True, 'data': {'investments': [], 'total': 0}})), 200

@app.route('/api/admin/investments/<investment_id>/complete', methods=['POST', 'OPTIONS'])
@require_admin
def admin_complete_investment(investment_id):
    try:
        if investments_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        investment = investments_collection.find_one({'_id': ObjectId(investment_id)})
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        if investment['status'] != 'active':
            return jsonify({'success': False, 'message': 'Investment already completed'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(investment['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        profit = investment.get('expected_profit', 0)
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': ObjectId(investment['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
        if investment_users is not None:
            investment_users.update_one({'_id': ObjectId(investment['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
        
        investments_collection.update_one({'_id': ObjectId(investment_id)}, {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}})
        
        if transactions_collection is not None:
            transactions_collection.insert_one({
                'user_id': investment['user_id'], 'type': 'profit', 'amount': profit, 'status': 'completed',
                'description': f'Profit from {investment.get("plan_name", "Investment")} (Manual completion)',
                'investment_id': str(investment_id), 'created_at': datetime.now(timezone.utc)
            })
        
        create_notification(investment['user_id'], 'Investment Completed! 🎉', f'Earned ${profit:,.2f} profit!', 'success')
        send_investment_completed_email(user, investment['amount'], investment.get('plan_name', 'Investment'), profit)
        
        return add_cors_headers(jsonify({'success': True, 'message': 'Investment completed', 'data': {'profit_added': profit}}))
    except Exception as e:
        logger.error(f"Complete investment error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/investments/<investment_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_investment(investment_id):
    """Admin approves or rejects investment request"""
    
    # Handle OPTIONS preflight
    if request.method == "OPTIONS":
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
            
        action = data.get('action')
        reason = data.get('reason', '')
        
        print(f"🔵 Processing investment {investment_id}, action: {action}")
        
        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        # Find investment
        investment = None
        investment_collection_used = None
        
        if veloxtrades_investments is not None:
            try:
                investment = veloxtrades_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = veloxtrades_investments
                    print(f"✅ Found investment in veloxtrades_investments")
            except Exception as e:
                print(f"Error in veloxtrades_investments: {e}")
        
        if investment is None and investment_investments is not None:
            try:
                investment = investment_investments.find_one({'_id': ObjectId(investment_id)})
                if investment:
                    investment_collection_used = investment_investments
                    print(f"✅ Found investment in investment_investments")
            except Exception as e:
                print(f"Error in investment_investments: {e}")
        
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        
        print(f"📝 Investment: Amount=${investment.get('amount')}, Plan={investment.get('plan_name')}, Status={investment.get('status')}")
        
        # Find user
        user = None
        user_id = investment.get('user_id')
        
        if veloxtrades_users is not None:
            try:
                user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in veloxtrades_users: {user.get('username')}")
                    print(f"📧 Email: {user.get('email')}")
            except Exception as e:
                print(f"Error in veloxtrades_users: {e}")
        
        if user is None and investment_users is not None:
            try:
                user = investment_users.find_one({'_id': ObjectId(user_id)})
                if user:
                    print(f"✅ Found user in investment_users: {user.get('username')}")
            except Exception as e:
                print(f"Error in investment_users: {e}")
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        if action == 'approve':
            print(f"💰 APPROVING INVESTMENT for {user.get('username')}")
            
            # ========== UPDATE INVESTMENT STATUS TO ACTIVE ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'active',
                            'approved_at': datetime.now(timezone.utc),
                            'approved_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to active")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")
            
            # ========== UPDATE USER'S TOTAL INVESTED ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated veloxtrades_users total_invested")
            except Exception as e:
                print(f"❌ Error updating veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.total_invested': investment['amount']}}
                    )
                    print(f"✅ Updated investment_users total_invested")
            except Exception as e:
                print(f"❌ Error updating investment_users: {e}")
            
            # ========== UPDATE TRANSACTION ==========
            if transactions_collection is not None:
                try:
                    # Update the pending request to completed
                    transactions_collection.update_one(
                        {'investment_id': investment_id, 'type': 'investment_request'},
                        {'$set': {
                            'status': 'completed',
                            'description': f'Investment in {investment["plan_name"]} - Active (Profit: ${investment["expected_profit"]:,.2f})'
                        }}
                    )
                    print(f"✅ Updated investment_request transaction")
                except Exception as e:
                    print(f"❌ Error updating transaction: {e}")
                
                try:
                    # Add investment record
                    transactions_collection.insert_one({
                        'user_id': str(user_id),
                        'type': 'investment',
                        'amount': investment['amount'],
                        'status': 'completed',
                        'description': f'Investment in {investment["plan_name"]} - ${investment["amount"]:,.2f} at {investment["roi"]}% ROI',
                        'investment_id': investment_id,
                        'created_at': datetime.now(timezone.utc)
                    })
                    print(f"✅ Investment transaction record created")
                except Exception as e:
                    print(f"❌ Error creating investment transaction: {e}")
            
            # ========== NOTIFY USER ==========
            try:
                create_notification(
                    user_id,
                    'Investment Approved! 🎉',
                    f'Your investment of ${investment["amount"]:,.2f} in {investment["plan_name"]} has been approved! Expected profit: ${investment["expected_profit"]:,.2f} after {investment["duration_hours"]} hours.',
                    'success'
                )
                print(f"✅ Notification created")
            except Exception as e:
                print(f"❌ Error creating notification: {e}")
            
            # ========== SEND APPROVAL EMAIL ==========
            email_sent = False
            try:
                email_sent = send_investment_confirmation_email(
                    user,
                    investment['amount'],
                    investment['plan_name'],
                    investment['roi'],
                    investment['expected_profit']
                )
                print(f"✅ Confirmation email sent: {email_sent}")
            except Exception as e:
                print(f"❌ Error sending email: {e}")
            
            print(f"🎉 ===== INVESTMENT APPROVED SUCCESSFULLY =====")
            
            return jsonify({
                'success': True,
                'message': f'Investment approved successfully!',
                'data': {
                    'amount': investment['amount'],
                    'user': user.get('username'),
                    'expected_profit': investment['expected_profit'],
                    'duration_hours': investment['duration_hours'],
                    'email_sent': email_sent
                }
            })
            
        elif action == 'reject':
            print(f"❌ REJECTING INVESTMENT for {user.get('username')}")
            
            # ========== REFUND USER BALANCE (Money was deducted at request) ==========
            try:
                if veloxtrades_users is not None:
                    veloxtrades_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in veloxtrades_users")
            except Exception as e:
                print(f"❌ Error refunding in veloxtrades_users: {e}")
            
            try:
                if investment_users is not None:
                    investment_users.update_one(
                        {'_id': ObjectId(user_id)},
                        {'$inc': {'wallet.balance': investment['amount']}}
                    )
                    print(f"✅ Refunded ${investment['amount']} to user in investment_users")
            except Exception as e:
                print(f"❌ Error refunding in investment_users: {e}")
            
            # ========== UPDATE INVESTMENT STATUS ==========
            if investment_collection_used is not None:
                try:
                    investment_collection_used.update_one(
                        {'_id': ObjectId(investment_id)},
                        {'$set': {
                            'status': 'rejected',
                            'rejection_reason': reason,
                            'rejected_at': datetime.now(timezone.utc),
                            'rejected_by': str(get_user_from_request()['_id'])
                        }}
                    )
                    print(f"✅ Investment status updated to rejected")
                except Exception as e:
                    print(f"❌ Error updating investment: {e}")

# ==================== ADMIN - TRANSACTIONS ====================
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
        
        # ✅ FIXED: Use list of tuples
        transactions = list(transactions_collection.find(query).sort([('created_at', -1)]).skip(skip).limit(limit))
        
        result_transactions = []
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if 'created_at' in tx and isinstance(tx['created_at'], datetime):
                tx['created_at'] = tx['created_at'].isoformat()
            result_transactions.append(tx)
        
        return add_cors_headers(jsonify({
            'success': True,
            'data': {
                'transactions': result_transactions,
                'total': total,
                'page': page,
                'pages': (total + limit - 1) // limit if total > 0 else 1
            }
        }))
    except Exception as e:
        logger.error(f"Get admin transactions error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'transactions': [], 'total': 0}})), 200



# ==================== ADMIN - CREATE TRANSACTION ====================
@app.route('/api/admin/create-transaction', methods=['POST', 'OPTIONS'])
@require_admin
def admin_create_transaction():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        transaction_type = data.get('type', 'adjustment')
        amount = float(data.get('amount', 0))
        description = data.get('description', 'Manual transaction')
        add_to_balance = data.get('add_to_balance', True)
        
        if not user_id or amount <= 0:
            return jsonify({'success': False, 'message': 'User ID and positive amount required'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        transaction_data = {
            'user_id': user_id, 'type': transaction_type, 'amount': amount,
            'status': 'completed', 'description': f'{description} (Admin created)',
            'created_at': datetime.now(timezone.utc), 'admin_created': True
        }
        
        result = None
        if transactions_collection is not None:
            result = transactions_collection.insert_one(transaction_data)
        
        if add_to_balance:
            if veloxtrades_users is not None:
                veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
            if investment_users is not None:
                investment_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
            create_notification(user_id, f'{transaction_type.capitalize()} Added! 🎉', f'${amount:,.2f} added to your account. Reason: {description}', 'success')
            new_balance = user.get('wallet', {}).get('balance', 0) + amount
            return add_cors_headers(jsonify({'success': True, 'message': f'Transaction created and ${amount:,.2f} added', 'data': {'new_balance': new_balance}}))
        
        return add_cors_headers(jsonify({'success': True, 'message': 'Transaction created', 'data': {'transaction_id': str(result.inserted_id) if result else None}}))
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/applications', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_applications():
    if kyc_collection is None:
        return jsonify({'success': True, 'data': {'applications': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'pending')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = kyc_collection.count_documents(query)
        
        # FIXED: Use list of tuples for sort
        applications = list(kyc_collection.find(query).sort([('submitted_at', -1)]).skip(skip).limit(limit))
        
        result_applications = []
        for app in applications:
            app['_id'] = str(app['_id'])
            if app.get('submitted_at'):
                app['submitted_at'] = app['submitted_at'].isoformat()
            if app.get('reviewed_at'):
                app['reviewed_at'] = app['reviewed_at'].isoformat()
            
            if users_collection and app.get('user_id'):
                try:
                    user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
                    if user:
                        app['user_details'] = {
                            'username': user.get('username', ''),
                            'email': user.get('email', ''),
                            'phone': user.get('phone', ''),
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
    try:
        if kyc_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        
        kyc['_id'] = str(kyc['_id'])
        if kyc.get('submitted_at'):
            kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
            if user:
                kyc['user_details'] = {'username': user.get('username', ''), 'email': user.get('email', ''), 'wallet_balance': user.get('wallet', {}).get('balance', 0)}
        
        return add_cors_headers(jsonify({'success': True, 'data': kyc}))
    except Exception as e:
        logger.error(f"Get KYC application error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>/approve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_approve_kyc(kyc_id):
    try:
        if kyc_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        
        kyc_collection.update_one({'_id': ObjectId(kyc_id)}, {'$set': {'status': 'approved', 'reviewed_at': datetime.now(timezone.utc)}})
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'verified', 'is_verified': True}})
        if investment_users is not None:
            investment_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'verified', 'is_verified': True}})
        
        create_notification(kyc['user_id'], 'KYC Approved! ✅', 'Your KYC verification has been approved.', 'success')
        
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
            if user:
                send_email(user['email'], 'KYC Verification Approved', f'Dear {user.get("username")},\n\nYour KYC has been approved.\n\nBest regards,\nVeloxtrades')
        
        return add_cors_headers(jsonify({'success': True, 'message': 'KYC approved'}))
    except Exception as e:
        logger.error(f"Approve KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>/reject', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reject_kyc(kyc_id):
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason required'}), 400
        
        if kyc_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        
        kyc_collection.update_one({'_id': ObjectId(kyc_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'reviewed_at': datetime.now(timezone.utc)}})
        
        if veloxtrades_users is not None:
            veloxtrades_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'rejected'}})
        if investment_users is not None:
            investment_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'rejected'}})
        
        create_notification(kyc['user_id'], 'KYC Rejected ❌', f'Your KYC was rejected. Reason: {reason}', 'error')
        
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
            if user:
                send_email(user['email'], 'KYC Verification Rejected', f'Dear {user.get("username")},\n\nYour KYC was rejected.\nReason: {reason}\n\nPlease submit new documents.\n\nBest regards,\nVeloxtrades')
        
        return add_cors_headers(jsonify({'success': True, 'message': 'KYC rejected'}))
    except Exception as e:
        logger.error(f"Reject KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_stats():
    if kyc_collection is None:
        return jsonify({'success': True, 'data': {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}}), 200
    
    try:
        pending = kyc_collection.count_documents({'status': 'pending'})
        approved = kyc_collection.count_documents({'status': 'approved'})
        rejected = kyc_collection.count_documents({'status': 'rejected'})
        
        response = jsonify({
            'success': True,
            'data': {
                'pending': pending,
                'approved': approved,
                'rejected': rejected,
                'total': pending + approved + rejected
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get KYC stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN - SUPPORT TICKETS ====================
@app.route('/api/admin/support/tickets', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_tickets():
    if support_tickets_collection is None:
        return jsonify({'success': True, 'data': {'tickets': [], 'total': 0}}), 200
    
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        
        query = {}
        if status != 'all':
            query['status'] = status
        
        total = support_tickets_collection.count_documents(query)
        
        # FIXED: Use list of tuples for sort
        tickets = list(support_tickets_collection.find(query).sort([('created_at', -1)]).skip(skip).limit(limit))
        
        result_tickets = []
        for ticket in tickets:
            ticket['_id'] = str(ticket['_id'])
            if ticket.get('created_at'):
                ticket['created_at'] = ticket['created_at'].isoformat()
            if ticket.get('updated_at'):
                ticket['updated_at'] = ticket['updated_at'].isoformat()
            
            ticket['message_count'] = len(ticket.get('messages', []))
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
    try:
        if support_tickets_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        ticket['_id'] = str(ticket['_id'])
        if ticket.get('created_at'):
            ticket['created_at'] = ticket['created_at'].isoformat()
        if ticket.get('updated_at'):
            ticket['updated_at'] = ticket['updated_at'].isoformat()
        for msg in ticket.get('messages', []):
            if msg.get('created_at'):
                msg['created_at'] = msg['created_at'].isoformat()
        
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
            if user:
                ticket['user_details'] = {'username': user.get('username', ''), 'email': user.get('email', ''), 'wallet_balance': user.get('wallet', {}).get('balance', 0)}
        
        return add_cors_headers(jsonify({'success': True, 'data': ticket}))
    except Exception as e:
        logger.error(f"Admin get ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reply_ticket(ticket_id):
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'message': 'Message required'}), 400
        
        admin_user = get_user_from_request()
        
        if support_tickets_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        reply = {'sender': 'admin', 'sender_id': str(admin_user['_id']), 'sender_name': admin_user.get('username', 'Admin'), 'message': message, 'created_at': datetime.now(timezone.utc)}
        support_tickets_collection.update_one({'ticket_id': ticket_id}, {'$push': {'messages': reply}, '$set': {'updated_at': datetime.now(timezone.utc), 'status': 'pending'}})
        
        if users_collection is not None:
            user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
            if user:
                send_email(user['email'], f'New Reply to Ticket #{ticket_id}', f'Admin replied: {message}')
                create_notification(ticket['user_id'], f'Ticket Updated: {ticket_id}', 'Admin has replied to your ticket.', 'info')
        
        return add_cors_headers(jsonify({'success': True, 'message': 'Reply sent'}))
    except Exception as e:
        logger.error(f"Admin reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>/resolve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resolve_ticket(ticket_id):
    try:
        if support_tickets_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        support_tickets_collection.update_one({'ticket_id': ticket_id}, {'$set': {'status': 'resolved', 'closed_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)}})
        create_notification(ticket['user_id'], f'Ticket Resolved: {ticket_id}', 'Your ticket has been resolved.', 'success')
        
        return add_cors_headers(jsonify({'success': True, 'message': 'Ticket resolved'}))
    except Exception as e:
        logger.error(f"Resolve ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_ticket_stats():
    if support_tickets_collection is None:
        return jsonify({'success': True, 'data': {'open': 0, 'pending': 0, 'resolved': 0, 'closed': 0, 'total': 0}}), 200
    
    try:
        open_tickets = support_tickets_collection.count_documents({'status': 'open'})
        pending_tickets = support_tickets_collection.count_documents({'status': 'pending'})
        resolved_tickets = support_tickets_collection.count_documents({'status': 'resolved'})
        closed_tickets = support_tickets_collection.count_documents({'status': 'closed'})
        
        response = jsonify({
            'success': True,
            'data': {
                'open': open_tickets,
                'pending': pending_tickets,
                'resolved': resolved_tickets,
                'closed': closed_tickets,
                'total': open_tickets + pending_tickets + resolved_tickets + closed_tickets
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get ticket stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - EMAIL & BROADCAST ====================
@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast_email():
    try:
        data = request.get_json()
        recipients_type = data.get('recipients', 'all')
        subject = data.get('subject')
        message = data.get('message')
        html_message = data.get('html_message')
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message required'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        query = {}
        if recipients_type == 'active':
            query = {'is_banned': False}
        elif recipients_type == 'depositors':
            query = {'wallet.total_deposited': {'$gt': 0}}
        elif recipients_type == 'investors':
            if investments_collection is not None:
                active_investors = investments_collection.distinct('user_id', {'status': 'active'})
                if active_investors:
                    query = {'_id': {'$in': [ObjectId(uid) for uid in active_investors]}}
                else:
                    query = {'_id': {'$in': []}}
        elif recipients_type == 'new_users':
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            query = {'created_at': {'$gte': thirty_days_ago}}
        elif recipients_type == 'verified_kyc':
            query = {'kyc_status': 'verified'}
        
        users = list(users_collection.find(query))
        if not users:
            return add_cors_headers(jsonify({'success': True, 'message': 'No users found', 'data': {'sent': 0, 'total': 0}}))
        
        if not html_message:
            html_message = f'<div style="font-family:Arial;max-width:600px;margin:0 auto;"><div style="background:#10b981;padding:20px;text-align:center;color:white;"><h1>Veloxtrades</h1></div><div style="padding:20px;"><h2>{subject}</h2><p>{message.replace(chr(10), "<br>")}</p></div></div>'
        
        sent_count = 0
        for user in users:
            try:
                if send_email(user['email'], subject, message, html_message):
                    create_notification(user['_id'], subject, message, 'info')
                    sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send to {user['email']}: {e}")
        
        admin_user = get_user_from_request()
        log_admin_action(admin_user['_id'], 'Broadcast Email', f"Sent to {sent_count}/{len(users)} users")
        
        return add_cors_headers(jsonify({'success': True, 'message': f'Broadcast sent to {sent_count} users', 'data': {'sent': sent_count, 'total': len(users)}}))
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/email-config', methods=['GET', 'OPTIONS'])
@require_admin
def admin_email_config_check():
    is_valid, message = check_email_configuration() if EMAIL_CONFIGURED else (False, "Email not configured")
    return add_cors_headers(jsonify({'success': True, 'data': {'configured': EMAIL_CONFIGURED, 'valid': is_valid, 'message': message, 'host': EMAIL_HOST, 'port': EMAIL_PORT, 'from': EMAIL_FROM, 'user': EMAIL_USER if EMAIL_USER else 'Not set'}}))


@app.route('/api/admin/send-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_send_email():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        subject = data.get('subject')
        message = data.get('message')
        
        if not user_id or not subject or not message:
            return jsonify({'success': False, 'message': 'User ID, subject, and message required'}), 400
        
        if users_collection is None:
            return jsonify({'success': False, 'message': 'Database connection error'}), 500
        
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        html_body = f'<div style="font-family:Arial;max-width:600px;margin:0 auto;"><div style="background:#10b981;padding:20px;text-align:center;color:white;"><h1>Veloxtrades</h1></div><div style="padding:20px;"><h2>{subject}</h2><p>{message.replace(chr(10), "<br>")}</p></div></div>'
        
        if send_email(user['email'], subject, message, html_body):
            create_notification(user_id, subject, message, 'info')
            return add_cors_headers(jsonify({'success': True, 'message': f'Email sent to {user["email"]}'}))
        else:
            return jsonify({'success': False, 'message': 'Failed to send email'}), 500
    except Exception as e:
        logger.error(f"Send email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - REFERRALS ====================
@app.route('/api/admin/referral-stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_referral_stats():
    try:
        if users_collection is None:
            return add_cors_headers(jsonify({'success': True, 'data': {'stats': {}, 'top_referrers': [], 'referral_network': []}}))
        
        all_users = list(users_collection.find({}, {'username': 1, 'email': 1, 'full_name': 1, 'referral_code': 1, 'referred_by': 1, 'created_at': 1, 'wallet.total_deposited': 1}))
        
        referral_network = []
        for user in all_users:
            referral_code = user.get('referral_code', '')
            referrals = [u for u in all_users if u.get('referred_by') == referral_code]
            total_commission = 0
            for ref in referrals:
                total_deposited = ref.get('wallet', {}).get('total_deposited', 0)
                total_commission += total_deposited * 0.05
            referral_network.append({
                'user_id': str(user['_id']), 'username': user.get('username', ''), 'email': user.get('email', ''),
                'full_name': user.get('full_name', ''), 'referral_code': referral_code,
                'referred_by': user.get('referred_by', 'None'),
                'joined': user.get('created_at').isoformat() if user.get('created_at') else None,
                'total_deposited': user.get('wallet', {}).get('total_deposited', 0),
                'referrals_count': len(referrals), 'total_commission': total_commission,
                'referrals': [{'username': r.get('username', ''), 'email': r.get('email', ''), 'total_deposited': r.get('wallet', {}).get('total_deposited', 0)} for r in referrals]
            })
        
        referral_network.sort(key=lambda x: x['referrals_count'], reverse=True)
        top_referrers = referral_network[:10]
        total_users = len(all_users)
        users_with_referrals = len([u for u in referral_network if u['referrals_count'] > 0])
        total_referrals = sum(u['referrals_count'] for u in referral_network)
        total_commission_paid = sum(u['total_commission'] for u in referral_network)
        
        return add_cors_headers(jsonify({'success': True, 'data': {
            'stats': {'total_users': total_users, 'users_with_referrals': users_with_referrals, 'total_referrals': total_referrals, 'total_commission_paid': total_commission_paid, 'top_referrer': top_referrers[0] if top_referrers else None},
            'top_referrers': top_referrers, 'referral_network': referral_network
        }}))
    except Exception as e:
        logger.error(f"Get referral stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN RESET ====================
@app.route('/api/admin/reset-all', methods=['GET', 'POST', 'OPTIONS'])
def reset_all_admin():
    secret_key = request.args.get('secret') or request.headers.get('X-Admin-Secret')
    if not secret_key or secret_key != ADMIN_RESET_SECRET:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    try:
        existing_admin = None
        if veloxtrades_users is not None:
            existing_admin = veloxtrades_users.find_one({'$or': [{'username': 'admin'}, {'is_admin': True}]})
        
        hashed_password = hash_password('admin123')
        admin_data = {
            'full_name': 'System Administrator', 'email': 'admin@veloxtrades.ltd', 'username': 'admin',
            'password': hashed_password, 'phone': '+1234567890', 'country': 'USA',
            'wallet': {'balance': 100000.00, 'total_deposited': 100000.00, 'total_withdrawn': 0.00, 'total_invested': 0.00, 'total_profit': 0.00},
            'is_admin': True, 'is_verified': True, 'is_active': True, 'is_banned': False,
            'two_factor_enabled': False, 'created_at': datetime.now(timezone.utc), 'last_login': None,
            'referral_code': 'ADMIN2025', 'referrals': [], 'kyc_status': 'verified'
        }
        
        if existing_admin:
            if veloxtrades_users is not None:
                veloxtrades_users.update_one({'_id': existing_admin['_id']}, {'$set': {'password': hashed_password, 'is_admin': True}})
            if investment_users is not None:
                investment_users.update_one({'_id': existing_admin['_id']}, {'$set': {'password': hashed_password, 'is_admin': True}})
            admin_id = existing_admin['_id']
            message = 'Admin account updated'
        else:
            result = veloxtrades_users.insert_one(admin_data) if veloxtrades_users is not None else None
            if investment_users is not None:
                investment_users.insert_one(admin_data)
            admin_id = result.inserted_id if result else 'unknown'
            message = 'Admin account created'
        
        logger.info(f"✅ {message}: admin / admin123")
        return jsonify({'success': True, 'message': f'✅ {message}!', 'credentials': {'username': 'admin', 'password': 'admin123'}, 'admin_id': str(admin_id)})
    except Exception as e:
        logger.error(f"Reset admin error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== SYSTEM & UTILITY ENDPOINTS ====================
@app.route('/health', methods=['GET', 'OPTIONS'])
@app.route('/api/health', methods=['GET', 'OPTIONS'])
def health_check():
    return add_cors_headers(jsonify({
        'success': True, 'status': 'healthy',
        'mongo': 'connected' if veloxtrades_db is not None else 'disconnected',
        'databases': {'veloxtrades_db': veloxtrades_db is not None, 'investment_db': investment_db is not None},
        'email': {'configured': EMAIL_CONFIGURED},
        'timestamp': datetime.now(timezone.utc).isoformat()
    }))


@app.route('/api/database-status', methods=['GET', 'OPTIONS'])
def database_status():
    return add_cors_headers(jsonify({
        'success': True,
        'data': {
            'veloxtrades_db': {
                'connected': veloxtrades_db is not None,
                'collections': {
                    'users': veloxtrades_users is not None,
                    'transactions': veloxtrades_transactions is not None,
                    'deposits': veloxtrades_deposits is not None,
                    'withdrawals': veloxtrades_withdrawals is not None,
                    'investments': veloxtrades_investments is not None,
                    'notifications': veloxtrades_notifications is not None,
                    'kyc': veloxtrades_kyc is not None,
                    'support_tickets': veloxtrades_support_tickets is not None
                }
            },
            'investment_db': {
                'connected': investment_db is not None,
                'collections': {
                    'users': investment_users is not None,
                    'transactions': investment_transactions is not None,
                    'deposits': investment_deposits is not None,
                    'withdrawals': investment_withdrawals is not None,
                    'investments': investment_investments is not None,
                    'notifications': investment_notifications is not None,
                    'kyc': investment_kyc is not None,
                    'support_tickets': investment_support_tickets is not None
                }
            }
        }
    }))


@app.route('/')
def serve_index():
    return add_cors_headers(jsonify({
        'success': True, 'message': 'Veloxtrades API Server (Dual Database Mode)',
        'frontend': FRONTEND_URL, 'databases': {'veloxtrades_db': veloxtrades_db is not None, 'investment_db': investment_db is not None},
        'endpoints': ['/health', '/api/health', '/api/database-status', '/api/register', '/api/login', '/api/verify-token']
    }))


@app.route('/<path:filename>')
def serve_static_files(filename):
    try:
        return add_cors_headers(make_response(send_from_directory(app.static_folder, filename)))
    except Exception:
        return jsonify({'success': False, 'message': 'File not found'}), 404


# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 VELOXTRADES API SERVER - DUAL DATABASE MODE")
    print("=" * 70)
    
    if db_connected:
        print("📊 DATABASE STATUS: BOTH databases connected")
        print("🔍 SEARCH MODE: Searching across BOTH databases for ALL operations")
    else:
        print("❌ MongoDB Connection Failed!")
    
    print("\n👑 Admin Dashboard Ready")
    print("=" * 70)
    print("📝 TO CREATE/UPDATE ADMIN:")
    print(f"   GET or POST {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)
    
    port = int(os.getenv('PORT', '10000'))
    host = os.getenv('HOST', '0.0.0.0')
    
    print(f"🌐 Server running on {host}:{port}")
    print("=" * 70)
    
    app.run(host=host, port=port, debug=False, threaded=True)
