"""
Telegram Bot Handlers for MakonBook SAT System
Modular handler classes for different bot functionality
"""

import logging
import os
from datetime import datetime
from typing import List, Optional
import math

from aiogram import types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from django.contrib.auth.models import User, Group
from asgiref.sync import sync_to_async

from .models import TelegramAdmin, BulkUserRequest, GeneratedUser
from .utils import generate_password, check_admin_privileges

logger = logging.getLogger(__name__)


# States for conversation
class UserCreationStates(StatesGroup):
    waiting_for_prefix = State()
    waiting_for_count = State()
    waiting_for_groups = State()
    confirming_creation = State()


class PaginationConstants:
    """Constants for pagination"""
    REQUESTS_PER_PAGE = 5
    MAX_USERS_PER_CHUNK = 15
    MAX_MESSAGE_LENGTH = 4000


class BaseHandler:
    """Base handler class with common functionality"""
    
    @staticmethod
    def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
        """Get main menu keyboard"""
        builder = ReplyKeyboardBuilder()
        builder.add(KeyboardButton(text="🔄 Create Bulk Users"))
        builder.add(KeyboardButton(text="📊 My Requests"))
        if is_admin:
            builder.add(KeyboardButton(text="👥 Manage Admins"))
        builder.add(KeyboardButton(text="ℹ️ Help"))
        builder.adjust(2, 1)
        return builder.as_markup(resize_keyboard=True)

    @staticmethod
    async def get_groups_keyboard() -> InlineKeyboardMarkup:
        """Get available groups as inline keyboard"""
        builder = InlineKeyboardBuilder()
        
        # Get all available groups using async
        groups = await sync_to_async(list)(Group.objects.all())
        for group in groups:
            builder.add(InlineKeyboardButton(
                text=f"⬜ {group.name}",
                callback_data=f"group_{group.id}"
            ))
        
        builder.add(InlineKeyboardButton(text="✅ Confirm Groups", callback_data="confirm_groups"))
        builder.add(InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"))
        builder.adjust(1)
        return builder.as_markup()


class StartHandler(BaseHandler):
    """Handler for start command and basic user interaction"""
    
    @staticmethod
    async def start_command(message: types.Message):
        """Handle /start command"""
        admin = await check_admin_privileges(message.from_user.id)
        
        if not admin:
            await message.answer(
                "❌ <b>Access Denied</b>\n\n"
                "You are not authorized to use this bot.\n"
                "Contact the administrator to get access."
            )
            return
        
        welcome_text = (
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
        
        keyboard = StartHandler.get_main_keyboard(admin.is_admin)
        await message.answer(welcome_text, reply_markup=keyboard)


class HelpHandler(BaseHandler):
    """Handler for help information"""
    
    @staticmethod
    async def show_help(message: types.Message):
        """Show help information"""
        help_text = (
            "ℹ️ <b>MakonBook User Management Bot - Help</b>\n\n"
            
            "<b>🔄 Creating Bulk Users:</b>\n"
            "1. Click 'Create Bulk Users'\n"
            "2. Enter a prefix (2-10 characters, letters/numbers only)\n"
            "3. Specify count (1-50 users)\n"
            "4. Select user groups (optional)\n"
            "5. Confirm and create\n\n"
            
            "<b>📝 Username Format:</b>\n"
            "• Pattern: [prefix][number]\n"
            "• Example: student001, student002, etc.\n"
            "• Numbers are zero-padded to 3 digits\n\n"
            
            "<b>🔐 Password Format:</b>\n"
            "• Length: 8 characters\n"
            "• Contains: Letters (a-z, A-Z) and numbers (0-9)\n"
            "• Example: aB3kL8pQ\n\n"
            
            "<b>👥 User Groups:</b>\n"
            "• Users can belong to multiple groups\n"
            "• Groups determine access permissions\n"
            "• Can be modified later in Django admin\n\n"
            
            "<b>📊 Request History:</b>\n"
            "• View your request history with pagination\n"
            "• Browse through requests 5 at a time\n"
            "• See status and creation details\n"
            "• Download credentials as files\n\n"
            
            "<b>💡 Tips:</b>\n"
            "• Use descriptive prefixes (e.g., 'student2025')\n"
            "• Check existing usernames to avoid conflicts\n"
            "• Save generated passwords securely\n"
            "• Download credential files for backup\n"
            "• Contact admin for additional help"
        )
        
        await message.answer(help_text)


class UserCreationHandler(BaseHandler):
    """Handler for bulk user creation functionality"""
    
    @staticmethod
    async def start_bulk_creation(message: types.Message, state: FSMContext):
        """Start bulk user creation process"""
        admin = await check_admin_privileges(message.from_user.id)
        if not admin:
            await message.answer("❌ Access denied.")
            return
        
        instructions = (
            "🔄 <b>Bulk User Creation - Step 1</b>\n\n"
            "<b>📝 Enter Username Prefix:</b>\n"
            "This will be used for all usernames in this batch.\n\n"
            "<b>📋 Requirements:</b>\n"
            "• 2-10 characters only\n"
            "• Letters and numbers only (a-z, A-Z, 0-9)\n"
            "• No spaces or special characters\n\n"
            "<b>💡 Examples:</b>\n"
            "• <code>student</code> → student001, student002, ...\n"
            "• <code>test2025</code> → test2025001, test2025002, ...\n"
            "• <code>sat</code> → sat001, sat002, ...\n\n"
            "What prefix would you like to use? 👇"
        )
        
        await state.set_state(UserCreationStates.waiting_for_prefix)
        await message.answer(instructions)

    @staticmethod
    async def process_prefix(message: types.Message, state: FSMContext):
        """Process username prefix input"""
        prefix = message.text.strip()
        
        # Validate prefix
        if not prefix.isalnum() or len(prefix) < 2 or len(prefix) > 10:
            await message.answer(
                "❌ <b>Invalid Prefix</b>\n\n"
                "Please enter a valid prefix:\n"
                "• 2-10 characters only\n"
                "• Letters and numbers only\n"
                "• No spaces or special characters\n\n"
                "Try again: 👇"
            )
            return
        
        await state.update_data(prefix=prefix)
        
        count_instructions = (
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
        
        await state.set_state(UserCreationStates.waiting_for_count)
        await message.answer(count_instructions)

    @staticmethod
    async def process_count(message: types.Message, state: FSMContext):
        """Process user count input"""
        try:
            count = int(message.text.strip())
            if count < 1 or count > 50:
                raise ValueError("Count out of range")
        except ValueError:
            await message.answer(
                "❌ <b>Invalid Number</b>\n\n"
                "Please enter a valid number:\n"
                "• Must be between 1 and 50\n"
                "• Whole numbers only\n\n"
                "Try again: 👇"
            )
            return
        
        data = await state.get_data()
        prefix = data['prefix']
        
        await state.update_data(count=count)
        
        groups_instructions = (
            f"✅ <b>Count Set:</b> {count} users\n\n"
            f"<b>📝 Step 3: User Groups</b>\n"
            f"Select which groups the new users should belong to.\n"
            f"You can select multiple groups or none.\n\n"
            f"<b>📋 Preview:</b>\n"
            f"• Users: {prefix}001 through {prefix}{count:03d}\n"
            f"• Passwords: 8-character random (letters + numbers)\n\n"
            f"Select groups below: 👇"
        )
        
        keyboard = await UserCreationHandler.get_groups_keyboard()
        await state.set_state(UserCreationStates.waiting_for_groups)
        await message.answer(groups_instructions, reply_markup=keyboard)


class GroupSelectionHandler(BaseHandler):
    """Handler for group selection during user creation"""
    
    @staticmethod
    async def toggle_group(callback: types.CallbackQuery, state: FSMContext):
        """Toggle group selection"""
        group_id = int(callback.data.split("_")[1])
        data = await state.get_data()
        selected_groups = data.get('selected_groups', [])
        
        if group_id in selected_groups:
            selected_groups.remove(group_id)
        else:
            selected_groups.append(group_id)
        
        await state.update_data(selected_groups=selected_groups)
        
        # Update keyboard
        builder = InlineKeyboardBuilder()
        groups = await sync_to_async(list)(Group.objects.all())
        for group in groups:
            is_selected = group.id in selected_groups
            builder.add(InlineKeyboardButton(
                text=f"{'✅' if is_selected else '⬜'} {group.name}",
                callback_data=f"group_{group.id}"
            ))
        
        builder.add(InlineKeyboardButton(text="✅ Confirm Groups", callback_data="confirm_groups"))
        builder.add(InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"))
        builder.adjust(1)
        
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
        await callback.answer()

    @staticmethod
    async def confirm_groups(callback: types.CallbackQuery, state: FSMContext):
        """Confirm group selection and show final confirmation"""
        data = await state.get_data()
        prefix = data['prefix']
        count = data['count']
        selected_groups = data.get('selected_groups', [])
        
        # Get group names
        group_names = []
        if selected_groups:
            groups = await sync_to_async(list)(Group.objects.filter(id__in=selected_groups))
            group_names = [group.name for group in groups]
        
        confirmation_text = (
            f"📋 <b>Creation Summary</b>\n\n"
            f"<b>📝 Details:</b>\n"
            f"• Prefix: <code>{prefix}</code>\n"
            f"• Count: {count} users\n"
            f"• Groups: {', '.join(group_names) if group_names else 'None'}\n\n"
            f"<b>👥 Users to be created:</b>\n"
            f"• {prefix}001 through {prefix}{count:03d}\n"
            f"• Each with a random 8-character password\n\n"
            f"<b>⚠️ This action cannot be undone!</b>\n\n"
            f"Do you want to proceed? 👇"
        )
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Create Users", callback_data="create_users"))
        builder.add(InlineKeyboardButton(text="❌ Cancel", callback_data="cancel"))
        builder.adjust(1)
        
        await state.set_state(UserCreationStates.confirming_creation)
        await callback.message.edit_text(confirmation_text, reply_markup=builder.as_markup())


class FileManager:
    """Handle file operations for bulk requests"""
    
    @staticmethod
    def ensure_requests_dir():
        """Ensure the telegram_bot/requests directory exists"""
        requests_dir = os.path.join(os.path.dirname(__file__), 'requests')
        if not os.path.exists(requests_dir):
            os.makedirs(requests_dir)
        return requests_dir
    
    @staticmethod
    def save_request_file(request_id: int, prefix: str, created_users: list, failed_users: list = None) -> str:
        """Save request data to file and return file path"""
        requests_dir = FileManager.ensure_requests_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"request_{request_id}_{prefix}_{timestamp}.txt"
        filepath = os.path.join(requests_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"MakonBook SAT System - Bulk User Creation Report\n")
            f.write(f"=" * 50 + "\n")
            f.write(f"Request ID: {request_id}\n")
            f.write(f"Prefix: {prefix}\n")
            f.write(f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Users Created: {len(created_users)}\n")
            if failed_users:
                f.write(f"Failed Users: {len(failed_users)}\n")
            f.write(f"=" * 50 + "\n\n")
            
            f.write("CREATED USERS:\n")
            f.write("-" * 30 + "\n")
            for user_data in created_users:
                f.write(f"{user_data}\n")
            
            if failed_users:
                f.write(f"\nFAILED USERS:\n")
                f.write("-" * 30 + "\n")
                for failed_user in failed_users:
                    f.write(f"{failed_user}\n")
        
        return filepath
    
    @staticmethod
    def get_request_file(request_id: int) -> str:
        """Get file path for a request"""
        requests_dir = FileManager.ensure_requests_dir()
        for filename in os.listdir(requests_dir):
            if filename.startswith(f"request_{request_id}_"):
                return os.path.join(requests_dir, filename)
        return None


class UserExecutionHandler(BaseHandler):
    """Handler for executing user creation"""
    
    @staticmethod
    async def create_users(callback: types.CallbackQuery, state: FSMContext):
        """Create the bulk users"""
        admin = await check_admin_privileges(callback.from_user.id)
        if not admin:
            await callback.message.edit_text("❌ Access denied.")
            return
        
        data = await state.get_data()
        prefix = data['prefix']
        count = data['count']
        selected_groups = data.get('selected_groups', [])
        
        await callback.message.edit_text("⏳ Creating users... Please wait.")
        
        try:
            # Create bulk request record
            bulk_request = await sync_to_async(BulkUserRequest.objects.create)(
                telegram_admin=admin,
                prefix=prefix,
                count=count,
                status='processing'
            )
            
            # Add groups to request
            if selected_groups:
                groups = await sync_to_async(list)(Group.objects.filter(id__in=selected_groups))
                for group in groups:
                    await sync_to_async(bulk_request.groups.add)(group)
            
            created_users = []
            failed_users = []
            
            for i in range(1, count + 1):
                username = f"{prefix}{i:03d}"
                password = generate_password()
                
                try:
                    # Check if username already exists
                    user_exists = await sync_to_async(User.objects.filter(username=username).exists)()
                    if user_exists:
                        failed_users.append(f"{username} (already exists)")
                        continue
                    
                    # Create Django user with proper password handling
                    user = await sync_to_async(User.objects.create_user)(
                        username=username,
                        password=password,  # create_user automatically hashes the password
                        is_active=True
                    )
                    
                    # Add user to selected groups
                    if selected_groups:
                        groups = await sync_to_async(list)(Group.objects.filter(id__in=selected_groups))
                        for group in groups:
                            await sync_to_async(user.groups.add)(group)
                    
                    # Create generated user record
                    await sync_to_async(GeneratedUser.objects.create)(
                        bulk_request=bulk_request,
                        user=user,
                        username=username,
                        password=password  # Store plain password for admin use
                    )
                    
                    # Format: username:Student234, password:dsfbsfe4
                    created_users.append(f"username:{username}, password:{password}")
                    
                except Exception as e:
                    logger.error(f"Error creating user {username}: {e}")
                    failed_users.append(f"{username} (error: {str(e)})")
            
            # Update request status
            bulk_request.status = 'completed' if not failed_users else 'failed'
            if failed_users:
                bulk_request.error_message = "; ".join(failed_users)
            await sync_to_async(bulk_request.save)()
            
            # Save to file
            try:
                file_path = FileManager.save_request_file(
                    bulk_request.id, prefix, created_users, failed_users
                )
                logger.info(f"Saved request file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to save request file: {e}")
            
            # Send results
            if created_users:
                # Create properly formatted message without cutting
                result_lines = [
                    "✅ <b>Users Created Successfully!</b>",
                    "",
                    f"<b>📊 Summary:</b>",
                    f"• Created: {len(created_users)} users",
                    f"• Failed: {len(failed_users)} users" if failed_users else "• Failed: 0 users",
                    "",
                    f"<b>👥 Created Users:</b>"
                ]
                
                # Add all users without cutting
                for user_data in created_users:
                    result_lines.append(f"<code>{user_data}</code>")
                
                if failed_users:
                    result_lines.extend([
                        "",
                        f"<b>❌ Failed Users:</b>"
                    ])
                    for failed_user in failed_users[:10]:  # Show first 10 failed
                        result_lines.append(f"<code>{failed_user}</code>")
                    if len(failed_users) > 10:
                        result_lines.append(f"<i>... and {len(failed_users) - 10} more failed users</i>")
                
                result_lines.extend([
                    "",
                    f"<b>💾 All credentials saved to database and file.</b>",
                    f"<b>🗂️ Request ID: {bulk_request.id}</b>"
                ])
                
                result_text = "\n".join(result_lines)
                
                # Split message if too long for Telegram
                if len(result_text) > PaginationConstants.MAX_MESSAGE_LENGTH:
                    # Send summary first
                    summary_text = "\n".join(result_lines[:8])  # Header + summary
                    summary_text += f"\n\n<b>⚠️ Full list too long for single message.</b>\n<b>📊 Check 'My Requests' for complete details.</b>\n<b>🗂️ Request ID: {bulk_request.id}</b>"
                    await callback.message.edit_text(summary_text)
                    
                    # Send users in chunks
                    users_per_chunk = PaginationConstants.MAX_USERS_PER_CHUNK
                    for i in range(0, len(created_users), users_per_chunk):
                        chunk = created_users[i:i + users_per_chunk]
                        chunk_text = f"<b>👥 Users {i+1}-{min(i+users_per_chunk, len(created_users))}:</b>\n"
                        for user_data in chunk:
                            chunk_text += f"<code>{user_data}</code>\n"
                        await callback.message.answer(chunk_text)
                else:
                    await callback.message.edit_text(result_text)
            else:
                await callback.message.edit_text("❌ No users were created. Please check the error messages above.")
            
            # Show main menu
            keyboard = UserExecutionHandler.get_main_keyboard(admin.is_admin)
            await callback.message.answer("Ready for next operation!", reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error creating users: {e}")
            await callback.message.edit_text(
                f"❌ <b>Error Creating Users</b>\n\n"
                f"An error occurred: {str(e)}\n\n"
                f"Please try again or contact the administrator."
            )
        
        await state.clear()


class RequestHistoryHandler(BaseHandler):
    """Handler for showing request history with pagination"""
    
    @staticmethod
    async def show_my_requests(message: types.Message):
        """Show user's bulk creation requests with pagination"""
        admin = await check_admin_privileges(message.from_user.id)
        if not admin:
            await message.answer("❌ Access denied.")
            return
        
        # Get total count for pagination
        total_requests = await sync_to_async(
            BulkUserRequest.objects.filter(telegram_admin=admin).count
        )()
        
        if total_requests == 0:
            await message.answer("📊 No bulk creation requests found.")
            return
        
        # Show first page
        await RequestHistoryHandler._show_requests_page(message, admin, page=1, total_requests=total_requests)
    
    @staticmethod
    async def _show_requests_page(message_or_callback, admin, page: int, total_requests: int):
        """Show a specific page of requests"""
        per_page = PaginationConstants.REQUESTS_PER_PAGE
        offset = (page - 1) * per_page
        total_pages = math.ceil(total_requests / per_page)
        
        # Get requests for this page, ordered by date (newest first)
        requests = await sync_to_async(list)(
            BulkUserRequest.objects.filter(telegram_admin=admin)
            .order_by('-created_at')[offset:offset + per_page]
        )
        
        # Build message text
        text_lines = [
            f"📊 <b>Your Bulk Creation Requests</b>",
            f"<b>Page {page}/{total_pages}</b> ({total_requests} total)",
            ""
        ]
        
        builder = InlineKeyboardBuilder()
        
        for req in requests:
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'failed': '❌'
            }.get(req.status, '❓')
            
            # Format date nicely
            date_str = req.created_at.strftime('%Y-%m-%d %H:%M')
            
            text_lines.extend([
                f"{status_emoji} <b>{req.prefix}</b> x{req.count} - ID: {req.id}",
                f"   Status: <b>{req.status.title()}</b>",
                f"   Created: {date_str}",
                ""
            ])
            
            # Add action buttons for each request
            if req.status == 'completed':
                builder.add(InlineKeyboardButton(
                    text=f"📄 View {req.prefix}",
                    callback_data=f"view_request_{req.id}"
                ))
                builder.add(InlineKeyboardButton(
                    text=f"📁 Download {req.prefix}",
                    callback_data=f"download_request_{req.id}"
                ))
            elif req.status == 'failed':
                builder.add(InlineKeyboardButton(
                    text=f"⚠️ View {req.prefix} (Failed)",
                    callback_data=f"view_request_{req.id}"
                ))
        
        # Add pagination controls
        if total_pages > 1:
            pagination_row = []
            
            # Previous page button
            if page > 1:
                pagination_row.append(InlineKeyboardButton(
                    text="⬅️ Previous",
                    callback_data=f"requests_page_{page - 1}"
                ))
            
            # Page indicator
            pagination_row.append(InlineKeyboardButton(
                text=f"📄 {page}/{total_pages}",
                callback_data="noop"
            ))
            
            # Next page button
            if page < total_pages:
                pagination_row.append(InlineKeyboardButton(
                    text="Next ➡️",
                    callback_data=f"requests_page_{page + 1}"
                ))
            
            # Add pagination row
            for btn in pagination_row:
                builder.add(btn)
        
        # Adjust button layout: 2 buttons per row for actions, pagination in single row
        builder.adjust(2, 1)
        
        text = "\n".join(text_lines)
        
        # Send message or edit existing one - FIX THE EDIT ISSUE
        if hasattr(message_or_callback, 'edit_text'):
            # It's a callback query message
            try:
                await message_or_callback.edit_text(text, reply_markup=builder.as_markup())
            except Exception as e:
                logger.error(f"Failed to edit message: {e}")
                # Fallback: send new message if edit fails
                await message_or_callback.answer(text, reply_markup=builder.as_markup())
        else:
            # It's a regular message
            await message_or_callback.answer(text, reply_markup=builder.as_markup())
    
    @staticmethod
    async def handle_pagination(callback: types.CallbackQuery):
        """Handle pagination button clicks"""
        page = int(callback.data.split("_")[2])
        admin = await check_admin_privileges(callback.from_user.id)
        
        if not admin:
            await callback.answer("❌ Access denied.")
            return
        
        # Get total count
        total_requests = await sync_to_async(
            BulkUserRequest.objects.filter(telegram_admin=admin).count
        )()
        
        await RequestHistoryHandler._show_requests_page(callback.message, admin, page, total_requests)
        await callback.answer()
    
    @staticmethod
    async def view_request_details(callback: types.CallbackQuery):
        """View details of a specific request"""
        request_id = int(callback.data.split("_")[2])
        admin = await check_admin_privileges(callback.from_user.id)
        
        if not admin:
            await callback.answer("❌ Access denied.")
            return
        
        try:
            # Get the request
            bulk_request = await sync_to_async(BulkUserRequest.objects.get)(
                id=request_id, telegram_admin=admin
            )
            
            # Get generated users ordered by username
            generated_users = await sync_to_async(list)(
                GeneratedUser.objects.filter(bulk_request=bulk_request).order_by('username')
            )
            
            # Create detailed view
            text_lines = [
                f"📋 <b>Request Details - ID: {request_id}</b>",
                f"<b>Prefix:</b> {bulk_request.prefix}",
                f"<b>Total Users:</b> {len(generated_users)}",
                f"<b>Status:</b> {bulk_request.status.title()}",
                f"<b>Created:</b> {bulk_request.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                ""
            ]
            
            if bulk_request.status == 'failed' and bulk_request.error_message:
                text_lines.extend([
                    f"<b>❌ Error Details:</b>",
                    f"<code>{bulk_request.error_message}</code>",
                    ""
                ])
            
            if generated_users:
                text_lines.append(f"<b>👥 All Created Users:</b>")
                
                # Add all users with proper formatting
                for gen_user in generated_users:
                    text_lines.append(f"<code>username:{gen_user.username}, password:{gen_user.password}</code>")
            else:
                text_lines.append(f"<b>⚠️ No users were successfully created for this request.</b>")
            
            result_text = "\n".join(text_lines)
            
            # Create action buttons - download file is ALWAYS visible when viewing details
            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(
                text="📁 Download File", 
                callback_data=f"download_request_{request_id}"
            ))
            builder.add(InlineKeyboardButton(
                text="🔙 Back to Requests", 
                callback_data="back_to_requests"
            ))
            builder.adjust(1)
            
            # Split if too long
            if len(result_text) > PaginationConstants.MAX_MESSAGE_LENGTH:
                summary_text = "\n".join(text_lines[:8])  # Header info
                summary_text += f"\n\n<b>⚠️ Full list too long. Use download button for complete file.</b>"
                
                try:
                    await callback.message.edit_text(summary_text, reply_markup=builder.as_markup())
                except Exception as e:
                    logger.error(f"Failed to edit message in view_request_details: {e}")
                    # Fallback: answer callback and send new message
                    await callback.answer("Loading request details...")
                    await callback.message.answer(summary_text, reply_markup=builder.as_markup())
                
                # Send users in chunks if any exist
                if generated_users:
                    users_per_chunk = 20
                    user_lines = [f"<code>username:{gen.username}, password:{gen.password}</code>" for gen in generated_users]
                    
                    for i in range(0, len(user_lines), users_per_chunk):
                        chunk = user_lines[i:i + users_per_chunk]
                        chunk_text = f"<b>👥 Users {i+1}-{min(i+users_per_chunk, len(user_lines))}:</b>\n"
                        chunk_text += "\n".join(chunk)
                        await callback.message.answer(chunk_text)
            else:
                try:
                    await callback.message.edit_text(result_text, reply_markup=builder.as_markup())
                except Exception as e:
                    logger.error(f"Failed to edit message in view_request_details: {e}")
                    # Fallback: answer callback and send new message
                    await callback.answer("Loading request details...")
                    await callback.message.answer(result_text, reply_markup=builder.as_markup())
                
        except Exception as e:
            logger.error(f"Error viewing request {request_id}: {e}")
            try:
                await callback.message.edit_text(f"❌ Error loading request details: {str(e)}")
            except Exception as edit_error:
                logger.error(f"Failed to edit error message: {edit_error}")
                await callback.answer("❌ Error loading request details")
                await callback.message.answer(f"❌ Error loading request details: {str(e)}")
        
        await callback.answer()
    
    @staticmethod
    async def download_request_file(callback: types.CallbackQuery):
        """Send request file for download"""
        request_id = int(callback.data.split("_")[2])
        admin = await check_admin_privileges(callback.from_user.id)
        
        if not admin:
            await callback.answer("❌ Access denied.")
            return
        
        try:
            # Get the request
            bulk_request = await sync_to_async(BulkUserRequest.objects.get)(
                id=request_id, telegram_admin=admin
            )
            
            # Try to find existing file
            file_path = FileManager.get_request_file(request_id)
            
            if not file_path or not os.path.exists(file_path):
                # Generate file if not exists
                generated_users = await sync_to_async(list)(
                    GeneratedUser.objects.filter(bulk_request=bulk_request).order_by('username')
                )
                
                created_users = [f"username:{gen.username}, password:{gen.password}" for gen in generated_users]
                failed_users = []
                
                if bulk_request.status == 'failed' and bulk_request.error_message:
                    failed_users = bulk_request.error_message.split("; ")
                
                file_path = FileManager.save_request_file(request_id, bulk_request.prefix, created_users, failed_users)
            
            # Send file
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            filename = f"makonbook_users_{bulk_request.prefix}_ID{request_id}_{bulk_request.created_at.strftime('%Y%m%d')}.txt"
            document = BufferedInputFile(file_content, filename=filename)
            
            await callback.message.answer_document(
                document,
                caption=f"📁 <b>User Credentials File</b>\n\n"
                       f"<b>Request ID:</b> {request_id}\n"
                       f"<b>Prefix:</b> {bulk_request.prefix}\n"
                       f"<b>Total Users:</b> {bulk_request.count}\n"
                       f"<b>Status:</b> {bulk_request.status.title()}\n"
                       f"<b>Created:</b> {bulk_request.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
            
            await callback.answer("📁 File sent!")
            
        except Exception as e:
            logger.error(f"Error downloading request {request_id}: {e}")
            await callback.answer(f"❌ Error downloading file: {str(e)}")
    
    @staticmethod
    async def back_to_requests(callback: types.CallbackQuery):
        """Go back to requests list"""
        admin = await check_admin_privileges(callback.from_user.id)
        if not admin:
            await callback.answer("❌ Access denied.")
            return
        
        # Get total count for pagination
        total_requests = await sync_to_async(
            BulkUserRequest.objects.filter(telegram_admin=admin).count
        )()
        
        if total_requests == 0:
            await callback.message.edit_text("📊 No bulk creation requests found.")
        else:
            # Show first page
            await RequestHistoryHandler._show_requests_page(callback.message, admin, page=1, total_requests=total_requests)
        
        await callback.answer()


class UtilityHandler(BaseHandler):
    """Handler for utility functions like cancel"""
    
    @staticmethod
    async def cancel_operation(callback: types.CallbackQuery, state: FSMContext):
        """Cancel current operation"""
        admin = await check_admin_privileges(callback.from_user.id)
        if admin:
            keyboard = UtilityHandler.get_main_keyboard(admin.is_admin)
            await callback.message.edit_text("❌ Operation cancelled.")
            await callback.message.answer("Ready for next operation!", reply_markup=keyboard)
        
        await state.clear() 