from datetime import datetime
from bson import ObjectId


class ActivityLog:
    def __init__(self, db):
        self.collection = db.activity_logs

    def log_activity(self, user_id, activity_type, description, metadata=None, ip_address=None):
        """Log user activity"""
        log_data = {
            'user_id': ObjectId(user_id) if user_id else None,
            'activity_type': activity_type,
            'description': description,
            'metadata': metadata or {},
            'ip_address': ip_address,
            'timestamp': datetime.utcnow()
        }

        result = self.collection.insert_one(log_data)
        return str(result.inserted_id)

    def log_registration(self, user_id, username, email, ip_address=None):
        """Log user registration"""
        return self.log_activity(
            user_id,
            'registration',
            f'New user registered: {username} ({email})',
            {'username': username, 'email': email},
            ip_address
        )

    def log_login(self, user_id, username, role, ip_address=None):
        """Log user login"""
        return self.log_activity(
            user_id,
            'login',
            f'User logged in: {username} ({role})',
            {'username': username, 'role': role},
            ip_address
        )

    def log_investment(self, user_id, amount, investment_id, ip_address=None):
        """Log investment creation"""
        return self.log_activity(
            user_id,
            'investment',
            f'New investment created: ${amount}',
            {'amount': amount, 'investment_id': investment_id},
            ip_address
        )

    def log_investment_result(self, admin_id, user_id, investment_id, result_type, amount, profit_loss,
                              ip_address=None):
        """Log investment result (profit/loss)"""
        return self.log_activity(
            admin_id,
            'investment_result',
            f'Investment {result_type}: ${profit_loss} on ${amount} investment',
            {
                'user_id': user_id,
                'investment_id': investment_id,
                'result_type': result_type,
                'amount': amount,
                'profit_loss': profit_loss
            },
            ip_address
        )

    def log_admin_action(self, admin_id, action, target_user_id=None, details=None, ip_address=None):
        """Log admin actions"""
        description = f'Admin action: {action}'
        if target_user_id:
            description += f' on user {target_user_id}'

        metadata = {'action': action, 'details': details or {}}
        if target_user_id:
            metadata['target_user_id'] = target_user_id

        return self.log_activity(
            admin_id,
            'admin_action',
            description,
            metadata,
            ip_address
        )

    def log_balance_update(self, admin_id, user_id, amount, reason, ip_address=None):
        """Log balance update"""
        return self.log_activity(
            admin_id,
            'balance_update',
            f'Balance updated: ${amount} for user {user_id}',
            {'user_id': user_id, 'amount': amount, 'reason': reason},
            ip_address
        )

    def get_user_activity(self, user_id, limit=50):
        """Get activity logs for a specific user"""
        try:
            user_object_id = ObjectId(user_id)
        except:
            return []

        logs = list(self.collection.find(
            {'user_id': user_object_id}
        ).sort('timestamp', -1).limit(limit))

        # Convert ObjectId to string
        for log in logs:
            log['_id'] = str(log['_id'])
            log['user_id'] = str(log['user_id'])

        return logs

    def get_recent_activity(self, limit=100):
        """Get recent activity for admin dashboard"""
        logs = list(self.collection.find().sort('timestamp', -1).limit(limit))

        # Convert ObjectId to string
        for log in logs:
            log['_id'] = str(log['_id'])
            if log.get('user_id'):
                log['user_id'] = str(log['user_id'])

        return logs

    def get_system_stats(self, days=30):
        """Get system statistics for the last N days"""
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Count registrations
        registrations = self.collection.count_documents({
            'activity_type': 'registration',
            'timestamp': {'$gte': cutoff_date}
        })

        # Count logins
        logins = self.collection.count_documents({
            'activity_type': 'login',
            'timestamp': {'$gte': cutoff_date}
        })

        # Count investments
        investments = self.collection.count_documents({
            'activity_type': 'investment',
            'timestamp': {'$gte': cutoff_date}
        })

        # Count investment results
        investment_results = self.collection.count_documents({
            'activity_type': 'investment_result',
            'timestamp': {'$gte': cutoff_date}
        })

        # Count admin actions
        admin_actions = self.collection.count_documents({
            'activity_type': 'admin_action',
            'timestamp': {'$gte': cutoff_date}
        })

        return {
            'registrations': registrations,
            'logins': logins,
            'investments': investments,
            'investment_results': investment_results,
            'admin_actions': admin_actions,
            'period_days': days
        }

    def get_user_login_history(self, user_id, limit=20):
        """Get user login history"""
        try:
            user_object_id = ObjectId(user_id)
        except:
            return []

        logs = list(self.collection.find({
            'user_id': user_object_id,
            'activity_type': 'login'
        }).sort('timestamp', -1).limit(limit))

        for log in logs:
            log['_id'] = str(log['_id'])
            log['user_id'] = str(log['user_id'])

        return logs