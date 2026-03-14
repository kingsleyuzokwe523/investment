# backend/modules/user_controller.py
from datetime import datetime


class UserController:
    def __init__(self, db, user_model, investment_model, transaction_model):
        self.db = db
        self.user_model = user_model
        self.investment_model = investment_model
        self.transaction_model = transaction_model

    def register_user(self, username, email, password):
        """Register new user"""
        # Check if email exists
        if self.user_model.find_by_email(email):
            return {"error": "Email already registered"}

        # Check if username exists
        if self.user_model.find_by_username(username):
            return {"error": "Username already taken"}

        # Create user
        user_id = self.user_model.create(username, email, password)

        # Log transaction
        self.transaction_model.create(
            user_id=user_id,
            amount=0,
            type='registration',
            description='Account created'
        )

        return {
            "success": True,
            "user_id": user_id,
            "message": "Registration successful"
        }

    def login_user(self, email, password):
        """User login"""
        user = self.user_model.find_by_email(email)
        if not user:
            return {"error": "Invalid credentials"}

        # Check if blocked
        if user.get('is_blocked', False):
            return {"error": "Account is blocked. Contact admin."}

        # Verify password
        from modules.auth import Auth
        auth = Auth()
        if not auth.verify_password(user['password'], password):
            return {"error": "Invalid credentials"}

        # Update last login
        self.user_model.update_last_login(str(user['_id']))

        return {
            "success": True,
            "user_id": str(user['_id']),
            "username": user['username'],
            "email": user['email'],
            "balance": user['balance'],
            "is_admin": user.get('is_admin', False)
        }

    def make_investment(self, user_id, amount):
        """User makes an investment"""
        # Check if user exists
        user = self.user_model.find_by_id(user_id)
        if not user:
            return {"error": "User not found"}

        # Check if user is blocked
        if user.get('is_blocked', False):
            return {"error": "Account is blocked"}

        # Check if user has enough balance
        if user['balance'] < float(amount):
            return {"error": "Insufficient balance"}

        # Deduct from balance
        self.user_model.update_balance(user_id, -float(amount))

        # Create investment
        investment_id = self.investment_model.create(user_id, amount)

        # Update user's total invested
        from bson import ObjectId
        self.db.get_collection('users').update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'total_invested': float(amount)}}
        )

        # Log transaction
        self.transaction_model.create(
            user_id=user_id,
            amount=float(amount),
            type='investment',
            description=f'Investment #{investment_id}'
        )

        return {
            "success": True,
            "investment_id": investment_id,
            "message": "Investment submitted for admin approval",
            "new_balance": user['balance'] - float(amount)
        }

    def get_user_dashboard(self, user_id):
        """Get dashboard data for user"""
        user = self.user_model.find_by_id(user_id)
        if not user:
            return {"error": "User not found"}

        investments = self.investment_model.get_by_user(user_id)
        transactions = self.transaction_model.get_by_user(user_id)

        return {
            "success": True,
            "user": {
                "username": user['username'],
                "email": user['email'],
                "balance": user['balance'],
                "total_invested": user.get('total_invested', 0),
                "total_withdrawn": user.get('total_withdrawn', 0),
                "total_profit": user.get('total_profit', 0),
                "total_loss": user.get('total_loss', 0),
                "last_login": user.get('last_login'),
                "created_at": user.get('created_at')
            },
            "investments": investments,
            "transactions": transactions[:10]  # Last 10 transactions
        }

    def request_withdrawal(self, user_id, amount):
        """User requests withdrawal"""
        user = self.user_model.find_by_id(user_id)
        if not user:
            return {"error": "User not found"}

        if user.get('is_blocked', False):
            return {"error": "Account is blocked"}

        if user['balance'] < float(amount):
            return {"error": "Insufficient balance"}

        # For now, we'll just deduct balance
        # In real system, you'd have withdrawal request queue for admin approval
        self.user_model.update_balance(user_id, -float(amount))

        # Update total withdrawn
        from bson import ObjectId
        self.db.get_collection('users').update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'total_withdrawn': float(amount)}}
        )

        # Log transaction
        self.transaction_model.create(
            user_id=user_id,
            amount=float(amount),
            type='withdrawal',
            description='Withdrawal request'
        )

        return {
            "success": True,
            "message": "Withdrawal processed",
            "new_balance": user['balance'] - float(amount)
        }