# backend/modules/models.py
from datetime import datetime
import bcrypt


class User:
    def __init__(self, db):
        self.collection = db.get_collection('users')

    def create(self, username, email, password):
        """Create new user with hashed password"""
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        user = {
            'username': username,
            'email': email,
            'password': hashed.decode('utf-8'),
            'balance': 0.0,
            'total_invested': 0.0,
            'total_withdrawn': 0.0,
            'is_admin': False,
            'is_blocked': False,
            'created_at': datetime.utcnow(),
            'last_login': None,
            'last_investment': None,
            'total_profit': 0.0,
            'total_loss': 0.0
        }

        result = self.collection.insert_one(user)
        return str(result.inserted_id)

    def find_by_email(self, email):
        return self.collection.find_one({'email': email})

    def find_by_id(self, user_id):
        from bson import ObjectId
        return self.collection.find_one({'_id': ObjectId(user_id)})

    def find_by_username(self, username):
        return self.collection.find_one({'username': username})

    def update_last_login(self, user_id):
        from bson import ObjectId
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'last_login': datetime.utcnow()}}
        )

    def update_balance(self, user_id, amount):
        """Update user balance (positive for deposit, negative for withdrawal)"""
        from bson import ObjectId
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'balance': amount}}
        )

    def block_user(self, user_id, bson=None):
        from bson import ObjectId
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_blocked': True}}
        )

    def unblock_user(self, user_id):
        from bson import ObjectId
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'is_blocked': False}}
        )

    def get_all_users(self):
        return list(self.collection.find({}, {'password': 0}))


class Investment:
    def __init__(self, db):
        self.collection = db.get_collection('investments')

    def create(self, user_id, amount):
        """Create new pending investment"""
        investment = {
            'user_id': user_id,
            'amount': float(amount),
            'status': 'pending',  # pending, profit, loss, completed
            'profit_loss_percentage': 0.0,
            'final_amount': float(amount),
            'admin_notes': '',
            'is_active': True,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'completed_at': None
        }

        result = self.collection.insert_one(investment)
        return str(result.inserted_id)

    def update_status(self, investment_id, status, percentage, notes=""):
        """Update investment status (admin only)"""
        from bson import ObjectId

        # Calculate final amount based on percentage
        investment = self.collection.find_one({'_id': ObjectId(investment_id)})
        if not investment:
            return False

        final_amount = investment['amount'] * (1 + percentage / 100)

        self.collection.update_one(
            {'_id': ObjectId(investment_id)},
            {'$set': {
                'status': status,
                'profit_loss_percentage': percentage,
                'final_amount': final_amount,
                'admin_notes': notes,
                'updated_at': datetime.utcnow(),
                'completed_at': datetime.utcnow() if status in ['profit', 'loss'] else None
            }}
        )
        return True

    def get_pending(self):
        """Get all pending investments"""
        return list(self.collection.find({'status': 'pending'}))

    def get_by_user(self, user_id):
        """Get all investments for a user"""
        return list(self.collection.find({'user_id': user_id}).sort('created_at', -1))

    def get_all(self):
        """Get all investments"""
        return list(self.collection.find().sort('created_at', -1))


class Transaction:
    def __init__(self, db):
        self.collection = db.get_collection('transactions')

    def create(self, user_id, amount, type, description=""):
        """Create transaction record"""
        transaction = {
            'user_id': user_id,
            'amount': float(amount),
            'type': type,  # deposit, withdrawal, investment, profit, loss
            'description': description,
            'status': 'completed',
            'created_at': datetime.utcnow()
        }

        result = self.collection.insert_one(transaction)
        return str(result.inserted_id)

    def get_by_user(self, user_id):
        """Get all transactions for a user"""
        return list(self.collection.find({'user_id': user_id}).sort('created_at', -1))