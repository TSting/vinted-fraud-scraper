import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

REQUIRED_VARS = [
    "IN_RIVER_BASE_URL",
    "ECOM_INRIVER_API_KEY"
]

def get_config():
    """
    Validates and returns configuration from environment variables.
    """
    config = {}
    missing_vars = []

    for var in REQUIRED_VARS:
        value = os.getenv(var)
        if not value:
            missing_vars.append(var)
        config[var] = value

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # Optional variables with defaults
    # Optional variables with defaults
    config["INRIVER_IMAGE_FIELD"] = os.getenv("INRIVER_IMAGE_FIELD", "MainImage")
    config["BATCH_SIZE"] = int(os.getenv("BATCH_SIZE", "500"))
    
    # GCP Config
    config["GOOGLE_CLOUD_PROJECT"] = os.getenv("GOOGLE_CLOUD_PROJECT") or "ecom-agents"
    config["VERTEX_LOCATION"] = os.getenv("VERTEX_LOCATION", "europe-west1")
    config["FIRESTORE_PRODUCTS_COLLECTION"] = os.getenv("FIRESTORE_PRODUCTS_COLLECTION", "products")
    config["FIRESTORE_PROGRESS_COLLECTION"] = os.getenv("FIRESTORE_PROGRESS_COLLECTION", "batchProgress")
    config["FIRESTORE_ERRORS_COLLECTION"] = os.getenv("FIRESTORE_ERRORS_COLLECTION", "processingErrors")
    
    return config
