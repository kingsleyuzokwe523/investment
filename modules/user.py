from datetime import datetime
from bson import ObjectId
import bcrypt


class User:
    def __init__(self, db):
        self.collection = db.users

    def create_user(self, user_data):
        """Create a new user with all required fields"""
        # Hash the password
        hashed_password = self.hash_password(user_data['password'])

        user_document = {
            'username': user_data['username'],
            'email': user_data['email'],
            'phone': user_data.get('phone', ''),
            'password_hash': hashed_password,
            'full_name': user_data.get('full_name', ''),
            'balance': 0.0,
            'initial_balance': 0.0,
            'is_blocked': False,
            'role': 'user',  # Default role
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'last_login': None,
            'total_investments': 0,
            'active_investments': 0,
            'total_profit': 0.0,
            'total_loss': 0.0,
            'total_invested': 0.0
        }

        result = self.collection.insert_one(user_document)
        return str(result.inserted_id)

    def create_admin_user(self, email, password, full_name=""):
        """Create an admin user (should be called once during setup)"""
        # Check if admin already exists
        existing_admin = self.collection.find_one({'email': email, 'role': 'admin'})
        if existing_admin:
            return str(existing_admin['_id'])

        hashed_password = self.hash_password(password)

        admin_document = {
            'username': 'admin',
            'email': email,
            'phone': '',
            'password_hash': hashed_password,
            'full_name': full_name or 'System Administrator',
            'balance': 0.0,
            'initial_balance': 0.0,
            'is_blocked': False,
            'role': 'admin',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'last_login': None,
            'total_investments': 0,
            'active_investments': 0,
            'total_profit': 0.0,
            'total_loss': 0.0,
            'total_invested': 0.0
        }

        result = self.collection.insert_one(admin_document)
        return str(result.inserted_id)

    def hash_password(self, password):
        """Hash a password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt)

    def verify_password(self, password, hashed_password):
        """Verify a password against its hash"""
        if isinstance(hashed_password, str):
            hashed_password = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password)

    def authenticate_user(self, username_or_email, password):
        """Authenticate user by username or email"""
        # Try to find by email first
        user = self.collection.find_one({'email': username_or_email})

        # If not found by email, try by username
        if not user:
            user = self.collection.find_one({'username': username_or_email})

        if not user:
            return None

        # Check if user is blocked
        if user.get('is_blocked', False):
            return {'error': 'Account is blocked. Contact administrator.'}

        # Verify password
        if self.verify_password(password, user['password_hash']):
            # Update last login time
            self.collection.update_one(
                {'_id': user['_id']},
                {'$set': {'last_login': datetime.utcnow()}}
            )

            # Convert ObjectId to string for JSON serialization
            user['_id'] = str(user['_id'])
            return user

        return None

    def authenticate_admin(self, email, password):
        """Authenticate admin user"""
        user = self.collection.find_one({
            'email': email,
            'role': 'admin'
        })

        if not user:
            return None

        if self.verify_password(password, user['password_hash']):
            # Update last login time
            self.collection.update_one(
                {'_id': user['_id']},
                {'$set': {'last_login': datetime.utcnow()}}
            )

            user['_id'] = str(user['_id'])
            return user

        return None

    def find_by_email(self, email):
        """Find user by email"""
        user = self.collection.find_one({'email': email})
        if user:
            user['_id'] = str(user['_id'])
        return user

    def find_by_username(self, username):
        """Find user by username"""
        user = self.collection.find_one({'username': username})
        if user:
            user['_id'] = str(user['_id'])
        return user

    def find_by_id(self, user_id):
        """Find user by ID"""
        try:
            user = self.collection.find_one({'_id': ObjectId(user_id)})
            if user:
                user['_id'] = str(user['_id'])
            return user
        except:
            return None

    def update_user(self, user_id, update_data):
        """Update user information"""
        update_data['updated_at'] = datetime.utcnow()
        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': update_data}
        )
        return result.modified_count > 0

    def update_balance(self, user_id, amount):
        """Update user balance by adding/subtracting amount"""
        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$inc': {'balance': float(amount)}}
        )
        return result.modified_count > 0

    def update_user_stats(self, user_id, amount, profit_loss=0, is_profit=True):
        """Update user investment statistics"""
        update_data = {
            '$inc': {
                'total_invested': float(amount),
                'total_investments': 1
            }
        }

        if is_profit:
            update_data['$inc']['total_profit'] = float(profit_loss)
        else:
            update_data['$inc']['total_loss'] = float(profit_loss)

        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            update_data
        )
        return result.modified_count > 0

    def process_investment_result(self, user_id, original_amount, final_amount):
        """Process investment result and update user balance and stats"""
        profit_loss = final_amount - original_amount
        is_profit = profit_loss > 0

        # Update balance
        balance_update = self.update_balance(user_id, profit_loss)

        # Update stats
        stats_update = self.update_user_stats(user_id, original_amount, abs(profit_loss), is_profit)

        return balance_update and stats_update

    def get_all_users(self, page=1, limit=20):
        """Get all users with pagination (for admin)"""
        skip = (page - 1) * limit
        users = list(self.collection.find(
            {'role': 'user'}  # Only regular users, not admins
        ).sort('created_at', -1).skip(skip).limit(limit))

        total = self.collection.count_documents({'role': 'user'})

        # Convert ObjectId to string and remove password hash
        for user in users:
            user['_id'] = str(user['_id'])
            user.pop('password_hash', None)  # Remove password hash for security

        return {
            'users': users,
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit
        }

    def get_user_stats(self, user_id):
        """Get user statistics"""
        user = self.find_by_id(user_id)
        if not user:
            return None

        return {
            'user_id': str(user['_id']),
            'username': user.get('username'),
            'email': user.get('email'),
            'phone': user.get('phone', ''),
            'full_name': user.get('full_name', ''),
            'balance': user.get('balance', 0),
            'initial_balance': user.get('initial_balance', 0),
            'is_blocked': user.get('is_blocked', False),
            'created_at': user.get('created_at'),
            'last_login': user.get('last_login'),
            'role': user.get('role', 'user'),
            'total_investments': user.get('total_investments', 0),
            'total_invested': user.get('total_invested', 0),
            'total_profit': user.get('total_profit', 0),
            'total_loss': user.get('total_loss', 0),
            'net_profit': user.get('total_profit', 0) - user.get('total_loss', 0)
        }

    def toggle_block_user(self, user_id):
        """Toggle user blocked status"""
        user = self.find_by_id(user_id)
        if not user:
            return None

        new_status = not user.get('is_blocked', False)
        self.update_user(user_id, {'is_blocked': new_status})
        return new_status

    def check_username_exists(self, username):
        """Check if username already exists"""
        return self.collection.find_one({'username': username}) is not None

    def check_email_exists(self, email):
        """Check if email already exists"""
        return self.collection.find_one({'email': email}) is not None

    def change_password(self, user_id, new_password):
        """Change user password"""
        hashed_password = self.hash_password(new_password)
        return self.update_user(user_id, {'password_hash': hashed_password})

    def deposit_funds(self, user_id, amount):
        """Deposit funds to user account"""
        return self.update_balance(user_id, amount)

    def withdraw_funds(self, user_id, amount):
        """Withdraw funds from user account"""
        user = self.find_by_id(user_id)
        if not user:
            return False, "User not found"

        if user.get('balance', 0) < float(amount):
            return False, "Insufficient funds"

        success = self.update_balance(user_id, -float(amount))
        return success, "Withdrawal successful" if success else "Withdrawal failed"