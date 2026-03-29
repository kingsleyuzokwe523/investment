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
    # Force flush print statements
import sys
sys.stdout.flush()
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

# ==================== DUAL DATABASE CONFIGURATION ====================
# Database names
DB_VELOXTRADES = 'veloxtrades_db'
DB_INVESTMENT = 'investment_db'
# test_api.py

# ==================== MONGO DB CONNECTION WITH DUAL DATABASES ====================
import certifi
import ssl

# Main MongoDB client
client = None

# Database connections
veloxtrades_db = None
investment_db = None

# ==================== COLLECTIONS FOR BOTH DATABASES ====================
# Each database will have ALL these collections
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

# ==================== COMBINED COLLECTIONS (SEARCH ACROSS BOTH DATABASES) ====================
# These will search across both databases for each data type
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

def connect_to_databases():
    """Connect to both databases and set up all collections in both"""
    global client, veloxtrades_db, investment_db
    
    # veloxtrades_db collections
    global veloxtrades_users, veloxtrades_transactions, veloxtrades_notifications, veloxtrades_kyc
    global veloxtrades_support_tickets, veloxtrades_admin_logs, veloxtrades_settings, veloxtrades_email_logs
    global veloxtrades_investments, veloxtrades_deposits, veloxtrades_withdrawals, veloxtrades_referral_stats
    
    # investment_db collections
    global investment_users, investment_transactions, investment_notifications, investment_kyc
    global investment_support_tickets, investment_admin_logs, investment_settings, investment_email_logs
    global investment_investments, investment_deposits, investment_withdrawals, investment_referral_stats
    
    # Combined collections
    global users_collection, investments_collection, transactions_collection, deposits_collection
    global withdrawals_collection, notifications_collection, kyc_collection, support_tickets_collection
    global admin_logs_collection, settings_collection, email_logs_collection, referral_stats_collection
    
    try:
        # Connect to MongoDB
        mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
        client = MongoClient(mongo_uri, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
        
        # Test connection
        client.admin.command('ping')
        logger.info("✅ MongoDB connection successful")
        
        # Get both databases
        veloxtrades_db = client[DB_VELOXTRADES]
        investment_db = client[DB_INVESTMENT]
        
        # ==================== CREATE ALL COLLECTIONS IN VELOXTRADES DB ====================
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
        
        # ==================== CREATE ALL COLLECTIONS IN INVESTMENT DB ====================
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
        
        # ==================== SET UP COMBINED COLLECTIONS (SEARCH ACROSS BOTH) ====================
        # Users - search across both databases
        users_collection = DualDatabaseCollection(
            [veloxtrades_users, investment_users], 
            'users'
        )
        
        # Investments - search across both databases
        investments_collection = DualDatabaseCollection(
            [veloxtrades_investments, investment_investments], 
            'investments'
        )
        
        # Transactions - search across both databases
        transactions_collection = DualDatabaseCollection(
            [veloxtrades_transactions, investment_transactions], 
            'transactions'
        )
        
        # Deposits - search across both databases
        deposits_collection = DualDatabaseCollection(
            [veloxtrades_deposits, investment_deposits], 
            'deposits'
        )
        
        # Withdrawals - search across both databases
        withdrawals_collection = DualDatabaseCollection(
            [veloxtrades_withdrawals, investment_withdrawals], 
            'withdrawals'
        )
        
        # Notifications - search across both databases
        notifications_collection = DualDatabaseCollection(
            [veloxtrades_notifications, investment_notifications], 
            'notifications'
        )
        
        # KYC - search across both databases
        kyc_collection = DualDatabaseCollection(
            [veloxtrades_kyc, investment_kyc], 
            'kyc'
        )
        
        # Support Tickets - search across both databases
        support_tickets_collection = DualDatabaseCollection(
            [veloxtrades_support_tickets, investment_support_tickets], 
            'support_tickets'
        )
        
        # Admin Logs - search across both databases
        admin_logs_collection = DualDatabaseCollection(
            [veloxtrades_admin_logs, investment_admin_logs], 
            'admin_logs'
        )
        
        # Settings - search across both databases
        settings_collection = DualDatabaseCollection(
            [veloxtrades_settings, investment_settings], 
            'settings'
        )
        
        # Email Logs - search across both databases
        email_logs_collection = DualDatabaseCollection(
            [veloxtrades_email_logs, investment_email_logs], 
            'email_logs'
        )
        
        # Referral Stats - search across both databases
        referral_stats_collection = DualDatabaseCollection(
            [veloxtrades_referral_stats, investment_referral_stats], 
            'referral_stats'
        )
        
        logger.info("=" * 60)
        logger.info("📊 DUAL DATABASE CONFIGURATION:")
        logger.info(f"   ✅ veloxtrades_db: {DB_VELOXTRADES}")
        logger.info(f"   ✅ investment_db: {DB_INVESTMENT}")
        logger.info("   📂 BOTH databases contain ALL collections:")
        logger.info("      - users, transactions, notifications, kyc, support_tickets")
        logger.info("      - admin_logs, settings, email_logs, investments")
        logger.info("      - deposits, withdrawals, referral_stats")
        logger.info("=" * 60)
        logger.info("🔍 SEARCH MODE: Searching across BOTH databases for all data types")
        logger.info("=" * 60)
        
        return True
        
    except errors.ServerSelectionTimeoutError as e:
        logger.error(f"❌ MongoDB connection timeout: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ MongoDB connection error: {e}")
        return False


class DualDatabaseCollection:
    """A wrapper that searches across multiple database collections"""
    
    def __init__(self, collections, name):
        self.collections = collections
        self.name = name
        # Remove None collections
        self.collections = [c for c in collections if c is not None]
    
    def find(self, query=None, *args, **kwargs):
        """Find documents across all databases"""
        results = []
        for collection in self.collections:
            try:
                cursor = collection.find(query or {}, *args, **kwargs)
                results.extend(list(cursor))
            except Exception as e:
                logger.error(f"Error searching {self.name} in collection: {e}")
        return results
    
    def find_one(self, query=None, *args, **kwargs):
        """Find one document across all databases (returns first found)"""
        for collection in self.collections:
            try:
                result = collection.find_one(query or {}, *args, **kwargs)
                if result:
                    return result
            except Exception as e:
                logger.error(f"Error finding one in {self.name}: {e}")
        return None
    
    def insert_one(self, document, *args, **kwargs):
        """Insert into primary database (veloxtrades_db first, then investment_db)"""
        # Try to insert into veloxtrades_db first
        if len(self.collections) > 0 and self.collections[0] is not None:
            try:
                return self.collections[0].insert_one(document, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error inserting into primary {self.name}: {e}")
        
        # If primary fails, try secondary
        if len(self.collections) > 1 and self.collections[1] is not None:
            try:
                return self.collections[1].insert_one(document, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error inserting into secondary {self.name}: {e}")
        
        # If all fail, try any available
        for collection in self.collections:
            try:
                return collection.insert_one(document, *args, **kwargs)
            except Exception as e:
                continue
        
        raise Exception(f"Failed to insert into any {self.name} collection")
    
    def update_one(self, filter, update, *args, **kwargs):
        """Update across all databases"""
        updated_count = 0
        for collection in self.collections:
            try:
                result = collection.update_one(filter, update, *args, **kwargs)
                if result.modified_count > 0:
                    updated_count += result.modified_count
            except Exception as e:
                logger.error(f"Error updating {self.name}: {e}")
        return updated_count > 0
    
    def update_many(self, filter, update, *args, **kwargs):
        """Update many across all databases"""
        total_modified = 0
        for collection in self.collections:
            try:
                result = collection.update_many(filter, update, *args, **kwargs)
                total_modified += result.modified_count
            except Exception as e:
                logger.error(f"Error updating many in {self.name}: {e}")
        return total_modified
    
    def delete_one(self, filter, *args, **kwargs):
        """Delete one across all databases"""
        deleted_count = 0
        for collection in self.collections:
            try:
                result = collection.delete_one(filter, *args, **kwargs)
                if result.deleted_count > 0:
                    deleted_count += result.deleted_count
            except Exception as e:
                logger.error(f"Error deleting from {self.name}: {e}")
        return deleted_count > 0
    
    def delete_many(self, filter, *args, **kwargs):
        """Delete many across all databases"""
        total_deleted = 0
        for collection in self.collections:
            try:
                result = collection.delete_many(filter, *args, **kwargs)
                total_deleted += result.deleted_count
            except Exception as e:
                logger.error(f"Error deleting many from {self.name}: {e}")
        return total_deleted
    
    def count_documents(self, filter=None, *args, **kwargs):
        """Count documents across all databases"""
        total = 0
        for collection in self.collections:
            try:
                total += collection.count_documents(filter or {}, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error counting in {self.name}: {e}")
        return total
    
    def distinct(self, key, filter=None, *args, **kwargs):
        """Get distinct values across all databases"""
        all_values = []
        for collection in self.collections:
            try:
                values = collection.distinct(key, filter or {}, *args, **kwargs)
                all_values.extend(values)
            except Exception as e:
                logger.error(f"Error getting distinct in {self.name}: {e}")
        # Remove duplicates while preserving order
        seen = set()
        unique_values = []
        for v in all_values:
            if v not in seen:
                seen.add(v)
                unique_values.append(v)
        return unique_values
    
    def aggregate(self, pipeline, *args, **kwargs):
        """Aggregate across all databases"""
        all_results = []
        for collection in self.collections:
            try:
                results = list(collection.aggregate(pipeline, *args, **kwargs))
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Error aggregating in {self.name}: {e}")
        return all_results
    
    def create_index(self, keys, *args, **kwargs):
        """Create index in all databases"""
        for collection in self.collections:
            try:
                collection.create_index(keys, *args, **kwargs)
            except Exception as e:
                logger.error(f"Error creating index in {self.name}: {e}")


# Initialize database connection
db_connected = connect_to_databases()

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
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import os

app = Flask(__name__)

# ==================== CORS CONFIGURATION ====================
# Add all your domains here
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

# Configure CORS properly
CORS(app, 
     origins=ALLOWED_ORIGINS,
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken", "Origin"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
     max_age=86400)

# Add this before any routes
@app.before_request
def handle_preflight():
    """Handle CORS preflight requests"""
    if request.method == "OPTIONS":
        response = make_response()
        origin = request.headers.get('Origin', '')
        
        # Check if origin is allowed
        if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
            response.headers.add("Access-Control-Allow-Origin", origin)
        else:
            response.headers.add("Access-Control-Allow-Origin", "https://www.veloxtrades.com.ng")
            
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, PATCH')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        response.headers.add('Access-Control-Max-Age', '86400')
        return response
@app.after_request
def add_cors_headers(response):
    """Add CORS headers to every response"""
    origin = request.headers.get('Origin', '')
    
    # Check if origin is allowed
    if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
    
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS, PATCH'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization, X-Total-Count'
    response.headers['Access-Control-Max-Age'] = '86400'
    
    return response
# ==================== EMAIL CONFIGURATION WITH VALIDATION ====================
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USER = os.getenv('EMAIL_USER', '')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'Veloxtrades')

# Email configuration status
EMAIL_CONFIGURED = bool(EMAIL_USER and EMAIL_PASSWORD and EMAIL_HOST)

def check_email_configuration():
    """Check if email is properly configured"""
    if not EMAIL_CONFIGURED:
        return False, "Email credentials not configured. Please set EMAIL_USER and EMAIL_PASSWORD in environment variables."
    
    try:
        # Test connection
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
        return True, "Email configuration is valid"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"SMTP Authentication failed: {str(e)}"
    except smtplib.SMTPException as e:
        return False, f"SMTP connection error: {str(e)}"
    except Exception as e:
        return False, f"Email configuration error: {str(e)}"

def send_email(to_email, subject, body, html_body=None, max_retries=3):
    """Send email with logging and retry logic"""
    
    # Check email configuration
    if not EMAIL_CONFIGURED:
        error_msg = "Email not configured. Missing EMAIL_USER or EMAIL_PASSWORD"
        logger.error(f"❌ {error_msg}")
        
        # Log to database if available
        if email_logs_collection is not None:
            try:
                email_logs_collection.insert_one({
                    'to': to_email,
                    'subject': subject,
                    'status': 'failed',
                    'error': error_msg,
                    'created_at': datetime.now(timezone.utc)
                })
            except Exception as log_error:
                logger.error(f"Failed to log email error: {log_error}")
        
        return False
    
    # Validate email format
    if not to_email or not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', to_email):
        error_msg = f"Invalid email format: {to_email}"
        logger.error(f"❌ {error_msg}")
        return False
    
    for attempt in range(max_retries):
        try:
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
            
            # Log successful email
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
            error_msg = f"SMTP Authentication Error: {e}"
            logger.error(f"❌ {error_msg}")
            if email_logs_collection is not None:
                try:
                    email_logs_collection.insert_one({
                        'to': to_email,
                        'subject': subject,
                        'status': 'failed',
                        'error': error_msg,
                        'created_at': datetime.now(timezone.utc)
                    })
                except Exception:
                    pass
            return False
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP Error (attempt {attempt+1}): {e}"
            logger.error(f"❌ {error_msg}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                if email_logs_collection is not None:
                    try:
                        email_logs_collection.insert_one({
                            'to': to_email,
                            'subject': subject,
                            'status': 'failed',
                            'error': error_msg,
                            'created_at': datetime.now(timezone.utc)
                        })
                    except Exception:
                        pass
                return False
                
        except Exception as e:
            error_msg = f"Email error (attempt {attempt+1}): {e}"
            logger.error(f"❌ {error_msg}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                if email_logs_collection is not None:
                    try:
                        email_logs_collection.insert_one({
                            'to': to_email,
                            'subject': subject,
                            'status': 'failed',
                            'error': error_msg,
                            'created_at': datetime.now(timezone.utc)
                        })
                    except Exception:
                        pass
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

# ==================== EMAIL SENDING FUNCTIONS ====================
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
        logger.info("🔄 Processing investment profits across both databases...")
        cursor = investments_collection.find({
            'status': 'active',
            'end_date': {'$lte': datetime.now(timezone.utc)}
        })
        
        processed_count = 0
        for investment in cursor:
            try:
                user_id = investment['user_id']
                user = users_collection.find_one({'_id': ObjectId(user_id)})
                if not user:
                    logger.warning(f"User {user_id} not found for investment {investment.get('_id')}")
                    continue
                    
                amount = investment['amount']
                expected_profit = investment.get('expected_profit', 0)
                plan_name = investment.get('plan_name', 'Investment')
                
                result = users_collection.update_one(
                    {'_id': ObjectId(user_id)},
                    {'$inc': {'wallet.balance': expected_profit, 'wallet.total_profit': expected_profit}}
                )
                
                if result:
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
                    
                    try:
                        send_investment_completed_email(user, amount, plan_name, expected_profit)
                    except Exception as e:
                        logger.error(f"Failed to send investment completion email: {e}")
                    
                    processed_count += 1
            except Exception as e:
                logger.error(f"Error processing investment: {e}")
        
        logger.info(f"✅ Processed {processed_count} investments across both databases")
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
        
        # Check across both databases for existing email/username
        existing_email = users_collection.find_one({'email': email})
        if existing_email:
            return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
        existing_username = users_collection.find_one({'username': username})
        if existing_username:
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
        
        # Add to referrer's referrals list (search across both databases)
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
    # Handle OPTIONS preflight request
    if request.method == "OPTIONS":
        response = make_response()
        return add_cors_headers(response)
    
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
            'id': str(user['_id']), 
            'username': user['username'], 
            'full_name': user.get('full_name', ''),
            'email': user['email'], 
            'balance': user.get('wallet', {}).get('balance', 0.00),
            'is_admin': user.get('is_admin', False), 
            'kyc_status': user.get('kyc_status', 'pending')
        }

        response = make_response(jsonify({
            'success': True, 
            'message': 'Login successful!', 
            'data': {'token': token, 'user': user_data}
        }))
        
        # Set cookie
        response.set_cookie('veloxtrades_token', 
                           value=token, 
                           httponly=True, 
                           secure=True, 
                           samesite='None',  # Important for cross-origin
                           max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, 
                           path='/',
                           domain='.veloxtrades.com.ng')  # Allow subdomains
        
        # Add CORS headers
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        response = jsonify({'success': False, 'message': 'Login failed'}), 500
        return add_cors_headers(response)

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
        wallet = user.get('wallet', {})
        if not isinstance(wallet, dict):
            wallet = {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0}
        
        active_investments = []
        if investments_collection is not None:
            active_investments = list(investments_collection.find({'user_id': str(user['_id']), 'status': 'active'}))
        
        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)
        
        recent_transactions = []
        if transactions_collection is not None:
            recent_transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).limit(10))
        
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
        
        unread_count = 0
        if notifications_collection is not None:
            unread_count = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
        
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
        
        if result:
            response = jsonify({'success': True, 'message': 'Notification marked as read'})
        else:
            response = jsonify({'success': False, 'message': 'Notification not found'}), 404
        
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Mark notification read error: {e}")
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
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message are required'}), 400
        
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
            return jsonify({'success': False, 'message': 'Please provide all required KYC information'}), 400
        
        existing = kyc_collection.find_one({'user_id': str(user['_id'])})
        if existing:
            status = existing.get('status', 'pending')
            if status == 'pending':
                return jsonify({'success': False, 'message': 'You already have a pending KYC application'}), 400
            elif status == 'approved':
                return jsonify({'success': False, 'message': 'Your KYC is already verified'}), 400
        
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
        
        users_collection.update_one(
            {'_id': user['_id']},
            {'$set': {'kyc_status': 'pending'}}
        )
        
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

# ==================== REFERRAL FUNCTIONS ====================
def add_referral_commission(user_id, deposit_amount):
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
        
        bonus_percentage = 5
        if settings_collection is not None:
            settings = settings_collection.find_one({})
            if settings:
                bonus_percentage = settings.get('referral_bonus', 5)
        
        commission = deposit_amount * (bonus_percentage / 100)
        
        if commission <= 0:
            return False
        
        result = users_collection.update_one(
            {'_id': referrer['_id']},
            {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}}
        )
        
        if result:
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
        
        if not result:
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

# ==================== ADMIN DEPOSITS ====================
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
            
            try:
                email_sent = send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
                logger.info(f"Deposit approval email sent to {user['email']}: {email_sent}")
            except Exception as e:
                logger.error(f"Failed to send deposit approval email: {e}")
            
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

# ==================== ADMIN RESEND DEPOSIT EMAILS ====================
@app.route('/api/admin/resend-deposit-emails', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_emails():
    """Resend deposit confirmation emails for approved/rejected deposits"""
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
        elif status_filter == 'all':
            query = {'status': {'$in': ['approved', 'rejected']}}
        else:
            query = {'status': 'approved'}
        
        deposits = list(deposits_collection.find(query))
        
        if not deposits:
            return jsonify({
                'success': True,
                'message': 'No deposits found to resend emails',
                'data': {'sent': 0, 'failed': 0, 'errors': []}
            })
        
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
                else:
                    continue
                
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
                'errors': errors[:10]  # Return first 10 errors
            }
        })
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Resend emails error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/deposits/<deposit_id>/resend-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_single_deposit_email(deposit_id):
    """Resend email for a single deposit"""
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

# ==================== ADMIN BROADCAST EMAIL ====================
@app.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
@require_admin
def admin_broadcast_email():
    """Send broadcast email to multiple users"""
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        recipients_type = data.get('recipients', 'all')
        subject = data.get('subject')
        message = data.get('message')
        html_message = data.get('html_message', None)
        
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message are required'}), 400
        
        # Build query based on recipient type
        query = {}
        if recipients_type == 'active':
            query = {'is_banned': False}
        elif recipients_type == 'depositors':
            query = {'wallet.total_deposited': {'$gt': 0}}
        elif recipients_type == 'investors':
            # Users with active investments
            active_investors = investments_collection.distinct('user_id', {'status': 'active'}) if investments_collection else []
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
            return jsonify({'success': True, 'message': 'No users found matching criteria', 'data': {'sent': 0, 'total': 0}})
        
        # Use custom HTML if provided, otherwise create from plain text
        if not html_message:
            html_message = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #10b981, #059669); padding: 20px; text-align: center; color: white;">
                    <h1>Veloxtrades</h1>
                </div>
                <div style="padding: 20px; border: 1px solid #e2e8f0;">
                    <h2>{subject}</h2>
                    <p>{message.replace(chr(10), '<br>')}</p>
                    <hr style="margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">This is an automated message from Veloxtrades. If you have any questions, please contact support.</p>
                </div>
            </div>
            """
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        for user in users:
            try:
                if send_email(user['email'], subject, message, html_message):
                    create_notification(user['_id'], subject, message, 'info')
                    sent_count += 1
                else:
                    failed_count += 1
                    errors.append(f"Failed to send to {user['email']}")
            except Exception as e:
                failed_count += 1
                errors.append(f"Error sending to {user['email']}: {str(e)}")
                logger.error(f"Failed to send broadcast to {user['email']}: {e}")
        
        # Log admin action
        admin_user = get_user_from_request()
        log_admin_action(
            admin_user['_id'], 
            'Broadcast Email', 
            f"Sent to {sent_count}/{len(users)} users. Type: {recipients_type}, Subject: {subject}"
        )
        
        return jsonify({
            'success': True,
            'message': f'Broadcast sent to {sent_count} out of {len(users)} users',
            'data': {
                'sent': sent_count,
                'failed': failed_count,
                'total': len(users),
                'errors': errors[:20]  # Return first 20 errors
            }
        })
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ADMIN EMAIL CONFIGURATION CHECK ====================
@app.route('/api/admin/email-config', methods=['GET', 'OPTIONS'])
@require_admin
def admin_email_config_check():
    """Check email configuration status"""
    is_valid, message = check_email_configuration()
    
    return jsonify({
        'success': True,
        'data': {
            'configured': EMAIL_CONFIGURED,
            'valid': is_valid,
            'message': message,
            'host': EMAIL_HOST,
            'port': EMAIL_PORT,
            'from': EMAIL_FROM,
            'user': EMAIL_USER if EMAIL_USER else 'Not set'
        }
    })

# ==================== ADMIN WITHDRAWALS ====================
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

# ==================== ADMIN INVESTMENTS ====================
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
        
        if result:
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

# ==================== ADMIN TRANSACTIONS ====================
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

# ==================== ADMIN REFERRAL STATS ====================
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

# ==================== ADMIN SEND EMAIL ====================
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

# ==================== ADMIN CREATE TRANSACTION ====================
@app.route('/api/admin/create-transaction', methods=['POST', 'OPTIONS'])
@require_admin
def admin_create_transaction():
    if users_collection is None or transactions_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400
        
        user_id = data.get('user_id')
        transaction_type = data.get('type', 'adjustment')
        amount = data.get('amount')
        description = data.get('description', 'Manual transaction')
        add_to_balance = data.get('add_to_balance', True)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'User ID is required'}), 400
        
        if amount is None:
            return jsonify({'success': False, 'message': 'Amount is required'}), 400
        
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Amount must be a number'}), 400
        
        if amount <= 0:
            return jsonify({'success': False, 'message': 'Amount must be greater than 0'}), 400
        
        try:
            user = users_collection.find_one({'_id': ObjectId(user_id)})
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid user ID format'}), 400
        
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
            
            if update_result:
                create_notification(user_id, f'{transaction_type.capitalize()} Added! 🎉', 
                    f'${amount:,.2f} has been added to your account. Reason: {description}', 'success')
                
                new_balance = user.get('wallet', {}).get('balance', 0) + amount
                
                return jsonify({
                    'success': True,
                    'message': f'Transaction created and ${amount:,.2f} added to user balance',
                    'data': {
                        'transaction_id': str(result.inserted_id),
                        'new_balance': new_balance
                    }
                })
            else:
                return jsonify({'success': False, 'message': 'Failed to update user balance'}), 500
        else:
            return jsonify({
                'success': True,
                'message': 'Transaction created (balance not updated)',
                'data': {'transaction_id': str(result.inserted_id)}
            })
            
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# ==================== ADMIN KYC ====================
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
        applications = list(kyc_collection.find(query).sort('submitted_at', -1).skip(skip).limit(limit))
        
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
        
        if users_collection and kyc.get('user_id'):
            user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
            if user:
                kyc['user_details'] = {
                    '_id': str(user['_id']),
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'full_name': user.get('full_name', ''),
                    'phone': user.get('phone', ''),
                    'wallet_balance': user.get('wallet', {}).get('balance', 0)
                }
        
        response = jsonify({'success': True, 'data': kyc})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get KYC application error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/kyc/<kyc_id>/approve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_approve_kyc(kyc_id):
    if kyc_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC application not found'}), 404
        
        if kyc['status'] != 'pending':
            return jsonify({'success': False, 'message': f'This application has already been {kyc["status"]}'}), 400
        
        admin_user = get_user_from_request()
        
        kyc_collection.update_one(
            {'_id': ObjectId(kyc_id)},
            {
                '$set': {
                    'status': 'approved',
                    'reviewed_at': datetime.now(timezone.utc),
                    'reviewed_by': str(admin_user['_id']),
                    'reviewer_username': admin_user.get('username', 'Admin')
                }
            }
        )
        
        users_collection.update_one(
            {'_id': ObjectId(kyc['user_id'])},
            {'$set': {'kyc_status': 'verified', 'is_verified': True}}
        )
        
        create_notification(
            kyc['user_id'],
            'KYC Approved! ✅',
            'Congratulations! Your KYC verification has been approved.',
            'success'
        )
        
        user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
        if user:
            send_email(user['email'], 'KYC Verification Approved', f'Dear {user.get("username")},\n\nYour KYC has been approved.\n\nBest regards,\nVeloxtrades Team')
        
        log_admin_action(admin_user['_id'], 'KYC Approved', f'Approved KYC for user {kyc["username"]}')
        
        response = jsonify({'success': True, 'message': 'KYC application approved successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin approve KYC error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/kyc/<kyc_id>/reject', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reject_kyc(kyc_id):
    if kyc_collection is None or users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        data = request.get_json()
        reason = data.get('reason', '').strip()
        
        if not reason:
            return jsonify({'success': False, 'message': 'Rejection reason is required'}), 400
        
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)})
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC application not found'}), 404
        
        if kyc['status'] != 'pending':
            return jsonify({'success': False, 'message': f'This application has already been {kyc["status"]}'}), 400
        
        admin_user = get_user_from_request()
        
        kyc_collection.update_one(
            {'_id': ObjectId(kyc_id)},
            {
                '$set': {
                    'status': 'rejected',
                    'reviewed_at': datetime.now(timezone.utc),
                    'reviewed_by': str(admin_user['_id']),
                    'reviewer_username': admin_user.get('username', 'Admin'),
                    'rejection_reason': reason
                }
            }
        )
        
        users_collection.update_one(
            {'_id': ObjectId(kyc['user_id'])},
            {'$set': {'kyc_status': 'rejected'}}
        )
        
        create_notification(
            kyc['user_id'],
            'KYC Rejected ❌',
            f'Your KYC verification was rejected. Reason: {reason}',
            'error'
        )
        
        user = users_collection.find_one({'_id': ObjectId(kyc['user_id'])})
        if user:
            send_email(user['email'], 'KYC Verification Rejected', f'Dear {user.get("username")},\n\nYour KYC was rejected.\nReason: {reason}\n\nPlease submit new documents.\n\nBest regards,\nVeloxtrades Team')
        
        log_admin_action(admin_user['_id'], 'KYC Rejected', f'Rejected KYC for user {kyc["username"]}. Reason: {reason}')
        
        response = jsonify({'success': True, 'message': 'KYC application rejected successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin reject KYC error: {e}")
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

# ==================== ADMIN SUPPORT TICKETS ====================
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
        tickets = list(support_tickets_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        
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
        
        for msg in ticket.get('messages', []):
            if msg.get('created_at'):
                msg['created_at'] = msg['created_at'].isoformat()
        
        if users_collection and ticket.get('user_id'):
            user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
            if user:
                ticket['user_details'] = {
                    'username': user.get('username', ''),
                    'email': user.get('email', ''),
                    'wallet_balance': user.get('wallet', {}).get('balance', 0)
                }
        
        response = jsonify({'success': True, 'data': ticket})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin get ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
@require_admin
def admin_reply_ticket(ticket_id):
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
                    'status': 'pending'
                }
            }
        )
        
        user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
        if user:
            send_email(user['email'], f'New Reply to Ticket #{ticket_id}', f'Admin replied: {message}')
            create_notification(ticket['user_id'], f'Ticket Updated: {ticket_id}', 'Admin has replied to your ticket.', 'info')
        
        log_admin_action(admin_user['_id'], 'Ticket Reply', f'Replied to ticket {ticket_id}')
        
        response = jsonify({'success': True, 'message': 'Reply sent successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/support/tickets/<ticket_id>/resolve', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resolve_ticket(ticket_id):
    if support_tickets_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
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
                    'resolved_by': str(admin_user['_id'])
                }
            }
        )
        
        user = users_collection.find_one({'_id': ObjectId(ticket['user_id'])})
        if user:
            create_notification(ticket['user_id'], f'Ticket Resolved: {ticket_id}', 'Your ticket has been resolved.', 'success')
        
        log_admin_action(admin_user['_id'], 'Ticket Resolved', f'Resolved ticket {ticket_id}')
        
        response = jsonify({'success': True, 'message': 'Ticket resolved successfully'})
        return add_cors_headers(response)
        
    except Exception as e:
        logger.error(f"Admin resolve ticket error: {e}")
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

# ==================== ADMIN RESET ====================
@app.route('/api/admin/reset-all', methods=['GET', 'POST', 'OPTIONS'])
def reset_all_admin():
    """Create admin account - supports both GET and POST"""
    # Check authorization
    secret_key = request.args.get('secret') or request.headers.get('X-Admin-Secret')
    
    if not secret_key or secret_key != ADMIN_RESET_SECRET:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    if users_collection is None:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    
    try:
        # Delete existing admins from both databases
        users_collection.delete_many({'is_admin': True})
        users_collection.delete_many({'username': 'admin'})
        
        logger.info(f"Deleted existing admin users")
        
        # Hash password
        hashed_password = hash_password('admin123')
        
        # Create new admin
        new_admin = {
            'full_name': 'System Administrator',
            'email': 'admin@veloxtrades.ltd',
            'username': 'admin',
            'password': hashed_password,
            'phone': '+1234567890',
            'country': 'USA',
            'wallet': {
                'balance': 100000.00,
                'total_deposited': 100000.00,
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
            'referral_code': 'ADMIN2025',
            'referrals': [],
            'kyc_status': 'verified'
        }
        
        result = users_collection.insert_one(new_admin)
        
        logger.info(f"✅ Admin created with ID: {result.inserted_id}")
        
        return jsonify({
            'success': True,
            'message': '✅ Admin account created!',
            'credentials': {
                'username': 'admin',
                'password': 'admin123'
            },
            'admin_id': str(result.inserted_id)
        })
        
    except Exception as e:
        logger.error(f"Reset admin error: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)}), 500

# ==================== HEALTH CHECK ====================
@app.route('/health', methods=['GET', 'OPTIONS'])
def health_check():
    mongo_status = 'connected' if users_collection is not None else 'disconnected'
    email_status = 'configured' if EMAIL_CONFIGURED else 'not configured'
    
    # Check email validity if configured
    email_valid = None
    if EMAIL_CONFIGURED:
        is_valid, _ = check_email_configuration()
        email_valid = is_valid
    
    response = jsonify({
        'success': True, 
        'status': 'healthy', 
        'mongo': mongo_status,
        'databases': {
            'veloxtrades_db': 'connected' if veloxtrades_db is not None else 'disconnected',
            'investment_db': 'connected' if investment_db is not None else 'disconnected'
        },
        'email': {
            'configured': EMAIL_CONFIGURED,
            'valid': email_valid if EMAIL_CONFIGURED else None
        },
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    return add_cors_headers(response)

@app.route('/api/health', methods=['GET', 'OPTIONS'])
def api_health_check():
    return health_check()

# ==================== DATABASE STATUS ENDPOINT ====================
@app.route('/api/database-status', methods=['GET', 'OPTIONS'])
def database_status():
    """Check both database connections"""
    return jsonify({
        'success': True,
        'data': {
            'veloxtrades_db': {
                'connected': veloxtrades_db is not None,
                'collections': {
                    'users': veloxtrades_users is not None,
                    'transactions': veloxtrades_transactions is not None,
                    'notifications': veloxtrades_notifications is not None,
                    'kyc': veloxtrades_kyc is not None,
                    'support_tickets': veloxtrades_support_tickets is not None,
                    'admin_logs': veloxtrades_admin_logs is not None,
                    'settings': veloxtrades_settings is not None,
                    'email_logs': veloxtrades_email_logs is not None,
                    'investments': veloxtrades_investments is not None,
                    'deposits': veloxtrades_deposits is not None,
                    'withdrawals': veloxtrades_withdrawals is not None,
                    'referral_stats': veloxtrades_referral_stats is not None
                }
            },
            'investment_db': {
                'connected': investment_db is not None,
                'collections': {
                    'users': investment_users is not None,
                    'transactions': investment_transactions is not None,
                    'notifications': investment_notifications is not None,
                    'kyc': investment_kyc is not None,
                    'support_tickets': investment_support_tickets is not None,
                    'admin_logs': investment_admin_logs is not None,
                    'settings': investment_settings is not None,
                    'email_logs': investment_email_logs is not None,
                    'investments': investment_investments is not None,
                    'deposits': investment_deposits is not None,
                    'withdrawals': investment_withdrawals is not None,
                    'referral_stats': investment_referral_stats is not None
                }
            }
        }
    })

# ==================== FRONTEND ROUTES ====================
@app.route('/')
def serve_index():
    response = jsonify({
        'success': True, 
        'message': 'Veloxtrades API Server (Dual Database Mode - Both Databases Searchable)',
        'frontend': FRONTEND_URL,
        'databases': {
            'veloxtrades_db': 'connected' if veloxtrades_db is not None else 'disconnected',
            'investment_db': 'connected' if investment_db is not None else 'disconnected'
        },
        'search_mode': 'BOTH DATABASES - All collections exist in both databases',
        'collections_in_each_db': [
            'users', 'transactions', 'notifications', 'kyc', 'support_tickets',
            'admin_logs', 'settings', 'email_logs', 'investments',
            'deposits', 'withdrawals', 'referral_stats'
        ],
        'email_configured': EMAIL_CONFIGURED,
        'endpoints': ['/health', '/api/health', '/api/database-status', '/api/register', '/api/login', '/api/verify-token']
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
# At the very end of your file, replace the entire if __name__ == '__main__': block with:

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 VELOXTRADES API SERVER - DUAL DATABASE MODE")
    print("=" * 70)
    
    if db_connected:
        print("📊 DATABASE STATUS:")
        print(f"   ✅ veloxtrades_db: {'Connected' if veloxtrades_db is not None else 'Disconnected'}")
        print(f"   ✅ investment_db: {'Connected' if investment_db is not None else 'Disconnected'}")
        
        print("\n📂 COLLECTIONS IN BOTH DATABASES:")
        print("   Both databases contain ALL collections:")
        print("      - users, transactions, notifications, kyc, support_tickets")
        print("      - admin_logs, settings, email_logs, investments")
        print("      - deposits, withdrawals, referral_stats")
        print("\n🔍 SEARCH MODE: Searching across BOTH databases for ALL operations")
    else:
        print("❌ MongoDB Connection Failed!")
        print("⚠️ Server will still start but database operations will fail!")
    
    # Check email configuration
    if EMAIL_CONFIGURED:
        is_valid, msg = check_email_configuration()
        if is_valid:
            print(f"\n📧 Email Service: Configured and VALID")
        else:
            print(f"\n⚠️ Email Service: Configured but INVALID - {msg}")
    else:
        print(f"\n⚠️ Email Service: NOT CONFIGURED - Missing EMAIL_USER or EMAIL_PASSWORD")
    
    print("\n👑 Admin Dashboard Ready")
    print("=" * 70)
    print("📝 TO CREATE ADMIN:")
    print(f"   GET or POST {BACKEND_URL}/api/admin/reset-all?secret={ADMIN_RESET_SECRET}")
    print("   Then login with: admin / admin123")
    print("=" * 70)
    print("📧 EMAIL ENDPOINTS:")
    print(f"   GET  /api/admin/email-config - Check email configuration status")
    print(f"   POST /api/admin/broadcast - Send broadcast emails to users")
    print(f"   POST /api/admin/send-email - Send single email to user")
    print(f"   POST /api/admin/resend-deposit-emails - Resend all deposit emails")
    print(f"   POST /api/admin/deposits/<id>/resend-email - Resend single deposit email")
    print("=" * 70)
    print("🗄️ DATABASE ENDPOINTS:")
    print(f"   GET  /api/database-status - Check both database connections and collections")
    print(f"   GET  /health - Health check with database status")
    print("=" * 70)
    print("🔍 SEARCH BEHAVIOR:")
    print("   ✓ Users: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Transactions: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Investments: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Deposits: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Withdrawals: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Notifications: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ KYC: Searched in BOTH veloxtrades_db AND investment_db")
    print("   ✓ Support Tickets: Searched in BOTH veloxtrades_db AND investment_db")
    print("=" * 70)
    print("🌐 SERVER CONFIGURATION:")
    
    # Get port from environment variable (Render sets this)
    port = int(os.getenv('PORT', '10000'))  # Changed default to 10000 for Render
    host = os.getenv('HOST', '0.0.0.0')
    
    print(f"   Host: {host}")
    print(f"   Port: {port}")
    print(f"   Environment: {os.getenv('FLASK_ENV', 'production')}")
    print("=" * 70)
    print(f"✅ Server will bind to {host}:{port}")
    print("=" * 70)
    
    # Run the app
    try:
        app.run(host=host, port=port, debug=False, threaded=True)
    except Exception as e:
        print(f"\n❌ SERVER FAILED TO START: {e}")
        import traceback
        traceback.print_exc()
    
   
