"""
Utility functions for MakonBook Telegram Bot
Shared functions used across different handlers
"""

import random
import string
from typing import Optional

from asgiref.sync import sync_to_async
from .models import TelegramAdmin


def generate_password(length: int = 8) -> str:
    """Generate a password with numbers and alphabetic characters only"""
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


async def check_admin_privileges(telegram_id: int) -> Optional[TelegramAdmin]:
    """Check if user has admin or support privileges"""
    try:
        admin = await sync_to_async(
            TelegramAdmin.objects.get
        )(
            telegram_id=telegram_id,
            is_active=True
        )
        return admin if (admin.is_admin or admin.is_support) else None
    except TelegramAdmin.DoesNotExist:
        return None


def format_user_info(admin: TelegramAdmin) -> str:
    """Format admin user information for display"""
    role = "Admin" if admin.is_admin else "Support"
    name = admin.first_name or admin.username or f"User {admin.telegram_id}"
    return f"{name} ({role})"


def validate_prefix(prefix: str) -> tuple[bool, str]:
    """Validate username prefix and return (is_valid, error_message)"""
    if not prefix:
        return False, "Prefix cannot be empty"
    
    if not prefix.isalnum():
        return False, "Prefix must contain only letters and numbers"
    
    if len(prefix) < 2:
        return False, "Prefix must be at least 2 characters long"
    
    if len(prefix) > 10:
        return False, "Prefix must be no more than 10 characters long"
    
    return True, ""


def validate_count(count_str: str) -> tuple[bool, int, str]:
    """Validate user count and return (is_valid, count, error_message)"""
    try:
        count = int(count_str.strip())
        if count < 1:
            return False, 0, "Count must be at least 1"
        if count > 50:
            return False, 0, "Count cannot exceed 50 users per request"
        return True, count, ""
    except ValueError:
        return False, 0, "Count must be a valid number"


def generate_username(prefix: str, number: int) -> str:
    """Generate username with prefix and zero-padded number"""
    return f"{prefix}{number:03d}"


def format_success_message(created_count: int, failed_count: int, created_users: list) -> str:
    """Format success message for user creation"""
    message = (
        f"✅ <b>Users Created Successfully!</b>\n\n"
        f"<b>📊 Summary:</b>\n"
        f"• Created: {created_count} users\n"
        f"• Failed: {failed_count} users\n\n"
    )
    
    if created_users:
        message += f"<b>👥 Created Users:</b>\n"
        # Show first 20 users
        users_to_show = created_users[:20]
        message += "<code>" + "\n".join(users_to_show) + "</code>"
        
        if len(created_users) > 20:
            message += f"\n\n<i>... and {len(created_users) - 20} more users</i>"
    
    message += "\n\n<b>💾 All credentials have been saved to the database.</b>"
    return message


def format_error_message(error: Exception) -> str:
    """Format error message for display"""
    return (
        f"❌ <b>Error Creating Users</b>\n\n"
        f"An error occurred: {str(error)}\n\n"
        f"Please try again or contact the administrator."
    )


def format_request_history(requests: list) -> str:
    """Format request history for display"""
    if not requests:
        return "📊 No bulk creation requests found."
    
    text = "📊 <b>Your Recent Requests</b>\n\n"
    
    for req in requests:
        status_emoji = {
            'pending': '⏳',
            'processing': '🔄',
            'completed': '✅',
            'failed': '❌'
        }.get(req.status, '❓')
        
        text += (
            f"{status_emoji} <b>{req.prefix}</b> x{req.count}\n"
            f"   Status: {req.status.title()}\n"
            f"   Date: {req.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        )
    
    return text


def get_status_emoji(status: str) -> str:
    """Get emoji for request status"""
    status_emojis = {
        'pending': '⏳',
        'processing': '🔄',
        'completed': '✅',
        'failed': '❌'
    }
    return status_emojis.get(status, '❓')


class BotMessages:
    """Static messages used throughout the bot"""
    
    ACCESS_DENIED = (
        "❌ <b>Access Denied</b>\n\n"
        "You are not authorized to use this bot.\n"
        "Contact the administrator to get access."
    )
    
    OPERATION_CANCELLED = "❌ Operation cancelled."
    
    READY_FOR_NEXT = "Ready for next operation!"
    
    CREATING_USERS = "⏳ Creating users... Please wait."
    
    INVALID_PREFIX = (
        "❌ <b>Invalid Prefix</b>\n\n"
        "Please enter a valid prefix:\n"
        "• 2-10 characters only\n"
        "• Letters and numbers only\n"
        "• No spaces or special characters\n\n"
        "Try again: 👇"
    )
    
    INVALID_COUNT = (
        "❌ <b>Invalid Number</b>\n\n"
        "Please enter a valid number:\n"
        "• Must be between 1 and 50\n"
        "• Whole numbers only\n\n"
        "Try again: 👇"
    )
    
    NO_REQUESTS_FOUND = "📊 No bulk creation requests found."
    
    @staticmethod
    def welcome_message(admin: TelegramAdmin) -> str:
        """Generate welcome message for admin"""
        return (
            f"👋 <b>Welcome to MakonBook User Management Bot!</b>\n\n"
            f"Hello <b>{admin.first_name or admin.username or 'Admin'}</b>!\n\n"
            f"<b>🔐 Your Privileges:</b>\n"
            f"{'✅ Full Admin Access' if admin.is_admin else '✅ Support Access'}\n\n"
            f"<b>🚀 Available Functions:</b>\n"
            f"• 🔄 Create bulk users (1-50 per request)\n"
            f"• 👥 Assign users to groups\n"
            f"• 📊 View your request history\n"
            f"• 🔐 Generate secure passwords\n\n"
            f"Choose an option from the menu below: 👇"
        )
    
    @staticmethod
    def prefix_set_message(prefix: str) -> str:
        """Generate message when prefix is set"""
        return (
            f"✅ <b>Prefix Set:</b> <code>{prefix}</code>\n\n"
            f"<b>📝 Step 2: Number of Users</b>\n"
            f"How many users do you want to create?\n\n"
            f"<b>⚠️ Limits:</b>\n"
            f"• Minimum: 1 user\n"
            f"• Maximum: 50 users per request\n\n"
            f"<b>💡 Examples:</b>\n"
            f"• Enter <code>10</code> to create {prefix}001 through {prefix}010\n"
            f"• Enter <code>25</code> to create {prefix}001 through {prefix}025\n\n"
            f"Enter the number of users: 👇"
        )
    
    @staticmethod
    def count_set_message(prefix: str, count: int) -> str:
        """Generate message when count is set"""
        return (
            f"✅ <b>Count Set:</b> {count} users\n\n"
            f"<b>📝 Step 3: User Groups</b>\n"
            f"Select which groups the new users should belong to.\n"
            f"You can select multiple groups or none.\n\n"
            f"<b>📋 Preview:</b>\n"
            f"• Users: {prefix}001 through {prefix}{count:03d}\n"
            f"• Passwords: 8-character random (letters + numbers)\n\n"
            f"Select groups below: 👇"
        )
    
    @staticmethod
    def confirmation_message(prefix: str, count: int, group_names: list) -> str:
        """Generate confirmation message"""
        groups_text = ', '.join(group_names) if group_names else 'None'
        return (
            f"📋 <b>Creation Summary</b>\n\n"
            f"<b>📝 Details:</b>\n"
            f"• Prefix: <code>{prefix}</code>\n"
            f"• Count: {count} users\n"
            f"• Groups: {groups_text}\n\n"
            f"<b>👥 Users to be created:</b>\n"
            f"• {prefix}001 through {prefix}{count:03d}\n"
            f"• Each with a random 8-character password\n\n"
            f"<b>⚠️ This action cannot be undone!</b>\n\n"
            f"Do you want to proceed? 👇"
        )


class BotConstants:
    """Constants used throughout the bot"""
    
    MAX_USERS_PER_REQUEST = 50
    MIN_USERS_PER_REQUEST = 1
    PASSWORD_LENGTH = 8
    USERNAME_PREFIX_MIN_LENGTH = 2
    USERNAME_PREFIX_MAX_LENGTH = 10
    MAX_HISTORY_REQUESTS = 10
    MAX_USERS_TO_DISPLAY = 20
    MAX_FAILED_USERS_TO_DISPLAY = 10 