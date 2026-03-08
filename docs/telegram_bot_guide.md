# 🤖 MakonBook Telegram Bot Guide

## ✅ **BOT STATUS: FULLY OPERATIONAL**

The MakonBook Telegram Bot is now **running successfully** and ready to create bulk users!

### 🔧 **Bot Information**
- **Bot Username**: `@makonbook_bot`
- **Bot ID**: `8212951087`
- **Status**: ✅ Active and polling
- **Location**: Running on server at `/home/satmakon/makonbook/`

## 👥 **AUTHORIZED ADMINS**

The following Telegram user IDs have **full admin access**:
- **6795116083** - Admin privileges
- **1333069703** - Admin privileges  
- **7620009282** - Admin privileges

## 🚀 **HOW TO USE THE BOT**

### **Step 1: Start the Bot**
1. Open Telegram
2. Search for `@makonbook_bot`
3. Send `/start` command
4. You should see the welcome message with menu buttons

### **Step 2: Create Bulk Users**
1. Click **"🔄 Create Bulk Users"** button
2. Follow the **3-step process**:

#### **📝 Step 1: Username Prefix**
- Enter a prefix (2-10 characters, letters/numbers only)
- **Examples**:
  - `student` → creates student001, student002, etc.
  - `test2025` → creates test2025001, test2025002, etc.
  - `sat` → creates sat001, sat002, etc.

#### **📝 Step 2: Number of Users**
- Enter number between **1-50**
- **Examples**:
  - Enter `10` to create 10 users
  - Enter `25` to create 25 users

#### **📝 Step 3: Select Groups**
- Choose which user groups the new accounts should belong to
- You can select multiple groups or none
- Click **"✅ Confirm Groups"** when done

#### **📝 Step 4: Confirmation**
- Review the summary
- Click **"✅ Create Users"** to proceed
- Wait for creation to complete

### **Step 3: View Results**
- The bot will show you all created usernames and passwords
- **Example output**:
```
✅ Users Created Successfully!

📊 Summary:
• Created: 10 users
• Failed: 0 users

👥 Created Users:
student001 - aB3kL8pQ
student002 - xR9mN4pT
student003 - kP7qS2wE
...
```

## 📋 **BOT FEATURES**

### **🔄 Bulk User Creation**
- Create **1-50 users** per request
- Usernames follow pattern: `[prefix][001-999]`
- Passwords are **8 characters** (letters + numbers)
- Users can be assigned to **multiple groups**

### **📊 Request History**
- Click **"📊 My Requests"** to view your last 10 creation requests
- Track status: Pending, Processing, Completed, Failed
- View creation dates and details

### **ℹ️ Help System**
- Click **"ℹ️ Help"** for detailed instructions
- Contains examples and formatting rules
- Explains all bot features

## 🛠 **MANAGEMENT COMMANDS**

### **Start/Stop Bot**
```bash
# Start the bot
./start_telegram_bot.sh

# Stop the bot
./stop_telegram_bot.sh

# Check if bot is running
ps aux | grep run_telegram_bot
```

### **View Bot Logs**
```bash
# Real-time logs
tail -f logs/telegram_bot.log

# Last 20 log entries
tail -20 logs/telegram_bot.log
```

### **Add New Admin Users**
```bash
python manage.py shell
```
```python
from apps.telegram_bot.models import TelegramAdmin

# Add new admin (replace 123456789 with actual Telegram ID)
admin = TelegramAdmin.objects.create(
    telegram_id=123456789,
    username="new_admin",
    first_name="Admin Name", 
    is_admin=True,
    is_support=True,
    is_active=True
)
```

## 🔐 **SECURITY FEATURES**

### **Access Control**
- ✅ Only authorized Telegram IDs can use the bot
- ✅ All actions are logged with user identification
- ✅ Admin/support role separation
- ✅ Request history tracking

### **User Creation Security**
- ✅ Username uniqueness validation
- ✅ Password complexity (8 chars, alphanumeric)
- ✅ Group permission validation
- ✅ Transaction-based creation (all-or-nothing)

### **Bot Security**
- ✅ Token stored in environment variables
- ✅ Django integration for database access
- ✅ Error handling and logging
- ✅ Proper session management

## 📊 **USAGE EXAMPLES**

### **Example 1: Create 10 Student Accounts**
1. Send `/start` to bot
2. Click "🔄 Create Bulk Users"
3. Enter prefix: `student`
4. Enter count: `10`
5. Select groups (optional)
6. Confirm creation

**Result**: Creates student001 through student010

### **Example 2: Create 25 Test Accounts**
1. Click "🔄 Create Bulk Users"
2. Enter prefix: `test2025`
3. Enter count: `25`
4. Select "Tester" group
5. Confirm creation

**Result**: Creates test2025001 through test2025025, all in "Tester" group

## 🐛 **TROUBLESHOOTING**

### **Bot Not Responding**
```bash
# Check if bot is running
ps aux | grep run_telegram_bot

# Restart bot if needed
./stop_telegram_bot.sh
./start_telegram_bot.sh
```

### **"Access Denied" Message**
- Verify your Telegram ID is in the admin list
- Contact system administrator to add your ID

### **User Creation Fails**
- Check if usernames already exist
- Verify group permissions
- Check bot logs: `tail -20 logs/telegram_bot.log`

### **Environment Issues**
```bash
# Check environment variables
source venv/bin/activate
export $(cat .env | grep -v "^#" | xargs)
echo $TELEGRAM_BOT_TOKEN
```

## 📞 **SUPPORT**

### **Current Bot Status**
- ✅ **Bot Running**: Active and responsive
- ✅ **Database**: Connected to PostgreSQL
- ✅ **Logging**: All actions logged to `logs/telegram_bot.log`
- ✅ **Admin Users**: 3 authorized users configured

### **For Technical Issues**
1. Check bot logs: `tail -20 logs/telegram_bot.log`
2. Verify bot is running: `ps aux | grep run_telegram_bot`
3. Test database connection through Django admin
4. Contact system administrator if issues persist

**🎯 The Telegram bot is now fully operational and ready for bulk user creation!**