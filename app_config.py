import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_config():
    """
    Validates and returns configuration from environment variables.
    """
    config = {}
    
    # GCP Config
    config["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT") or "ecom-agents"
    config["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west1")
    
    # Vinted Search URL (Optional override)
    config["VINTED_SEARCH_URL"] = os.getenv("VINTED_SEARCH_URL", "https://www.vinted.nl/catalog?status_ids%5B%5D=6&page=1&time=1768305966&brand_ids%5B%5D=40883&search_by_image_uuid=&order=newest_first")
    
    return config
