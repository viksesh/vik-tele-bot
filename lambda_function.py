import os
import logging
import re
import json
import requests
import base64
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
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE")
RADARR_API_URL = os.getenv("RADARR_API_URL")
RADARR_API_KEY = os.getenv("RADARR_API_KEY")
SONARR_API_URL = os.getenv("SONARR_API_URL")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")
OMDB_API_KEY = os.getenv("OMDB_API_KEY")
RADARR_USERNAME = os.getenv("RADARR_USERNAME")
RADARR_PASSWORD = os.getenv("RADARR_PASSWORD")
SONARR_USERNAME = os.getenv("SONARR_USERNAME")
SONARR_PASSWORD = os.getenv("SONARR_PASSWORD")

# Initialize Bot and SSM + Dynamo Client
bot = Bot(token=TOKEN)
ssm_client = boto3.client('ssm')
dynamodb = boto3.client('dynamodb')

# Parameter Store Path
LAST_MESSAGE_ID_PARAM = '/vik-requests-bot/last_message_id'

# ======================
# Helper Function
# ======================

def get_basic_auth(username, password):
    """Base64 encodes the username and password for Basic Auth."""

    auth_string = f"{username}:{password}"
    base64_auth = base64.b64encode(auth_string.encode()).decode()
    return f"Basic {base64_auth}"

# Get Basic Auth Headers
RADARR_BASIC_AUTH = get_basic_auth(RADARR_USERNAME, RADARR_PASSWORD)
SONARR_BASIC_AUTH = get_basic_auth(SONARR_USERNAME, SONARR_PASSWORD)

# ======================
# Caching Functions
# ======================

def is_cached_in_dynamodb(imdb_id):
    """Check if the IMDb ID is already cached in DynamoDB."""
    try:
        response = dynamodb.get_item(
            TableName=DYNAMODB_TABLE,
            Key={
                'imdbId': {'S': imdb_id}
            }
        )
        return 'Item' in response
    except Exception as e:
        logger.error(f"Error checking cache in DynamoDB: {e}")
        return False


def cache_in_dynamodb(imdb_id):
    """Cache the IMDb ID in DynamoDB forever."""
    try:
        dynamodb.put_item(
            TableName=DYNAMODB_TABLE,
            Item={
                'imdbId': {'S': imdb_id}
            }
        )
        logger.info(f"Cached IMDb ID {imdb_id} in DynamoDB.")
    except Exception as e:
        logger.error(f"Error caching IMDb ID in DynamoDB: {e}")


# ======================
# OMDb Type Check
# ======================

def get_imdb_type(imdb_id):
    """Check if the IMDb ID is for a Movie or Series using OMDb API."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        }
        url = f"https://www.omdbapi.com/?i={imdb_id}&apikey=78cf3bda"
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            imdb_type = data.get('Type', '').lower()
            logger.info(f"IMDb ID {imdb_id} is a {imdb_type}.")
            return imdb_type
        else:
            logger.error(f"Failed to get IMDb type from OMDb. Status Code: {response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error getting IMDb type: {e}")
        return None

# ======================
# Radarr and Sonarr Checks
# ======================

def check_radarr_for_movie(imdb_id):
    """Check Radarr for an existing movie by IMDb ID using a Set for fast lookup."""
    # Check DynamoDB cache first
    if is_cached_in_dynamodb(imdb_id):
        logger.info(f"IMDb ID {imdb_id} is cached as existing in Radarr.")
        return True
    
    # If not cached, call Radarr API
    try:
        logger.info({RADARR_API_URL})
        logger.info({RADARR_BASIC_AUTH})
        url = f"{RADARR_API_URL}/movie"
        headers = {
            'X-Api-Key': RADARR_API_KEY,
            'Authorization': RADARR_BASIC_AUTH
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            movies = response.json()
            # Create a set of IMDb IDs for fast lookup
            imdb_ids = {movie['imdbId'] for movie in movies if 'imdbId' in movie}
            
            # Check if the IMDb ID is in the set
            if imdb_id in imdb_ids:
                logger.info(f"Movie already exists in Radarr for IMDb ID: {imdb_id}")
                # Cache the result in DynamoDB
                cache_in_dynamodb(imdb_id)
                return True
            else:
                logger.info(f"Movie not found in Radarr for IMDb ID: {imdb_id}")
                return False
        else:
            logger.error(f"Failed to get movies from Radarr. Status Code: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Error checking Radarr: {e}")
        return False


def check_sonarr_for_show(imdb_id):
    """Check Sonarr for an existing show by IMDb ID using a Set for fast lookup."""
    # Check DynamoDB cache first
    if is_cached_in_dynamodb(imdb_id):
        logger.info(f"IMDb ID {imdb_id} is cached as existing in Sonarr.")
        return True
    
    # If not cached, call Sonarr API
    try:
        url = f"{SONARR_API_URL}/series"
        headers = {
            'X-Api-Key': SONARR_API_KEY,
            'Authorization': SONARR_BASIC_AUTH
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            shows = response.json()
            # Create a set of IMDb IDs for fast lookup
            imdb_ids = {show['imdbId'] for show in shows if 'imdbId' in show}
            
            # Check if the IMDb ID is in the set
            if imdb_id in imdb_ids:
                logger.info(f"Show already exists in Sonarr for IMDb ID: {imdb_id}")
                # Cache the result in DynamoDB
                cache_in_dynamodb(imdb_id)
                return True
            else:
                logger.info(f"Show not found in Sonarr for IMDb ID: {imdb_id}")
                return False
        else:
            logger.error(f"Failed to get shows from Sonarr. Status Code: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Error checking Sonarr: {e}")
        return False

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

def check_for_imdb_link(update: Update, context):
    """Checks messages for an IMDb link and responds if none is found."""
    message = update.message.text
    username = update.message.from_user.username  # Get the sender's username
    message_id = update.message.message_id
    message_thread_id = update.message.message_thread_id

    # Log the username for debugging
    logger.debug(f"Message from @{username}: {message}")

    # Check if the message is in the right topic
    if message_thread_id == int(TOPIC_ID):
        # Check if the sender is whitelisted by username TODO uncomment!
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
        else: # A valid imdb link was sent, check if the content already exists or not.
            match = re.search(r'imdb\.com/title/(tt\d+)', message, re.IGNORECASE)
            if match:
                imdb_id = match.group(1)
                imdb_type = get_imdb_type(imdb_id)
                if imdb_type == "movie":
                    if check_radarr_for_movie(imdb_id):
                        update.message.reply_text("✅ Movie already exists or has been scheduled. Please check the pinned message for rules and tips for searching.")
                    else:
                        return
                elif imdb_type == "series":
                    if check_sonarr_for_show(imdb_id):
                        update.message.reply_text("✅ Series already exists or has been scheduled. Please check the pinned message for rules and tips for searching.")
                    else:
                        return
                elif imdb_type is None:
                    return
                else:
                    update.message.reply_text("⚠️ The IMDb link is not a valid movie or show.")


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
