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


class DualDatabaseCollection:
    def __init__(self, collections, name):
        self.collections = [c for c in collections if c is not None]
        self.name = name

    def find(self, query=None, *args, **kwargs):
        results = []
        for collection in self.collections:
            try:
                results.extend(list(collection.find(query or {}, *args, **kwargs)))
            except Exception as e:
                logger.error(f"Error searching {self.name}: {e}")
        return results

    def find_one(self, query=None, *args, **kwargs):
        for collection in self.collections:
            try:
                result = collection.find_one(query or {}, *args, **kwargs)
                if result:
                    return result
            except Exception:
                continue
        return None

    def insert_one(self, document, *args, **kwargs):
        for collection in self.collections:
            try:
                return collection.insert_one(document, *args, **kwargs)
            except Exception:
                continue
        raise Exception(f"Failed to insert into any {self.name} collection")

    def update_one(self, filter, update, *args, **kwargs):
        updated = False
        for collection in self.collections:
            try:
                if collection.update_one(filter, update, *args, **kwargs).modified_count > 0:
                    updated = True
            except Exception as e:
                logger.error(f"Error updating {self.name}: {e}")
        return updated

    def update_many(self, filter, update, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                total += collection.update_many(filter, update, *args, **kwargs).modified_count
            except Exception as e:
                logger.error(f"Error updating many {self.name}: {e}")
        return total

    def delete_one(self, filter, *args, **kwargs):
        deleted = False
        for collection in self.collections:
            try:
                if collection.delete_one(filter, *args, **kwargs).deleted_count > 0:
                    deleted = True
            except Exception as e:
                logger.error(f"Error deleting from {self.name}: {e}")
        return deleted

    def delete_many(self, filter, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                total += collection.delete_many(filter, *args, **kwargs).deleted_count
            except Exception as e:
                logger.error(f"Error deleting many from {self.name}: {e}")
        return total

    def count_documents(self, filter=None, *args, **kwargs):
        total = 0
        for collection in self.collections:
            try:
                total += collection.count_documents(filter or {}, *args, **kwargs)
            except Exception:
                continue
        return total

    def distinct(self, key, filter=None, *args, **kwargs):
        all_values = []
        for collection in self.collections:
            try:
                all_values.extend(collection.distinct(key, filter or {}, *args, **kwargs))
            except Exception:
                continue
        return list(dict.fromkeys(all_values))

    def aggregate(self, pipeline, *args, **kwargs):
        all_results = []
        for collection in self.collections:
            try:
                all_results.extend(list(collection.aggregate(pipeline, *args, **kwargs)))
            except Exception as e:
                logger.error(f"Error aggregating in {self.name}: {e}")
        return all_results

    def create_index(self, keys, *args, **kwargs):
        for collection in self.collections:
            try:
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

        # Create combined collections
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
    "http://localhost:5000", "http://127.0.0.1:5000", "http://localhost:3000", "http://localhost:5500",
    "https://frontend-ugb2.onrender.com", "https://elite-eky6.onrender.com",
    "https://veloxtrades.com.ng", "https://www.veloxtrades.com.ng",
    "https://velox-wnn4.onrender.com", "https://investment-gto3.onrender.com"
]

CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True,
     allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With", "X-CSRFToken", "Origin"],
     expose_headers=["Content-Type", "Authorization", "X-Total-Count"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"], max_age=86400)


@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = make_response()
        origin = request.headers.get('Origin', '')
        if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
            response.headers.add("Access-Control-Allow-Origin", origin)
        else:
            response.headers.add("Access-Control-Allow-Origin", "https://www.veloxtrades.com.ng")
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization, Accept, X-Requested-With, X-CSRFToken, Origin')
        response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS, PATCH')
        response.headers.add('Access-Control-Allow-Credentials', 'true')
        return response


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if origin in ALLOWED_ORIGINS or 'veloxtrades.com.ng' in origin or 'onrender.com' in origin:
        response.headers['Access-Control-Allow-Origin'] = origin
    else:
        response.headers['Access-Control-Allow-Origin'] = 'https://www.veloxtrades.com.ng'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response


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


# ==================== HELPER FUNCTIONS ====================
def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(hashed_password, password):
    try:
        if not hashed_password:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False


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
        if users_collection:
            user = users_collection.find_one({'_id': ObjectId(user_id)})
            if user:
                return user
        if veloxtrades_users:
            user = veloxtrades_users.find_one({'_id': ObjectId(user_id)})
            if user:
                return user
        if investment_users:
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
    if veloxtrades_notifications:
        try:
            veloxtrades_notifications.insert_one(notification_data)
        except Exception as e:
            logger.error(f"Failed to create notification in veloxtrades_db: {e}")
    if investment_notifications:
        try:
            investment_notifications.insert_one(notification_data)
        except Exception as e:
            logger.error(f"Failed to create notification in investment_db: {e}")


def log_admin_action(admin_id, action, details):
    log_data = {
        'admin_id': str(admin_id), 'action': action, 'details': details,
        'ip_address': request.remote_addr, 'created_at': datetime.now(timezone.utc)
    }
    if veloxtrades_admin_logs:
        try:
            veloxtrades_admin_logs.insert_one(log_data)
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")
    if investment_admin_logs:
        try:
            investment_admin_logs.insert_one(log_data)
        except Exception as e:
            logger.error(f"Failed to log admin action: {e}")


def add_referral_commission(user_id, deposit_amount):
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
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': referrer['_id']}, {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}})
        if investment_users:
            investment_users.update_one({'_id': referrer['_id']}, {'$inc': {'wallet.balance': commission, 'wallet.total_profit': commission}})
        if transactions_collection:
            transactions_collection.insert_one({
                'user_id': str(referrer['_id']), 'type': 'commission', 'amount': commission, 'status': 'completed',
                'description': f'Commission from {user["username"]}\'s deposit of ${deposit_amount:,.2f}',
                'created_at': datetime.now(timezone.utc)
            })
        create_notification(referrer['_id'], 'Referral Commission! 🎉', f'Earned ${commission:,.2f} from {user["username"]}\'s deposit!', 'success')
        return True
    except Exception as e:
        logger.error(f"Error adding referral commission: {e}")
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
        plain_body = f"Dear {user_name},\n\nYour deposit of ${amount:,.2f} has been APPROVED!\n\nAmount: ${amount:,.2f}\nMethod: {crypto.upper()}\n\nThank you!"
        content = f'<p>Dear {user_name},</p><div style="background:#d1fae5;padding:15px;"><p><strong>✅ DEPOSIT APPROVED!</strong></p><p>Amount: ${amount:,.2f}</p></div>'
        html_body = get_email_template(subject, content, 'Go to Dashboard', f'{FRONTEND_URL}/dashboard.html')
        return send_email(user['email'], subject, plain_body, html_body)
    except Exception as e:
        logger.error(f"Error in send_deposit_approved_email: {e}")
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
    'standard': {'name': 'Standard Plan', 'roi': 8, 'duration_hours': 20, 'min_deposit': 50, 'max_deposit': 999},
    'advanced': {'name': 'Advanced Plan', 'roi': 18, 'duration_hours': 48, 'min_deposit': 1000, 'max_deposit': 5000},
    'professional': {'name': 'Professional Plan', 'roi': 35, 'duration_hours': 96, 'min_deposit': 5001, 'max_deposit': 10000},
    'classic': {'name': 'Classic Plan', 'roi': 50, 'duration_hours': 144, 'min_deposit': 10001, 'max_deposit': float('inf')}
}


# ==================== AUTO-PROFIT SCHEDULER ====================
def process_investment_profits():
    if not investments_collection:
        return
    try:
        logger.info("🔄 Processing investment profits...")
        cursor = investments_collection.find({'status': 'active', 'end_date': {'$lte': datetime.now(timezone.utc)}})
        processed = 0
        for inv in cursor:
            try:
                user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
                if not user:
                    continue
                profit = inv.get('expected_profit', 0)
                users_collection.update_one({'_id': ObjectId(inv['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
                investments_collection.update_one({'_id': inv['_id']}, {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}})
                if transactions_collection:
                    transactions_collection.insert_one({'user_id': inv['user_id'], 'type': 'profit', 'amount': profit, 'status': 'completed', 'created_at': datetime.now(timezone.utc)})
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
    if not users_collection and not veloxtrades_users and not investment_users:
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
        existing = None
        if users_collection:
            existing = users_collection.find_one({'$or': [{'email': email}, {'username': username}]})
        if not existing and veloxtrades_users:
            existing = veloxtrades_users.find_one({'$or': [{'email': email}, {'username': username}]})
        if not existing and investment_users:
            existing = investment_users.find_one({'$or': [{'email': email}, {'username': username}]})
        if existing:
            if existing.get('email') == email:
                return jsonify({'success': False, 'message': 'Email already registered'}), 400
            return jsonify({'success': False, 'message': 'Username already taken'}), 400
        referred_by = None
        referrer = None
        if referral_code_input:
            if users_collection:
                referrer = users_collection.find_one({'referral_code': referral_code_input})
            if not referrer and veloxtrades_users:
                referrer = veloxtrades_users.find_one({'referral_code': referral_code_input})
            if not referrer and investment_users:
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
        if veloxtrades_users:
            result = veloxtrades_users.insert_one(user_data)
            user_id = result.inserted_id
        if investment_users:
            investment_users.insert_one(user_data)
        if referrer:
            if veloxtrades_users:
                veloxtrades_users.update_one({'_id': referrer['_id']}, {'$push': {'referrals': username}})
            if investment_users:
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
        if users_collection:
            referrer = users_collection.find_one({'referral_code': referral_code})
        if not referrer and veloxtrades_users:
            referrer = veloxtrades_users.find_one({'referral_code': referral_code})
        if not referrer and investment_users:
            referrer = investment_users.find_one({'referral_code': referral_code})
        if referrer:
            return jsonify({'success': True, 'valid': True, 'message': 'Valid referral code!', 'referrer': referrer.get('username', 'User')})
        else:
            return jsonify({'success': True, 'valid': False, 'message': 'Invalid referral code'})
    except Exception as e:
        logger.error(f"Verify referral error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == "OPTIONS":
        return add_cors_headers(make_response())
    if not users_collection and not veloxtrades_users and not investment_users:
        return jsonify({'success': False, 'message': 'Database connection error'}), 500
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'No credentials provided'}), 400
        username_or_email = data.get('username', '').strip().lower()
        password = data.get('password', '')
        if not username_or_email or not password:
            return jsonify({'success': False, 'message': 'Username and password required'}), 400
        user = None
        if users_collection:
            user = users_collection.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
        if not user and veloxtrades_users:
            user = veloxtrades_users.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
        if not user and investment_users:
            user = investment_users.find_one({'$or': [{'email': username_or_email}, {'username': username_or_email}]})
        if not user or not verify_password(user.get('password', ''), password):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
        if user.get('is_banned', False):
            return jsonify({'success': False, 'message': 'Account suspended'}), 403
        token = create_jwt_token(user['_id'], user['username'], user.get('is_admin', False))
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})
        if investment_users:
            investment_users.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.now(timezone.utc)}})
        wallet = user.get('wallet', {})
        user_data = {
            'id': str(user['_id']), 'username': user.get('username', ''), 'full_name': user.get('full_name', ''),
            'email': user.get('email', ''), 'balance': wallet.get('balance', 0.00),
            'is_admin': user.get('is_admin', False), 'kyc_status': user.get('kyc_status', 'pending')
        }
        response = make_response(jsonify({'success': True, 'message': 'Login successful!', 'data': {'token': token, 'user': user_data}}))
        response.set_cookie('veloxtrades_token', value=token, httponly=True, secure=True, samesite='None', max_age=app.config['JWT_EXPIRATION_DAYS'] * 24 * 60 * 60, path='/')
        return add_cors_headers(response)
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Login failed'}), 500


@app.route('/api/logout', methods=['POST', 'OPTIONS'])
def logout():
    response = make_response(jsonify({'success': True, 'message': 'Logged out'}))
    response.set_cookie('veloxtrades_token', '', expires=0, path='/')
    return add_cors_headers(response)


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
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        crypto = data.get('crypto', 'usdt')
        transaction_hash = data.get('transaction_hash', '').strip()
        settings = settings_collection.find_one({}) if settings_collection else None
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
        if transactions_collection:
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
        if deposits_collection:
            deposits = list(deposits_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
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
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        currency = data.get('currency', 'usdt')
        wallet_address = data.get('wallet_address', '').strip()
        if not wallet_address:
            return jsonify({'success': False, 'message': 'Wallet address required'}), 400
        settings = settings_collection.find_one({}) if settings_collection else None
        min_withdrawal = settings.get('min_withdrawal', 50) if settings else 50
        max_withdrawal = settings.get('max_withdrawal', 50000) if settings else 50000
        withdrawal_fee = settings.get('withdrawal_fee', 0) if settings else 0
        if amount < min_withdrawal:
            return jsonify({'success': False, 'message': f'Minimum withdrawal is ${min_withdrawal}'}), 400
        if amount > max_withdrawal:
            return jsonify({'success': False, 'message': f'Maximum withdrawal is ${max_withdrawal}'}), 400
        fee_amount = amount * (withdrawal_fee / 100)
        net_amount = amount - fee_amount
        if user['wallet']['balance'] < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        withdrawal_id = 'WIT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=12))
        withdrawal_data = {
            'withdrawal_id': withdrawal_id, 'user_id': str(user['_id']), 'username': user['username'],
            'amount': amount, 'fee': fee_amount, 'net_amount': net_amount, 'currency': currency,
            'wallet_address': wallet_address, 'status': 'pending', 'created_at': datetime.now(timezone.utc)
        }
        withdrawals_collection.insert_one(withdrawal_data)
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount}})
        if investment_users:
            investment_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount}})
        if transactions_collection:
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
        if withdrawals_collection:
            withdrawals = list(withdrawals_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
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
    try:
        data = request.get_json()
        plan_type = data.get('plan') or data.get('plan_type')
        amount = float(data.get('amount', 0))
        plan = INVESTMENT_PLANS.get(plan_type)
        if not plan:
            return jsonify({'success': False, 'message': 'Invalid plan'}), 400
        if amount < plan['min_deposit']:
            return jsonify({'success': False, 'message': f'Minimum investment is ${plan["min_deposit"]}'}), 400
        if amount > plan['max_deposit']:
            return jsonify({'success': False, 'message': f'Maximum investment is ${plan["max_deposit"]}'}), 400
        if user['wallet']['balance'] < amount:
            return jsonify({'success': False, 'message': 'Insufficient balance'}), 400
        expected_profit = amount * plan['roi'] / 100
        end_date = datetime.now(timezone.utc) + timedelta(hours=plan['duration_hours'])
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}})
        if investment_users:
            investment_users.update_one({'_id': user['_id']}, {'$inc': {'wallet.balance': -amount, 'wallet.total_invested': amount}})
        investment_data = {
            'user_id': str(user['_id']), 'username': user['username'], 'plan': plan_type,
            'plan_name': plan['name'], 'amount': amount, 'roi': plan['roi'],
            'expected_profit': expected_profit, 'duration_hours': plan['duration_hours'],
            'start_date': datetime.now(timezone.utc), 'end_date': end_date, 'status': 'active'
        }
        result = investments_collection.insert_one(investment_data)
        if transactions_collection:
            transactions_collection.insert_one({
                'user_id': str(user['_id']), 'type': 'investment', 'amount': amount, 'status': 'completed',
                'description': f'Investment in {plan["name"]}', 'investment_id': str(result.inserted_id),
                'created_at': datetime.now(timezone.utc)
            })
        create_notification(user['_id'], 'Investment Started!', f'Invested ${amount:,.2f} in {plan["name"]}. Expected profit: ${expected_profit:,.2f}', 'success')
        send_investment_confirmation_email(user, amount, plan['name'], plan['roi'], expected_profit)
        return add_cors_headers(jsonify({'success': True, 'message': 'Investment successful', 'data': {'expected_profit': expected_profit, 'end_date': end_date.isoformat()}}))
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
        if investments_collection:
            investments = list(investments_collection.find({'user_id': str(user['_id'])}).sort('start_date', -1))
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if inv.get('start_date'):
                inv['start_date'] = inv['start_date'].isoformat()
            if inv.get('end_date'):
                inv['end_date'] = inv['end_date'].isoformat()
        return add_cors_headers(jsonify({'success': True, 'data': {'investments': investments}}))
    except Exception as e:
        logger.error(f"Get investments error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== TRANSACTION ENDPOINTS ====================
@app.route('/api/transactions', methods=['GET', 'OPTIONS'])
def get_transactions():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        transactions = []
        if transactions_collection:
            transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1))
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if tx.get('created_at'):
                tx['created_at'] = tx['created_at'].isoformat()
        return add_cors_headers(jsonify({'success': True, 'data': {'transactions': transactions}}))
    except Exception as e:
        logger.error(f"Get transactions error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== DASHBOARD ENDPOINTS ====================
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
        if investments_collection:
            active_investments = list(investments_collection.find({'user_id': str(user['_id']), 'status': 'active'}))
        total_active = sum(inv.get('amount', 0) for inv in active_investments)
        pending_profit = sum(inv.get('expected_profit', 0) for inv in active_investments)
        recent_transactions = []
        if transactions_collection:
            recent_transactions = list(transactions_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).limit(10))
        formatted_transactions = []
        for tx in recent_transactions:
            formatted_transactions.append({
                '_id': str(tx['_id']), 'type': tx.get('type', 'unknown'), 'amount': tx.get('amount', 0),
                'status': tx.get('status', 'pending'), 'description': tx.get('description', ''),
                'created_at': tx.get('created_at').isoformat() if tx.get('created_at') else None
            })
        unread_count = 0
        if notifications_collection:
            unread_count = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False})
        pending_deposits = 0
        if deposits_collection:
            pending_deposits = deposits_collection.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
        pending_withdrawals = 0
        if withdrawals_collection:
            pending_withdrawals = withdrawals_collection.count_documents({'user_id': str(user['_id']), 'status': 'pending'})
        dashboard_data = {
            'wallet': {
                'balance': wallet.get('balance', 0), 'total_deposited': wallet.get('total_deposited', 0),
                'total_withdrawn': wallet.get('total_withdrawn', 0), 'total_invested': wallet.get('total_invested', 0),
                'total_profit': wallet.get('total_profit', 0)
            },
            'investments': {
                'total_active': total_active, 'total_profit': wallet.get('total_profit', 0),
                'pending_profit': pending_profit, 'count': len(active_investments)
            },
            'recent_transactions': formatted_transactions,
            'notification_count': unread_count,
            'kyc_status': user.get('kyc_status', 'pending'),
            'pending_requests': {'deposits': pending_deposits, 'withdrawals': pending_withdrawals}
        }
        return add_cors_headers(jsonify({'success': True, 'data': dashboard_data}))
    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        return add_cors_headers(jsonify({'success': True, 'data': {
            'wallet': {'balance': 0, 'total_deposited': 0, 'total_withdrawn': 0, 'total_invested': 0, 'total_profit': 0},
            'investments': {'total_active': 0, 'total_profit': 0, 'pending_profit': 0, 'count': 0},
            'recent_transactions': [], 'notification_count': 0, 'kyc_status': user.get('kyc_status', 'pending'),
            'pending_requests': {'deposits': 0, 'withdrawals': 0}
        }})), 200


@app.route('/api/user/referral-info', methods=['GET', 'OPTIONS'])
def get_user_referral_info():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        referral_code = user.get('referral_code', '')
        referred_users = []
        if users_collection:
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
        settings = settings_collection.find_one({}) if settings_collection else None
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
        if notifications_collection:
            notifications = list(notifications_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).skip(skip).limit(limit))
        for n in notifications:
            n['_id'] = str(n['_id'])
            if n.get('created_at'):
                n['created_at'] = n['created_at'].isoformat()
        total = notifications_collection.count_documents({'user_id': str(user['_id'])}) if notifications_collection else 0
        unread = notifications_collection.count_documents({'user_id': str(user['_id']), 'read': False}) if notifications_collection else 0
        return add_cors_headers(jsonify({'success': True, 'data': {'notifications': notifications, 'total': total, 'unread': unread, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get notifications error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/notifications/<notification_id>/read', methods=['PUT', 'OPTIONS'])
def mark_notification_read(notification_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        if notifications_collection:
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
        if kyc_collection:
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
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': user['_id']}, {'$set': {'kyc_status': 'pending'}})
        if investment_users:
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
        if kyc_collection:
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
        if kyc_collection:
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


# ==================== SUPPORT TICKET ENDPOINTS (USER) ====================
@app.route('/api/support/tickets', methods=['POST', 'OPTIONS'])
def create_ticket():
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        subject = data.get('subject', '').strip()
        message = data.get('message', '').strip()
        category = data.get('category', 'general')
        if not subject or not message:
            return jsonify({'success': False, 'message': 'Subject and message required'}), 400
        ticket_id = 'TKT-' + ''.join(random.choices(string.digits + string.ascii_uppercase, k=10))
        ticket_data = {
            'ticket_id': ticket_id, 'user_id': str(user['_id']), 'username': user['username'],
            'email': user['email'], 'subject': subject, 'message': message, 'category': category,
            'priority': data.get('priority', 'medium'), 'status': 'open',
            'created_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc),
            'messages': [{'sender': 'user', 'sender_name': user['username'], 'message': message, 'created_at': datetime.now(timezone.utc)}]
        }
        support_tickets_collection.insert_one(ticket_data)
        create_notification(user['_id'], f'Ticket Created: {ticket_id}', 'Your ticket has been created. We\'ll respond within 24 hours.', 'info')
        return add_cors_headers(jsonify({'success': True, 'message': 'Ticket created', 'data': {'ticket_id': ticket_id}})), 201
    except Exception as e:
        logger.error(f"Create ticket error: {e}")
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
        if support_tickets_collection:
            tickets = list(support_tickets_collection.find({'user_id': str(user['_id'])}).sort('created_at', -1).skip(skip).limit(limit))
        for t in tickets:
            t['_id'] = str(t['_id'])
            if t.get('created_at'):
                t['created_at'] = t['created_at'].isoformat()
            if t.get('updated_at'):
                t['updated_at'] = t['updated_at'].isoformat()
            t.pop('messages', None)
        total = support_tickets_collection.count_documents({'user_id': str(user['_id'])}) if support_tickets_collection else 0
        return add_cors_headers(jsonify({'success': True, 'data': {'tickets': tickets, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>', methods=['GET', 'OPTIONS'])
def get_ticket(ticket_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        ticket = None
        if support_tickets_collection:
            ticket = support_tickets_collection.find_one({'ticket_id': ticket_id, 'user_id': str(user['_id'])})
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
        return add_cors_headers(jsonify({'success': True, 'data': ticket}))
    except Exception as e:
        logger.error(f"Get ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>/reply', methods=['POST', 'OPTIONS'])
def reply_ticket(ticket_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'message': 'Message required'}), 400
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id, 'user_id': str(user['_id'])})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        if ticket['status'] == 'closed':
            return jsonify({'success': False, 'message': 'Cannot reply to closed ticket'}), 400
        reply = {'sender': 'user', 'sender_name': user['username'], 'message': message, 'created_at': datetime.now(timezone.utc)}
        support_tickets_collection.update_one({'ticket_id': ticket_id}, {'$push': {'messages': reply}, '$set': {'updated_at': datetime.now(timezone.utc), 'status': 'open'}})
        return add_cors_headers(jsonify({'success': True, 'message': 'Reply sent'}))
    except Exception as e:
        logger.error(f"Reply ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/support/tickets/<ticket_id>/close', methods=['POST', 'OPTIONS'])
def close_ticket(ticket_id):
    user = get_user_from_request()
    if not user:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    try:
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id, 'user_id': str(user['_id'])})
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        support_tickets_collection.update_one({'ticket_id': ticket_id}, {'$set': {'status': 'closed', 'closed_at': datetime.now(timezone.utc), 'updated_at': datetime.now(timezone.utc)}})
        return add_cors_headers(jsonify({'success': True, 'message': 'Ticket closed'}))
    except Exception as e:
        logger.error(f"Close ticket error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - STATISTICS ====================
@app.route('/api/admin/stats', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_stats():
    try:
        total_users = users_collection.count_documents({}) if users_collection else 0
        total_deposit_amount = 0
        total_withdrawal_amount = 0
        active_investments = 0
        pending_deposits = 0
        pending_withdrawals = 0
        banned_users = users_collection.count_documents({'is_banned': True}) if users_collection else 0
        if deposits_collection:
            approved_deposits = list(deposits_collection.find({'status': 'approved'}))
            total_deposit_amount = sum(d.get('amount', 0) for d in approved_deposits)
            pending_deposits = deposits_collection.count_documents({'status': 'pending'})
        if withdrawals_collection:
            approved_withdrawals = list(withdrawals_collection.find({'status': 'approved'}))
            total_withdrawal_amount = sum(w.get('amount', 0) for w in approved_withdrawals)
            pending_withdrawals = withdrawals_collection.count_documents({'status': 'pending'})
        if investments_collection:
            active_investments = investments_collection.count_documents({'status': 'active'})
        return add_cors_headers(jsonify({'success': True, 'data': {
            'total_users': total_users, 'total_deposit_amount': total_deposit_amount,
            'total_withdrawal_amount': total_withdrawal_amount, 'active_investments': active_investments,
            'pending_deposits': pending_deposits, 'pending_withdrawals': pending_withdrawals, 'banned_users': banned_users
        }}))
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'total_users': 0, 'total_deposit_amount': 0, 'total_withdrawal_amount': 0, 'active_investments': 0, 'pending_deposits': 0, 'pending_withdrawals': 0, 'banned_users': 0}})), 200


# ==================== ADMIN - USERS ====================
@app.route('/api/admin/users', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_users():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        search = request.args.get('search', '')
        skip = (page - 1) * limit
        query = {}
        if search:
            query['$or'] = [{'username': {'$regex': search, '$options': 'i'}}, {'email': {'$regex': search, '$options': 'i'}}, {'full_name': {'$regex': search, '$options': 'i'}}]
        total = users_collection.count_documents(query) if users_collection else 0
        users = []
        if users_collection:
            users = list(users_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        formatted_users = []
        for user in users:
            wallet = user.get('wallet', {})
            formatted_users.append({
                '_id': str(user['_id']), 'username': user.get('username', ''), 'email': user.get('email', ''),
                'full_name': user.get('full_name', ''), 'phone': user.get('phone', ''), 'country': user.get('country', ''),
                'wallet': wallet, 'is_admin': user.get('is_admin', False), 'is_banned': user.get('is_banned', False),
                'is_verified': user.get('is_verified', False), 'kyc_status': user.get('kyc_status', 'pending'),
                'created_at': user.get('created_at').isoformat() if user.get('created_at') else None,
                'last_login': user.get('last_login').isoformat() if user.get('last_login') else None,
                'referral_code': user.get('referral_code', ''), 'referrals': user.get('referrals', [])
            })
        return add_cors_headers(jsonify({'success': True, 'data': {'users': formatted_users, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1, 'limit': limit}}))
    except Exception as e:
        logger.error(f"Get users error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/users/<user_id>/balance', methods=['POST', 'OPTIONS'])
@require_admin
def admin_adjust_balance(user_id):
    try:
        data = request.get_json()
        amount = float(data.get('amount', 0))
        reason = data.get('reason', 'Admin adjustment')
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        if investment_users:
            investment_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
        if transactions_collection:
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
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        new_ban_status = not user.get('is_banned', False)
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$set': {'is_banned': new_ban_status}})
        if investment_users:
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
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        username = user.get('username', 'Unknown')
        if veloxtrades_users:
            veloxtrades_users.delete_one({'_id': ObjectId(user_id)})
        if investment_users:
            investment_users.delete_one({'_id': ObjectId(user_id)})
        for collection in [investments_collection, transactions_collection, deposits_collection, withdrawals_collection, notifications_collection]:
            if collection:
                collection.delete_many({'user_id': str(user_id)})
        return add_cors_headers(jsonify({'success': True, 'message': f'User {username} deleted'}))
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


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
        total = deposits_collection.count_documents(query) if deposits_collection else 0
        deposits = []
        if deposits_collection:
            deposits = list(deposits_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        result_deposits = []
        for d in deposits:
            d['_id'] = str(d['_id'])
            if d.get('created_at'):
                d['created_at'] = d['created_at'].isoformat()
            if users_collection:
                user = users_collection.find_one({'_id': ObjectId(d['user_id'])})
                d['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_deposits.append(d)
        return add_cors_headers(jsonify({'success': True, 'data': {'deposits': result_deposits, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get deposits error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'deposits': [], 'total': 0}})), 200


@app.route('/api/admin/deposits/<deposit_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_deposit(deposit_id):
    try:
        data = request.get_json()
        action = data.get('action')
        reason = data.get('reason', '')
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        if action == 'approve':
            if veloxtrades_users:
                veloxtrades_users.update_one({'_id': ObjectId(deposit['user_id'])}, {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}})
            if investment_users:
                investment_users.update_one({'_id': ObjectId(deposit['user_id'])}, {'$inc': {'wallet.balance': deposit['amount'], 'wallet.total_deposited': deposit['amount']}})
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}})
            if transactions_collection:
                transactions_collection.update_one({'deposit_id': deposit['deposit_id'], 'type': 'deposit', 'status': 'pending'}, {'$set': {'status': 'completed'}})
            create_notification(deposit['user_id'], 'Deposit Approved! ✅', f'Deposit of ${deposit["amount"]:,.2f} approved!', 'success')
            send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
            add_referral_commission(deposit['user_id'], deposit['amount'])
        elif action == 'reject':
            deposits_collection.update_one({'_id': ObjectId(deposit_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'rejected_at': datetime.now(timezone.utc)}})
            if transactions_collection:
                transactions_collection.update_one({'deposit_id': deposit['deposit_id'], 'type': 'deposit', 'status': 'pending'}, {'$set': {'status': 'failed'}})
            create_notification(deposit['user_id'], 'Deposit Rejected ❌', f'Deposit of ${deposit["amount"]:,.2f} rejected. Reason: {reason}', 'error')
            send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], reason)
        return add_cors_headers(jsonify({'success': True, 'message': f'Deposit {action}d successfully'}))
    except Exception as e:
        logger.error(f"Process deposit error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/resend-deposit-emails', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_deposit_emails():
    try:
        data = request.get_json() or {}
        status_filter = data.get('status', 'approved')
        query = {'status': status_filter} if status_filter != 'all' else {'status': {'$in': ['approved', 'rejected']}}
        deposits = list(deposits_collection.find(query)) if deposits_collection else []
        sent = 0
        failed = 0
        for deposit in deposits:
            user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
            if not user:
                failed += 1
                continue
            if deposit['status'] == 'approved':
                if send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash')):
                    sent += 1
                else:
                    failed += 1
            elif deposit['status'] == 'rejected':
                if send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], deposit.get('rejection_reason', 'Not specified')):
                    sent += 1
                else:
                    failed += 1
        return add_cors_headers(jsonify({'success': True, 'message': f'Resent {sent} emails, {failed} failed', 'data': {'sent': sent, 'failed': failed}}))
    except Exception as e:
        logger.error(f"Bulk resend error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/deposits/<deposit_id>/resend-email', methods=['POST', 'OPTIONS'])
@require_admin
def admin_resend_single_deposit_email(deposit_id):
    try:
        deposit = deposits_collection.find_one({'_id': ObjectId(deposit_id)})
        if not deposit:
            return jsonify({'success': False, 'message': 'Deposit not found'}), 404
        user = users_collection.find_one({'_id': ObjectId(deposit['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        if deposit['status'] == 'approved':
            sent = send_deposit_approved_email(user, deposit['amount'], deposit['crypto'], deposit.get('transaction_hash'))
        elif deposit['status'] == 'rejected':
            sent = send_deposit_rejected_email(user, deposit['amount'], deposit['crypto'], deposit.get('rejection_reason', 'Not specified'))
        else:
            return jsonify({'success': False, 'message': 'Deposit not processed'}), 400
        return add_cors_headers(jsonify({'success': sent, 'message': 'Email resent' if sent else 'Failed to send'}))
    except Exception as e:
        logger.error(f"Resend email error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


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
        total = withdrawals_collection.count_documents(query) if withdrawals_collection else 0
        withdrawals = []
        if withdrawals_collection:
            withdrawals = list(withdrawals_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        result_withdrawals = []
        for w in withdrawals:
            w['_id'] = str(w['_id'])
            if w.get('created_at'):
                w['created_at'] = w['created_at'].isoformat()
            if users_collection:
                user = users_collection.find_one({'_id': ObjectId(w['user_id'])})
                w['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_withdrawals.append(w)
        return add_cors_headers(jsonify({'success': True, 'data': {'withdrawals': result_withdrawals, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get withdrawals error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'withdrawals': [], 'total': 0}})), 200


@app.route('/api/admin/withdrawals/<withdrawal_id>/process', methods=['POST', 'OPTIONS'])
@require_admin
def admin_process_withdrawal(withdrawal_id):
    try:
        data = request.get_json()
        action = data.get('action')
        reason = data.get('reason', '')
        withdrawal = withdrawals_collection.find_one({'_id': ObjectId(withdrawal_id)})
        if not withdrawal:
            return jsonify({'success': False, 'message': 'Withdrawal not found'}), 404
        user = users_collection.find_one({'_id': ObjectId(withdrawal['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        if action == 'approve':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'approved', 'approved_at': datetime.now(timezone.utc)}})
            if transactions_collection:
                transactions_collection.update_one({'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'}, {'$set': {'status': 'completed'}})
            create_notification(withdrawal['user_id'], 'Withdrawal Approved! ✅', f'Withdrawal of ${withdrawal["amount"]:,.2f} approved!', 'success')
            send_withdrawal_approved_email(user, withdrawal['amount'], withdrawal['currency'], withdrawal['wallet_address'])
        elif action == 'reject':
            withdrawals_collection.update_one({'_id': ObjectId(withdrawal_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'rejected_at': datetime.now(timezone.utc)}})
            if veloxtrades_users:
                veloxtrades_users.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': withdrawal['amount']}})
            if investment_users:
                investment_users.update_one({'_id': ObjectId(withdrawal['user_id'])}, {'$inc': {'wallet.balance': withdrawal['amount']}})
            if transactions_collection:
                transactions_collection.update_one({'withdrawal_id': withdrawal['withdrawal_id'], 'type': 'withdrawal', 'status': 'pending'}, {'$set': {'status': 'failed'}})
            create_notification(withdrawal['user_id'], 'Withdrawal Rejected ❌', f'Withdrawal of ${withdrawal["amount"]:,.2f} rejected. Reason: {reason}', 'error')
            send_withdrawal_rejected_email(user, withdrawal['amount'], withdrawal['currency'], reason)
        return add_cors_headers(jsonify({'success': True, 'message': f'Withdrawal {action}d successfully'}))
    except Exception as e:
        logger.error(f"Process withdrawal error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - INVESTMENTS ====================
@app.route('/api/admin/investments', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_investments():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        query = {}
        if status != 'all':
            query['status'] = status
        total = investments_collection.count_documents(query) if investments_collection else 0
        investments = []
        if investments_collection:
            investments = list(investments_collection.find(query).sort('start_date', -1).skip(skip).limit(limit))
        result_investments = []
        for inv in investments:
            inv['_id'] = str(inv['_id'])
            if inv.get('start_date'):
                inv['start_date'] = inv['start_date'].isoformat()
            if inv.get('end_date'):
                inv['end_date'] = inv['end_date'].isoformat()
            if users_collection:
                user = users_collection.find_one({'_id': ObjectId(inv['user_id'])})
                inv['username'] = user.get('username', 'Unknown') if user else 'Unknown'
            result_investments.append(inv)
        return add_cors_headers(jsonify({'success': True, 'data': {'investments': result_investments, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get investments error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'investments': [], 'total': 0}})), 200


@app.route('/api/admin/investments/<investment_id>/complete', methods=['POST', 'OPTIONS'])
@require_admin
def admin_complete_investment(investment_id):
    try:
        investment = investments_collection.find_one({'_id': ObjectId(investment_id)})
        if not investment:
            return jsonify({'success': False, 'message': 'Investment not found'}), 404
        if investment['status'] != 'active':
            return jsonify({'success': False, 'message': 'Investment already completed'}), 400
        user = users_collection.find_one({'_id': ObjectId(investment['user_id'])})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        profit = investment.get('expected_profit', 0)
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': ObjectId(investment['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
        if investment_users:
            investment_users.update_one({'_id': ObjectId(investment['user_id'])}, {'$inc': {'wallet.balance': profit, 'wallet.total_profit': profit}})
        investments_collection.update_one({'_id': ObjectId(investment_id)}, {'$set': {'status': 'completed', 'completed_at': datetime.now(timezone.utc)}})
        if transactions_collection:
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


# ==================== ADMIN - TRANSACTIONS ====================
@app.route('/api/admin/transactions', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_transactions():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 50))
        tx_type = request.args.get('type', 'all')
        skip = (page - 1) * limit
        query = {}
        if tx_type != 'all':
            query['type'] = tx_type
        total = transactions_collection.count_documents(query) if transactions_collection else 0
        transactions = []
        if transactions_collection:
            transactions = list(transactions_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        result_transactions = []
        for tx in transactions:
            tx['_id'] = str(tx['_id'])
            if tx.get('created_at'):
                tx['created_at'] = tx['created_at'].isoformat()
            if users_collection:
                user = users_collection.find_one({'_id': ObjectId(tx['user_id'])})
                tx['user'] = {'username': user.get('username', 'Unknown') if user else 'Unknown', 'email': user.get('email', '') if user else ''}
            result_transactions.append(tx)
        return add_cors_headers(jsonify({'success': True, 'data': {'transactions': result_transactions, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get admin transactions error: {e}")
        return add_cors_headers(jsonify({'success': True, 'data': {'transactions': [], 'total': 0}})), 200


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
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        transaction_data = {
            'user_id': user_id, 'type': transaction_type, 'amount': amount,
            'status': 'completed', 'description': f'{description} (Admin created)',
            'created_at': datetime.now(timezone.utc), 'admin_created': True
        }
        result = transactions_collection.insert_one(transaction_data) if transactions_collection else None
        if add_to_balance:
            if veloxtrades_users:
                veloxtrades_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
            if investment_users:
                investment_users.update_one({'_id': ObjectId(user_id)}, {'$inc': {'wallet.balance': amount}})
            create_notification(user_id, f'{transaction_type.capitalize()} Added! 🎉', f'${amount:,.2f} added to your account. Reason: {description}', 'success')
            new_balance = user.get('wallet', {}).get('balance', 0) + amount
            return add_cors_headers(jsonify({'success': True, 'message': f'Transaction created and ${amount:,.2f} added', 'data': {'new_balance': new_balance}}))
        return add_cors_headers(jsonify({'success': True, 'message': 'Transaction created', 'data': {'transaction_id': str(result.inserted_id) if result else None}}))
    except Exception as e:
        logger.error(f"Create transaction error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - KYC ====================
@app.route('/api/admin/kyc/applications', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_applications():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'pending')
        skip = (page - 1) * limit
        query = {}
        if status != 'all':
            query['status'] = status
        total = kyc_collection.count_documents(query) if kyc_collection else 0
        applications = []
        if kyc_collection:
            applications = list(kyc_collection.find(query).sort('submitted_at', -1).skip(skip).limit(limit))
        result_applications = []
        for app in applications:
            app['_id'] = str(app['_id'])
            if app.get('submitted_at'):
                app['submitted_at'] = app['submitted_at'].isoformat()
            if users_collection:
                user = users_collection.find_one({'_id': ObjectId(app['user_id'])})
                if user:
                    app['user_details'] = {'username': user.get('username', ''), 'email': user.get('email', ''), 'wallet_balance': user.get('wallet', {}).get('balance', 0)}
            result_applications.append(app)
        return add_cors_headers(jsonify({'success': True, 'data': {'applications': result_applications, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Get KYC applications error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/kyc/<kyc_id>', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_kyc_application(kyc_id):
    try:
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)}) if kyc_collection else None
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        kyc['_id'] = str(kyc['_id'])
        if kyc.get('submitted_at'):
            kyc['submitted_at'] = kyc['submitted_at'].isoformat()
        if users_collection:
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
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)}) if kyc_collection else None
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        kyc_collection.update_one({'_id': ObjectId(kyc_id)}, {'$set': {'status': 'approved', 'reviewed_at': datetime.now(timezone.utc)}})
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'verified', 'is_verified': True}})
        if investment_users:
            investment_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'verified', 'is_verified': True}})
        create_notification(kyc['user_id'], 'KYC Approved! ✅', 'Your KYC verification has been approved.', 'success')
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
        kyc = kyc_collection.find_one({'_id': ObjectId(kyc_id)}) if kyc_collection else None
        if not kyc:
            return jsonify({'success': False, 'message': 'KYC not found'}), 404
        kyc_collection.update_one({'_id': ObjectId(kyc_id)}, {'$set': {'status': 'rejected', 'rejection_reason': reason, 'reviewed_at': datetime.now(timezone.utc)}})
        if veloxtrades_users:
            veloxtrades_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'rejected'}})
        if investment_users:
            investment_users.update_one({'_id': ObjectId(kyc['user_id'])}, {'$set': {'kyc_status': 'rejected'}})
        create_notification(kyc['user_id'], 'KYC Rejected ❌', f'Your KYC was rejected. Reason: {reason}', 'error')
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
    try:
        pending = kyc_collection.count_documents({'status': 'pending'}) if kyc_collection else 0
        approved = kyc_collection.count_documents({'status': 'approved'}) if kyc_collection else 0
        rejected = kyc_collection.count_documents({'status': 'rejected'}) if kyc_collection else 0
        return add_cors_headers(jsonify({'success': True, 'data': {'pending': pending, 'approved': approved, 'rejected': rejected, 'total': pending + approved + rejected}}))
    except Exception as e:
        logger.error(f"Get KYC stats error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== ADMIN - SUPPORT TICKETS ====================
@app.route('/api/admin/support/tickets', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_tickets():
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        status = request.args.get('status', 'all')
        skip = (page - 1) * limit
        query = {}
        if status != 'all':
            query['status'] = status
        total = support_tickets_collection.count_documents(query) if support_tickets_collection else 0
        tickets = []
        if support_tickets_collection:
            tickets = list(support_tickets_collection.find(query).sort('created_at', -1).skip(skip).limit(limit))
        result_tickets = []
        for t in tickets:
            t['_id'] = str(t['_id'])
            if t.get('created_at'):
                t['created_at'] = t['created_at'].isoformat()
            t['message_count'] = len(t.get('messages', []))
            t.pop('messages', None)
            result_tickets.append(t)
        return add_cors_headers(jsonify({'success': True, 'data': {'tickets': result_tickets, 'total': total, 'page': page, 'pages': (total + limit - 1) // limit if total > 0 else 1}}))
    except Exception as e:
        logger.error(f"Admin get tickets error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/admin/support/tickets/<ticket_id>', methods=['GET', 'OPTIONS'])
@require_admin
def admin_get_ticket(ticket_id):
    try:
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id}) if support_tickets_collection else None
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
        if users_collection:
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
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id}) if support_tickets_collection else None
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        reply = {'sender': 'admin', 'sender_id': str(admin_user['_id']), 'sender_name': admin_user.get('username', 'Admin'), 'message': message, 'created_at': datetime.now(timezone.utc)}
        support_tickets_collection.update_one({'ticket_id': ticket_id}, {'$push': {'messages': reply}, '$set': {'updated_at': datetime.now(timezone.utc), 'status': 'pending'}})
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
        ticket = support_tickets_collection.find_one({'ticket_id': ticket_id}) if support_tickets_collection else None
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
    try:
        open_tickets = support_tickets_collection.count_documents({'status': 'open'}) if support_tickets_collection else 0
        pending_tickets = support_tickets_collection.count_documents({'status': 'pending'}) if support_tickets_collection else 0
        resolved_tickets = support_tickets_collection.count_documents({'status': 'resolved'}) if support_tickets_collection else 0
        closed_tickets = support_tickets_collection.count_documents({'status': 'closed'}) if support_tickets_collection else 0
        return add_cors_headers(jsonify({'success': True, 'data': {'open': open_tickets, 'pending': pending_tickets, 'resolved': resolved_tickets, 'closed': closed_tickets, 'total': open_tickets + pending_tickets + resolved_tickets + closed_tickets}}))
    except Exception as e:
        logger.error(f"Get ticket stats error: {e}")
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
        query = {}
        if recipients_type == 'active':
            query = {'is_banned': False}
        elif recipients_type == 'depositors':
            query = {'wallet.total_deposited': {'$gt': 0}}
        elif recipients_type == 'investors':
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
        users = list(users_collection.find(query)) if users_collection else []
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
        all_users = list(users_collection.find({}, {'username': 1, 'email': 1, 'full_name': 1, 'referral_code': 1, 'referred_by': 1, 'created_at': 1, 'wallet.total_deposited': 1})) if users_collection else []
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
        if veloxtrades_users:
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
            if veloxtrades_users:
                veloxtrades_users.update_one({'_id': existing_admin['_id']}, {'$set': {'password': hashed_password, 'is_admin': True}})
            if investment_users:
                investment_users.update_one({'_id': existing_admin['_id']}, {'$set': {'password': hashed_password, 'is_admin': True}})
            admin_id = existing_admin['_id']
            message = 'Admin account updated'
        else:
            result = veloxtrades_users.insert_one(admin_data) if veloxtrades_users else None
            if investment_users:
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
        'mongo': 'connected' if veloxtrades_db else 'disconnected',
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
