import os
from dotenv import load_dotenv
from pymongo import MongoClient
from backend.models.user import User


def init_database():
    """Initialize database connection and create admin user if not exists"""
    load_dotenv()

    # Get MongoDB URI from environment
    mongo_uri = os.getenv('MONGO_URI')
    if not mongo_uri:
        raise ValueError("MONGO_URI not found in environment variables")

    # Connect to MongoDB
    client = MongoClient(mongo_uri)
    db = client.get_database()

    print(f"✅ Connected to database: {db.name}")

    # Create indexes for better performance
    print("Creating database indexes...")

    # Users collection indexes
    db.users.create_index('email', unique=True)
    db.users.create_index('username', unique=True)
    db.users.create_index('created_at')
    db.users.create_index([('role', 1), ('is_blocked', 1)])
    db.users.create_index('balance')

    # Investments collection indexes
    db.investments.create_index('user_id')
    db.investments.create_index('status')
    db.investments.create_index([('user_id', 1), ('status', 1)])
    db.investments.create_index('created_at')
    db.investments.create_index('result_type')
    db.investments.create_index('processed_at')

    # Activity logs collection indexes
    db.activity_logs.create_index('user_id')
    db.activity_logs.create_index('activity_type')
    db.activity_logs.create_index('timestamp')
    db.activity_logs.create_index([('user_id', 1), ('timestamp', -1)])

    print("✅ Database indexes created")

    # Create admin user if not exists
    admin_email = os.getenv('ADMIN_EMAIL')
    admin_password = os.getenv('ADMIN_PASSWORD')

    if admin_email and admin_password:
        user_model = User(db)
        existing_admin = user_model.collection.find_one({'email': admin_email, 'role': 'admin'})

        if not existing_admin:
            admin_id = user_model.create_admin_user(admin_email, admin_password)
            print(f"\n✅ Admin user created successfully!")
            print(f"📧 Admin email: {admin_email}")
            print(f"🔑 Admin password: {admin_password}")
            print("⚠️  IMPORTANT: Change these default credentials immediately!")
        else:
            print(f"\n✅ Admin user already exists: {admin_email}")

    print("\n✅ Database initialization completed successfully!")
    return db