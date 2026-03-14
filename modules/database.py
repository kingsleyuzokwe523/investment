# backend/modules/database.py
import os
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.client = None
            self.db = None
            self.connect()
            self._initialized = True

    def connect(self):
        """Connect to MongoDB Atlas"""
        try:
            uri = os.getenv('MONGO_URI')
            self.client = MongoClient(uri, server_api=ServerApi('1'))
            self.client.admin.command('ping')
            self.db = self.client['investment_db']
            print("✅ MongoDB Connected Successfully")
            self._setup_collections()
        except Exception as e:
            print(f"❌ MongoDB Connection Error: {e}")
            raise

    def _setup_collections(self):
        """Create collections with indexes"""
        # Users collection
        if 'users' not in self.db.list_collection_names():
            self.db.create_collection('users')
            self.db.users.create_index('email', unique=True)
            self.db.users.create_index('username', unique=True)
            print("✅ Created 'users' collection")

        # Investments collection
        if 'investments' not in self.db.list_collection_names():
            self.db.create_collection('investments')
            self.db.investments.create_index([('user_id', 1), ('created_at', -1)])
            self.db.investments.create_index('status')
            print("✅ Created 'investments' collection")

        # Transactions collection (for withdrawals)
        if 'transactions' not in self.db.list_collection_names():
            self.db.create_collection('transactions')
            self.db.transactions.create_index([('user_id', 1), ('created_at', -1)])
            self.db.transactions.create_index('type')
            print("✅ Created 'transactions' collection")

        # Admin logs collection
        if 'admin_logs' not in self.db.list_collection_names():
            self.db.create_collection('admin_logs')
            self.db.admin_logs.create_index([('created_at', -1)])
            print("✅ Created 'admin_logs' collection")

    def get_collection(self, name):
        """Get collection by name"""
        return self.db[name]


# Global database instance
db = Database()