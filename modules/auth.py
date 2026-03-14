# backend/modules/auth.py
import jwt
import os
from datetime import datetime, timedelta
import bcrypt
from dotenv import load_dotenv

load_dotenv()


class Auth:
    def __init__(self):
        self.secret_key = os.getenv('JWT_SECRET_KEY', 'secret-key-change-me')
        self.admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        self.admin_password = os.getenv('ADMIN_PASSWORD', 'admin123456')

    def create_token(self, user_id, is_admin=False, username=""):
        """Create JWT token"""
        payload = {
            'user_id': user_id,
            'is_admin': is_admin,
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=24)
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def verify_token(self, token):
        """Verify JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def hash_password(self, password):
        """Hash password"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, hashed_password, password):
        """Verify password against hash"""
        return bcrypt.checkpw(
            password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    def verify_admin_credentials(self, username, password):
        """Verify admin credentials from .env"""
        return username == self.admin_username and password == self.admin_password