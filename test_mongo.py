#

import os
import sys
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("🔍 MONGODB CONNECTION TEST")
print("=" * 50)

uri = os.getenv('MONGO_URI')
if not uri:
    print("❌ MONGO_URI not found in .env file")
    sys.exit(1)

# Hide password for display
hidden_uri = uri.replace('Trewqasd15e.', '********')
print(f"📌 URI: {hidden_uri}")
print()

try:
    print("⏳ Connecting to MongoDB Atlas...")
    client = MongoClient(uri, serverSelectionTimeoutMS=10000)

    # Test connection
    client.admin.command('ping')
    print("✅ SUCCESS: Connected to MongoDB Atlas!")

    # List databases
    dbs = client.list_database_names()
    print(f"📊 Available databases: {dbs}")

    # Check our database
    if 'investment_db' in dbs:
        print("✅ Database 'investment_db' exists")
        db = client['investment_db']

        # List collections
        collections = db.list_collection_names()
        print(f"📁 Collections: {collections}")

        # Check users collection
        if 'users' in collections:
            user_count = db.users.count_documents({})
            print(f"👥 Users in database: {user_count}")

            # Show sample users (without passwords)
            print("\n📋 Sample users:")
            for user in db.users.find().limit(3):
                print(f"   • {user.get('username')} - {user.get('email')}")
        else:
            print("⚠️ 'users' collection not found yet")
    else:
        print("⚠️ Database 'investment_db' not found - will be created when you add first user")

except ServerSelectionTimeoutError as e:
    print(f"❌ TIMEOUT ERROR: {e}")
    print("\n🔧 Troubleshooting steps:")
    print("   1. Check your internet connection")
    print("   2. Go to MongoDB Atlas → Network Access → Add IP 0.0.0.0/0")
    print("   3. Check if cluster is paused (free tier pauses after 60 days)")
    print("   4. Verify username/password in .env")
except ConnectionFailure as e:
    print(f"❌ CONNECTION ERROR: {e}")
    print("\n🔧 Troubleshooting steps:")
    print("   1. Check if MongoDB Atlas is up (https://status.mongodb.com)")
    print("   2. Verify your connection string format")
    print("   3. Try creating a new database user")
except Exception as e:
    print(f"❌ UNEXPECTED ERROR: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 50)
