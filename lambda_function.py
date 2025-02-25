import os
import logging
from telegram import Bot
from telegram.error import TelegramError

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

def send_daily_message():
    """Sends the daily message to a specified topic in a group chat."""
    try:
        bot = Bot(token=TOKEN)
        message = """
        RULES REMINDER:
        1. CHECK IF THE CONTENT EXISTS BEFORE REQUESTING 🙏 search keywords to find content easily. It must match the movie/show title exactly
        2. Please send IMDB LINK for all requests. You can search for it on google
        3. Allow at least 2 days for requests to be fulfilled
        4. Refresh and check for the content after requesting
        5. Will react:
        👍 if available 
        👎 if not
        👀 if you did not follow step 1
        scheduled = scheduled to upload when available digitally
        """
        bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            message_thread_id=TOPIC_ID
        )
        logger.info("Message sent successfully.")
    except TelegramError as e:
        logger.error(f"Failed to send message: {e}")

def lambda_handler(event, context):
    """Lambda function entry point"""
    logger.info("Triggered daily message function.")
    send_daily_message()
    return {
        'statusCode': 200,
        'body': 'Message sent!'
    }
