from datetime import datetime
from bson import ObjectId


class Investment:
    def __init__(self, db):
        self.collection = db.investments

    def create_investment(self, user_id, amount, investment_type="standard"):
        """Create a new investment"""
        investment_data = {
            'user_id': ObjectId(user_id),
            'amount': float(amount),
            'status': 'pending',
            'type': investment_type,
            'result_type': None,  # 'profit' or 'loss'
            'percentage_change': 0.0,
            'final_amount': 0.0,
            'profit_loss_amount': 0.0,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow(),
            'admin_notes': '',
            'processed_by': None,
            'processed_at': None,
            'duration_days': 0,
            'expected_return': 0.0
        }

        result = self.collection.insert_one(investment_data)
        investment_id = str(result.inserted_id)

        # Update user's total investments count
        from backend.models.user import User
        user_model = User(self.collection.database)
        user_model.update_user(user_id, {
            'total_investments': {'$inc': 1},
            'active_investments': {'$inc': 1}
        })

        return investment_id

    def get_investment_by_id(self, investment_id):
        """Get investment by ID"""
        try:
            investment = self.collection.find_one({'_id': ObjectId(investment_id)})
            if investment:
                investment['_id'] = str(investment['_id'])
                investment['user_id'] = str(investment['user_id'])
                if investment.get('processed_by'):
                    investment['processed_by'] = str(investment['processed_by'])
            return investment
        except:
            return None

    def get_user_investments(self, user_id, status=None, page=1, limit=20):
        """Get all investments for a specific user"""
        skip = (page - 1) * limit

        # Convert string user_id to ObjectId
        try:
            user_object_id = ObjectId(user_id)
        except:
            return {'investments': [], 'total': 0, 'page': page, 'limit': limit, 'total_pages': 0}

        # Build query
        query = {'user_id': user_object_id}
        if status:
            query['status'] = status

        investments = list(self.collection.find(
            query
        ).sort('created_at', -1).skip(skip).limit(limit))

        total = self.collection.count_documents(query)

        # Convert ObjectId to string for JSON serialization
        for investment in investments:
            investment['_id'] = str(investment['_id'])
            investment['user_id'] = str(investment['user_id'])
            if investment.get('processed_by'):
                investment['processed_by'] = str(investment['processed_by'])

        return {
            'investments': investments,
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit
        }

    def get_pending_investments(self, page=1, limit=20):
        """Get all pending investments for admin"""
        skip = (page - 1) * limit
        investments = list(self.collection.find(
            {'status': 'pending'}
        ).sort('created_at', 1).skip(skip).limit(limit))

        total = self.collection.count_documents({'status': 'pending'})

        for investment in investments:
            investment['_id'] = str(investment['_id'])
            investment['user_id'] = str(investment['user_id'])

        return {
            'investments': investments,
            'total': total,
            'page': page,
            'limit': limit,
            'total_pages': (total + limit - 1) // limit
        }



    def process_profit(self, investment_id, percentage, admin_id, admin_notes=''):
        """Process investment as PROFIT"""
        investment = self.get_investment_by_id(investment_id)
        if not investment or investment['status'] != 'pending':
            return None, "Investment not found or already processed"

        amount = investment['amount']
        profit_amount = amount * (percentage / 100)
        final_amount = amount + profit_amount

        update_data = {
            'status': 'completed',
            'result_type': 'profit',
            'percentage_change': percentage,
            'final_amount': final_amount,
            'profit_loss_amount': profit_amount,
            'admin_notes': admin_notes,
            'processed_by': ObjectId(admin_id),
            'processed_at': datetime.utcnow()
        }

        success = self.update_investment(investment_id, update_data)

        if success:
            # Update user balance and stats
            from backend.models.user import User
            user_model = User(self.collection.database)
            user_model.process_investment_result(
                investment['user_id'],
                amount,
                final_amount
            )

            # Update user's active investments count
            user_model.update_user(investment['user_id'], {
                'active_investments': {'$inc': -1}
            })

            return {
                'investment_id': investment_id,
                'original_amount': amount,
                'result_type': 'profit',
                'percentage_change': percentage,
                'profit_amount': profit_amount,
                'final_amount': final_amount,
                'processed_by': admin_id,
                'processed_at': update_data['processed_at']
            }, "Investment processed as PROFIT successfully"

        return None, "Failed to process investment"

    def process_loss(self, investment_id, percentage, admin_id, admin_notes=''):
        """Process investment as LOSS"""
        investment = self.get_investment_by_id(investment_id)
        if not investment or investment['status'] != 'pending':
            return None, "Investment not found or already processed"

        amount = investment['amount']
        loss_amount = amount * (percentage / 100)
        final_amount = amount - loss_amount

        # Ensure final amount is not negative
        if final_amount < 0:
            final_amount = 0

        update_data = {
            'status': 'completed',
            'result_type': 'loss',
            'percentage_change': -percentage,  # Negative for loss
            'final_amount': final_amount,
            'profit_loss_amount': -loss_amount,  # Negative for loss
            'admin_notes': admin_notes,
            'processed_by': ObjectId(admin_id),
            'processed_at': datetime.utcnow()
        }

        success = self.update_investment(investment_id, update_data)

        if success:
            # Update user balance and stats
            from backend.models.user import User
            user_model = User(self.collection.database)
            user_model.process_investment_result(
                investment['user_id'],
                amount,
                final_amount
            )

            # Update user's active investments count
            user_model.update_user(investment['user_id'], {
                'active_investments': {'$inc': -1}
            })

            return {
                'investment_id': investment_id,
                'original_amount': amount,
                'result_type': 'loss',
                'percentage_change': -percentage,
                'loss_amount': loss_amount,
                'final_amount': final_amount,
                'processed_by': admin_id,
                'processed_at': update_data['processed_at']
            }, "Investment processed as LOSS successfully"

        return None, "Failed to process investment"

    def process_custom_amount(self, investment_id, result_type, custom_amount, admin_id, admin_notes=''):
        """Process investment with custom final amount"""
        investment = self.get_investment_by_id(investment_id)
        if not investment or investment['status'] != 'pending':
            return None, "Investment not found or already processed"

        amount = investment['amount']
        profit_loss_amount = custom_amount - amount
        percentage = (profit_loss_amount / amount) * 100

        update_data = {
            'status': 'completed',
            'result_type': result_type,
            'percentage_change': percentage,
            'final_amount': custom_amount,
            'profit_loss_amount': profit_loss_amount,
            'admin_notes': admin_notes,
            'processed_by': ObjectId(admin_id),
            'processed_at': datetime.utcnow()
        }

        success = self.update_investment(investment_id, update_data)

        if success:
            # Update user balance and stats
            from backend.models.user import User
            user_model = User(self.collection.database)
            user_model.process_investment_result(
                investment['user_id'],
                amount,
                custom_amount
            )

            # Update user's active investments count
            user_model.update_user(investment['user_id'], {
                'active_investments': {'$inc': -1}
            })

            return {
                'investment_id': investment_id,
                'original_amount': amount,
                'result_type': result_type,
                'percentage_change': percentage,
                'profit_loss_amount': profit_loss_amount,
                'final_amount': custom_amount,
                'processed_by': admin_id,
                'processed_at': update_data['processed_at']
            }, f"Invesment processed as {result_type.upper()} successfully"

        return None, "Failed to process investment"

    def delete_investment(self, investment_id):
        """Delete an investment"""
        # Get investment first to update user stats
        investment = self.get_investment_by_id(investment_id)
        if investment and investment['status'] == 'pending':
            # Update user's active investments count
            from backend.models.user import User
            user_model = User(self.collection.database)
            user_model.update_user(investment['user_id'], {
                'active_investments': {'$inc': -1},
                'total_investments': {'$inc': -1}
            })

        result = self.collection.delete_one({'_id': ObjectId(investment_id)})
        return result.deleted_count > 0

    def get_user_investment_stats(self, user_id):
        """Get investment statistics for a user"""
        try:
            user_object_id = ObjectId(user_id)
        except:
            return None

        # Get all user investments
        investments = list(self.collection.find({'user_id': user_object_id}))

        total_invested = sum(inv.get('amount', 0) for inv in investments)
        pending_investments = [inv for inv in investments if inv.get('status') == 'pending']
        completed_investments = [inv for inv in investments if inv.get('status') == 'completed']

        total_pending = len(pending_investments)
        total_completed = len(completed_investments)
        pending_amount = sum(inv.get('amount', 0) for inv in pending_investments)
        completed_amount = sum(inv.get('amount', 0) for inv in completed_investments)

        # Calculate profit/loss from completed investments
        total_profit_loss = sum(inv.get('profit_loss_amount', 0) for inv in completed_investments)

        # Count profits and losses
        profits = [inv for inv in completed_investments if inv.get('result_type') == 'profit']
        losses = [inv for inv in completed_investments if inv.get('result_type') == 'loss']

        return {
            'total_invested': total_invested,
            'total_pending': total_pending,
            'total_completed': total_completed,
            'total_profits': len(profits),
            'total_losses': len(losses),
            'total_profit_loss': total_profit_loss,
            'pending_amount': pending_amount,
            'completed_amount': completed_amount,
            'total_profit_amount': sum(inv.get('profit_loss_amount', 0) for inv in profits),
            'total_loss_amount': abs(sum(inv.get('profit_loss_amount', 0) for inv in losses))
        }