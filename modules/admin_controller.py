# backend/modules/admin_controller.py
from datetime import datetime
from bson import ObjectId


class AdminController:
    def __init__(self, db, user_model, investment_model, transaction_model):
        self.db = db
        self.user_model = user_model
        self.investment_model = investment_model
        self.transaction_model = transaction_model

    def get_all_users(self):
        """Get all users (admin only)"""
        users = self.user_model.get_all_users()
        return {
            "success": True,
            "count": len(users),
            "users": users
        }

    def get_all_investments(self):
        """Get all investments (admin only)"""
        investments = self.investment_model.get_all()
        return {
            "success": True,
            "count": len(investments),
            "investments": investments
        }

    def get_pending_investments(self):
        """Get pending investments needing admin action"""
        investments = self.investment_model.get_pending()
        return {
            "success": True,
            "count": len(investments),
            "investments": investments
        }

    def update_investment(self, investment_id, status, percentage, notes=""):
        """Update investment status (profit/loss)"""
        # Update investment
        success = self.investment_model.update_status(investment_id, status, percentage, notes)
        if not success:
            return {"error": "Investment not found"}

        # Get investment details
        investment = self.db.get_collection('investments').find_one(
            {'_id': ObjectId(investment_id)}
        )

        user_id = investment['user_id']
        final_amount = investment['final_amount']
        original_amount = investment['amount']

        # Update user balance
        if status == 'profit':
            profit_amount = final_amount - original_amount
            self.user_model.update_balance(user_id, profit_amount)

            # Update user profit stats
            self.db.get_collection('users').update_one(
                {'_id': ObjectId(user_id)},
                {'$inc': {'total_profit': profit_amount}}
            )

            # Log transaction
            self.transaction_model.create(
                user_id=user_id,
                amount=profit_amount,
                type='profit',
                description=f'Profit from investment #{investment_id}'
            )

        elif status == 'loss':
            loss_amount = original_amount - final_amount

            # Update user loss stats
            self.db.get_collection('users').update_one(
                {'_id': ObjectId(user_id)},
                {'$inc': {'total_loss': loss_amount}}
            )

            # Log transaction
            self.transaction_model.create(
                user_id=user_id,
                amount=loss_amount,
                type='loss',
                description=f'Loss from investment #{investment_id}'
            )

        return {
            "success": True,
            "message": f"Investment updated to {status}",
            "investment_id": investment_id,
            "final_amount": final_amount
        }

    def block_user(self, user_id):
        """Block a user"""
        self.user_model.block_user(user_id)
        return {
            "success": True,
            "message": "User blocked successfully"
        }

    def unblock_user(self, user_id):
        """Unblock a user"""
        self.user_model.unblock_user(user_id)
        return {
            "success": True,
            "message": "User unblocked successfully"
        }

    def get_system_stats(self):
        """Get system statistics"""
        users = self.db.get_collection('users')
        investments = self.db.get_collection('investments')
        transactions = self.db.get_collection('transactions')

        total_users = users.count_documents({})
        active_users = users.count_documents({'is_blocked': False})
        blocked_users = users.count_documents({'is_blocked': True})

        total_investments = investments.count_documents({})
        pending_investments = investments.count_documents({'status': 'pending'})
        completed_investments = investments.count_documents({'status': {'$in': ['profit', 'loss']}})

        total_deposited = sum(user['total_invested'] for user in users.find({}, {'total_invested': 1}))
        total_withdrawn = sum(user['total_withdrawn'] for user in users.find({}, {'total_withdrawn': 1}))

        return {
            "success": True,
            "stats": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "blocked": blocked_users
                },
                "investments": {
                    "total": total_investments,
                    "pending": pending_investments,
                    "completed": completed_investments
                },
                "financial": {
                    "total_deposited": total_deposited,
                    "total_withdrawn": total_withdrawn,
                    "net_balance": total_deposited - total_withdrawn
                }
            }
        }