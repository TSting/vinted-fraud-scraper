import requests
import hashlib
import io
from PIL import Image as PILImage
from typing import Optional

def download_image(url: str, timeout: int = 15) -> Optional[bytes]:
    """
    Downloads an image from a URL.
    Returns bytes if successful and it is an image, None otherwise.
    """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        
        content_type = response.headers.get("Content-Type", "").lower()
        if "video" in content_type or "mp4" in content_type:
            print(f"  - Skip: Asset is a video ({content_type})")
            return None
            
        return response.content
    except requests.RequestException as e:
        print(f"  - Error downloading {url}: {e}")
        return None

def is_valid_image(image_bytes: bytes) -> bool:
    """
    Checks if the bytes represent a valid, openable image.
    """
    if not image_bytes:
        return False
    try:
        with PILImage.open(io.BytesIO(image_bytes)) as img:
            img.verify()
        return True
    except Exception:
        return False

def calculate_image_hash(image_bytes: bytes) -> str:
    """
    Calculates SHA256 hash of image bytes.
    """
    return hashlib.sha256(image_bytes).hexdigest()
