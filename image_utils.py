import requests
import hashlib
import io
from PIL import Image as PILImage
from typing import Optional, List, Dict
import os
import json

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

def crop_screenshot_bottom(image_bytes: bytes, crop_percentage: float = 0.35) -> tuple[bytes, bool]:
    """
    Crops the bottom part of an image if it looks like a mobile screenshot (tall aspect ratio).
    Returns (processed_image_bytes, was_cropped).
    """
    if not image_bytes:
        return image_bytes, False
        
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        width, height = img.size
        aspect_ratio = height / width
        
        # Mobile screenshots typically have high aspect ratio (e.g., 2.16 for iPhone 15)
        # We check if it's taller than 1.5 to identify potential screenshots
        if aspect_ratio > 1.5:
            # Calculate the crop area
            new_height = int(height * (1 - crop_percentage))
            # Crop box: (left, top, right, bottom)
            cropped_img = img.crop((0, 0, width, new_height))
            
            # Save back to bytes
            img_byte_arr = io.BytesIO()
            # Preserve original format if possible
            fmt = img.format if img.format else "PNG"
            cropped_img.save(img_byte_arr, format=fmt)
            return img_byte_arr.getvalue(), True
            
        return image_bytes, False
    except Exception as e:
        print(f"  - Error during cropping check: {e}")
        return image_bytes, False

def detect_clothing_items(image_bytes: bytes) -> List[Dict]:
    """
    Uses Gemini to detect clothing items and accessories in the image.
    Returns a list of detected items with labels and bounding boxes.
    """
    if not image_bytes:
        return []

    try:
        from google import genai
        from google.genai import types
        
        # Initialize client (relying on environment variables for Vertex AI)
        client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT") or "ecom-agents",
            location=os.getenv("VERTEX_LOCATION") or "europe-west1"
        )
        
        prompt = """
        Detecteer alle afzonderlijke kledingstukken en modeaccessoires in deze afbeelding.
        Geef de resultaten terug als een JSON-lijst van objecten, elk met:
        - "label": een korte Nederlandse naam voor het item (bijv. "blouse", "trui", "broek", "rok", "schoenen")
        - "box_2d": [ymin, xmin, ymax, xmax] in genormaliseerde coördinaten (0-1000)
        - "description": een korte beschrijving in het Nederlands, inclusief kleur en stijl
        
        Retourneer alleen de JSON-lijst, niets anders.
        """
        
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        
        if not response or not response.text:
            return []
            
        items = json.loads(response.text)
        return items if isinstance(items, list) else []
        
    except Exception as e:
        print(f"  - Error during object detection: {e}")
        return []

def crop_to_box(image_bytes: bytes, box: List[int]) -> bytes:
    """
    Crops the image to a normalized bounding box [ymin, xmin, ymax, xmax].
    Coordinates are 0-1000.
    """
    try:
        img = PILImage.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        ymin, xmin, ymax, xmax = box
        
        # Convert normalized to pixel coordinates
        left = int(xmin * width / 1000)
        top = int(ymin * height / 1000)
        right = int(xmax * width / 1000)
        bottom = int(ymax * height / 1000)
        
        # Add a small margin (5%)
        margin_w = int((right - left) * 0.05)
        margin_h = int((bottom - top) * 0.05)
        
        left = max(0, left - margin_w)
        top = max(0, top - margin_h)
        right = min(width, right + margin_w)
        bottom = min(height, bottom + margin_h)
        
        cropped_img = img.crop((left, top, right, bottom))
        
        img_byte_arr = io.BytesIO()
        fmt = img.format if img.format else "PNG"
        cropped_img.save(img_byte_arr, format=fmt)
        return img_byte_arr.getvalue()
        
    except Exception as e:
        print(f"  - Error during cropping: {e}")
        return image_bytes
