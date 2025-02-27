import os
import logging
import requests
import boto3
import base64
from urllib.parse import quote
from botocore.exceptions import ClientError

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
DYNAMODB_TABLE = os.getenv("DYNAMODB_TABLE", "ContentCache")
RADARR_API_URL = os.getenv("RADARR_API_URL")
RADARR_API_KEY = os.getenv("RADARR_API_KEY")
SONARR_API_URL = os.getenv("SONARR_API_URL")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")
RADARR_USERNAME = os.getenv("RADARR_USERNAME")
RADARR_PASSWORD = os.getenv("RADARR_PASSWORD")
SONARR_USERNAME = os.getenv("SONARR_USERNAME")
SONARR_PASSWORD = os.getenv("SONARR_PASSWORD")

# Initialize DynamoDB Client
dynamodb = boto3.client('dynamodb')

# ======================
# Helper Function
# ======================

def get_basic_auth(username, password):
    """Base64 encodes the username and password for Basic Auth."""
    # Combine username and password
    auth_string = f"{username}:{password}"
    
    # Base64 encode
    base64_auth = base64.b64encode(auth_string.encode()).decode()
    
    # Return the Authorization header value
    return f"Basic {base64_auth}"


# Get Basic Auth Headers
RADARR_BASIC_AUTH = get_basic_auth(RADARR_USERNAME, RADARR_PASSWORD)
SONARR_BASIC_AUTH = get_basic_auth(SONARR_USERNAME, SONARR_PASSWORD)

# ======================
# DynamoDB Functions
# ======================

def batch_write_to_dynamodb(imdb_ids):
    """Batch write IMDb IDs to DynamoDB."""
    try:
        with boto3.resource('dynamodb').Table(DYNAMODB_TABLE).batch_writer() as batch:
            for imdb_id in imdb_ids:
                batch.put_item(
                    Item={'imdbId': imdb_id}
                )
        logger.info("Batch write to DynamoDB completed.")
    except ClientError as e:
        logger.error(f"Error writing to DynamoDB: {e}")

# ======================
# Radarr Functions
# ======================

def get_radarr_imdb_ids():
    """Get all IMDb IDs from Radarr with Basic Auth."""
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
            imdb_ids = [movie['imdbId'] for movie in movies if 'imdbId' in movie]
            logger.info(f"Found {len(imdb_ids)} IMDb IDs in Radarr.")
            return imdb_ids
        else:
            logger.error(f"Failed to get movies from Radarr. Status Code: {response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Error getting IMDb IDs from Radarr: {e}")
        return []

# ======================
# Sonarr Functions
# ======================

def get_sonarr_imdb_ids():
    """Get all IMDb IDs from Sonarr with Basic Auth."""
    try:
        url = f"{SONARR_API_URL}/series"
        headers = {
            'X-Api-Key': SONARR_API_KEY,
            'Authorization': SONARR_BASIC_AUTH
        }
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            shows = response.json()
            imdb_ids = [show['imdbId'] for show in shows if 'imdbId' in show]
            logger.info(f"Found {len(imdb_ids)} IMDb IDs in Sonarr.")
            return imdb_ids
        else:
            logger.error(f"Failed to get shows from Sonarr. Status Code: {response.status_code}")
        return []
    except Exception as e:
        logger.error(f"Error getting IMDb IDs from Sonarr: {e}")
        return []

# ======================
# Main Function
# ======================

def main():
    """Main function to populate DynamoDB with IMDb IDs."""
    logger.info("Starting IMDb ID population process.")
    
    # Get IMDb IDs from Radarr and Sonarr
    radarr_ids = get_radarr_imdb_ids()
    sonarr_ids = get_sonarr_imdb_ids()
    
    # Combine and remove duplicates
    all_imdb_ids = list(set(radarr_ids + sonarr_ids))
    logger.info(f"Total IMDb IDs to cache: {len(all_imdb_ids)}")
    
    # Batch write to DynamoDB
    batch_write_to_dynamodb(all_imdb_ids)
    logger.info("Finished IMDb ID population process.")

if __name__ == "__main__":
    main()
