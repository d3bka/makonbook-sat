"""
MakonBook SAT System - Telegram Bot
Professional modular bot structure with robust error handling
"""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties

import django
from django.conf import settings

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'satmakon.settings')
django.setup()

from .handlers import (
    StartHandler,
    HelpHandler,
    UserCreationHandler,
    GroupSelectionHandler,
    UserExecutionHandler,
    RequestHistoryHandler,
    UtilityHandler,
    UserCreationStates
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


class BotRoutes:
    """Central route configuration for all bot handlers"""
    
    @staticmethod
    def register_handlers():
        """Register all bot handlers with the dispatcher"""
        
        # Command handlers
        dp.message.register(
            StartHandler.start_command,
            Command("start")
        )
        
        # Text message handlers
        dp.message.register(
            HelpHandler.show_help,
            lambda message: message.text == "ℹ️ Help"
        )
        
        dp.message.register(
            UserCreationHandler.start_bulk_creation,
            lambda message: message.text == "🔄 Create Bulk Users"
        )
        
        dp.message.register(
            RequestHistoryHandler.show_my_requests,
            lambda message: message.text == "📊 My Requests"
        )
        
        # State-based message handlers
        dp.message.register(
            UserCreationHandler.process_prefix,
            StateFilter(UserCreationStates.waiting_for_prefix)
        )
        
        dp.message.register(
            UserCreationHandler.process_count,
            StateFilter(UserCreationStates.waiting_for_count)
        )
        
        # Callback query handlers
        dp.callback_query.register(
            GroupSelectionHandler.toggle_group,
            lambda c: c.data.startswith("group_")
        )
        
        dp.callback_query.register(
            GroupSelectionHandler.confirm_groups,
            lambda c: c.data == "confirm_groups"
        )
        
        dp.callback_query.register(
            UserExecutionHandler.create_users,
            lambda c: c.data == "create_users"
        )
        
        # Request history handlers
        dp.callback_query.register(
            RequestHistoryHandler.view_request_details,
            lambda c: c.data.startswith("view_request_")
        )
        
        dp.callback_query.register(
            RequestHistoryHandler.download_request_file,
            lambda c: c.data.startswith("download_request_")
        )
        
        dp.callback_query.register(
            RequestHistoryHandler.handle_pagination,
            lambda c: c.data.startswith("requests_page_")
        )
        
        dp.callback_query.register(
            RequestHistoryHandler.back_to_requests,
            lambda c: c.data == "back_to_requests"
        )
        
        # Add handler for noop callbacks (page indicators)
        dp.callback_query.register(
            lambda callback: callback.answer(),
            lambda c: c.data == "noop"
        )
        
        dp.callback_query.register(
            UtilityHandler.cancel_operation,
            lambda c: c.data == "cancel"
        )
        
        logger.info("All bot handlers registered successfully")


class BotMiddleware:
    """Middleware for error handling and logging"""
    
    @staticmethod
    async def error_handler(update: types.Update, exception: Exception) -> bool:
        """Global error handler for the bot"""
        logger.error(f"Error processing update {update.update_id}: {exception}")
        
        # Try to send error message to user if possible
        if update.message:
            try:
                await update.message.answer(
                    "❌ <b>System Error</b>\n\n"
                    "An unexpected error occurred. Please try again later.\n"
                    "If the problem persists, contact the administrator."
                )
            except Exception as e:
                logger.error(f"Failed to send error message: {e}")
        
        elif update.callback_query:
            try:
                await update.callback_query.answer("❌ System error occurred")
                await update.callback_query.message.answer(
                    "❌ <b>System Error</b>\n\n"
                    "An unexpected error occurred. Please try again later.\n"
                    "If the problem persists, contact the administrator."
                )
            except Exception as e:
                logger.error(f"Failed to send error message via callback: {e}")
        
        return True
    
    @staticmethod
    def setup_middleware():
        """Setup middleware for the dispatcher"""
        # Use correct aiogram v3 syntax for error handling
        dp.error.register(BotMiddleware.error_handler)
        logger.info("Error handling middleware setup complete")


class BotHealthCheck:
    """Health check utilities for the bot"""
    
    @staticmethod
    async def check_bot_health() -> bool:
        """Check if bot is healthy and can communicate with Telegram"""
        try:
            bot_info = await bot.get_me()
            logger.info(f"Bot health check passed. Bot: @{bot_info.username}")
            return True
        except Exception as e:
            logger.error(f"Bot health check failed: {e}")
            return False
    
    @staticmethod
    async def check_database_connection() -> bool:
        """Check if database connection is working"""
        try:
            from .models import TelegramAdmin
            from asgiref.sync import sync_to_async
            
            count = await sync_to_async(TelegramAdmin.objects.count)()
            logger.info(f"Database health check passed. {count} admin users found.")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


class BotStats:
    """Bot statistics and monitoring"""
    
    @staticmethod
    async def log_startup_stats():
        """Log startup statistics"""
        try:
            from .models import TelegramAdmin, BulkUserRequest
            from django.contrib.auth.models import User, Group
            from asgiref.sync import sync_to_async
            
            admin_count = await sync_to_async(TelegramAdmin.objects.count)()
            request_count = await sync_to_async(BulkUserRequest.objects.count)()
            user_count = await sync_to_async(User.objects.count)()
            group_count = await sync_to_async(Group.objects.count)()
            
            logger.info("=== Bot Startup Statistics ===")
            logger.info(f"Telegram Admins: {admin_count}")
            logger.info(f"Bulk Requests: {request_count}")
            logger.info(f"Total Users: {user_count}")
            logger.info(f"User Groups: {group_count}")
            logger.info("==============================")
            
        except Exception as e:
            logger.error(f"Failed to gather startup stats: {e}")


async def setup_bot():
    """Setup and configure the bot"""
    try:
        logger.info("Starting MakonBook Telegram Bot setup...")
        
        # Health checks
        logger.info("Performing health checks...")
        bot_healthy = await BotHealthCheck.check_bot_health()
        db_healthy = await BotHealthCheck.check_database_connection()
        
        if not bot_healthy:
            raise Exception("Bot health check failed")
        if not db_healthy:
            raise Exception("Database health check failed")
        
        # Setup middleware
        BotMiddleware.setup_middleware()
        
        # Register handlers
        BotRoutes.register_handlers()
        
        # Log startup stats
        await BotStats.log_startup_stats()
        
        logger.info("✅ MakonBook Telegram Bot setup completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Bot setup failed: {e}")
        return False


async def start_bot():
    """Start the bot polling"""
    try:
        logger.info("Starting bot polling...")
        
        # Delete webhook if any
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Start polling
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Error during bot polling: {e}")
        raise
    finally:
        # Cleanup
        logger.info("Cleaning up bot session...")
        await bot.session.close()


async def stop_bot():
    """Gracefully stop the bot"""
    try:
        logger.info("Stopping bot...")
        await dp.stop_polling()
        await bot.session.close()
        logger.info("✅ Bot stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")


async def main():
    """Main bot function"""
    try:
        # Setup bot
        setup_success = await setup_bot()
        if not setup_success:
            logger.error("❌ Bot setup failed, exiting...")
            return
        
        # Start bot
        await start_bot()
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, stopping bot...")
    except Exception as e:
        logger.error(f"❌ Fatal error in bot main: {e}")
    finally:
        await stop_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")