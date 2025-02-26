import os
import logging
import re
import json
import boto3
from telegram import Bot, Update
from telegram.ext import Dispatcher, MessageHandler, Filters
from telegram.error import TelegramError
from botocore.exceptions import ClientError

# Setup Logging
logger = logging.getLogger()
logger.setLevel("INFO")

# Load environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")
WHITELISTED_USERNAME = os.getenv("WHITELISTED_USERNAME")

# Initialize Bot and SSM Client
bot = Bot(token=TOKEN)
ssm_client = boto3.client('ssm')

# Parameter Store Path
LAST_MESSAGE_ID_PARAM = '/vik-requests-bot/last_message_id'

def get_last_message_id():
    """Retrieve the last processed message ID from SSM Parameter Store."""
    try:
        response = ssm_client.get_parameter(Name=LAST_MESSAGE_ID_PARAM)
        last_message_id = int(response['Parameter']['Value'])
        logger.info(f"Retrieved last_message_id: {last_message_id}")
        return last_message_id
    except ClientError as e:
        logger.error(f"Error getting last_message_id: {e}")
        return 0

def set_last_message_id(message_id):
    """Store the last processed message ID in SSM Parameter Store."""
    try:
        ssm_client.put_parameter(
            Name=LAST_MESSAGE_ID_PARAM,
            Value=str(message_id),
            Type='String',
            Overwrite=True
        )
        logger.info(f"Stored last_message_id: {message_id}")
    except ClientError as e:
        logger.error(f"Error setting last_message_id: {e}")

def send_daily_message():
    """Sends the daily rules reminder message to a specified topic in a group chat."""
    try:
        message = """
        🚨 **RULES REMINDER:** 🚨
        1. **CHECK IF THE CONTENT EXISTS BEFORE REQUESTING** 🙏 Search keywords to find content easily. It must match the movie/show title exactly.
        2. **Please only send an IMDB LINK for requests.** You can search for it on Google.
        3. **Allow at least 2 days for requests to be fulfilled.**
        4. **Refresh and check for the content after requesting.**
        5. **Will react:**
           - 👍 if available 
           - 👎 if not
           - 👀 if you did not follow step 1
           - scheduled = scheduled to upload when available digitally
        """
        
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            message_thread_id=TOPIC_ID,
            parse_mode="Markdown"
        )
        logger.info("Rules reminder message sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def is_user_admin(user_id):
    """Checks if the user is an admin in the group chat."""
    try:
        admins = bot.get_chat_administrators(chat_id=CHAT_ID)
        for admin in admins:
            if admin.user.id == user_id:
                logger.info(f"User {user_id} is an admin.")
                return True
        logger.info(f"User {user_id} is NOT an admin.")
        return False
    except TelegramError as e:
        logger.error(f"Failed to get admin list: {e}")
        return False

def check_for_imdb_link(update: Update, context):
    """Checks messages for an IMDb link and responds if none is found."""
    message = update.message.text
    user_id = update.message.from_user.id
    username = update.message.from_user.username  # Get the sender's username
    message_id = update.message.message_id
    message_thread_id = update.message.message_thread_id

    # Log the username for debugging
    logger.debug(f"Message from @{username}: {message}")

    # Check if the message is in the right topic
    if message_thread_id == int(TOPIC_ID):
        # Check if the sender is whitelisted by username
        if username == WHITELISTED_USERNAME:
            logger.info(f"User @{username} is whitelisted. No response needed.")
            return
        
        # Only process if it's the latest message (using SSM)
        last_message_id = get_last_message_id()
        if message_id <= last_message_id:
            logger.info("Old or duplicate message detected. No response needed.")
            return
        
        # Update the last processed message ID
        set_last_message_id(message_id)
        
        # Check if the message contains an IMDb link
        if not re.search(r'imdb\.com/title/', message, re.IGNORECASE):
            # Reply with "Please read the rules"
            update.message.reply_text("⚠️ Please check the pinned message for rules. Only IMDB links are permitted in this chat. For anything else, please use the general support chat. Thank you! 🙏")
            logger.info("Responded with 'Please read the rules.'")

def lambda_handler(event, context):
    """Lambda function entry point"""
    logger.info("Triggered Lambda function.")
    logger.info(f"Incoming event: {event}")
    
    # Handle daily message
    if event.get("source") == "aws.events":
        send_daily_message()
    
    # Handle incoming messages
    if "body" in event:
        try:
            update = Update.de_json(json.loads(event["body"]), bot)
            dispatcher = Dispatcher(bot, None, workers=0)
            dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, check_for_imdb_link))
            dispatcher.process_update(update)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
    
    return {
        'statusCode': 200,
        'body': 'Function executed successfully!'
    }
