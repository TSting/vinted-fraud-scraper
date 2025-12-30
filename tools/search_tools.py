import google.cloud.firestore as firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from typing import List, Dict, Any
from vision_client import VisionEmbeddingGenerator
from firestore_client import FirestoreClient
from app_config import get_config

# Persistent clients initialized once at module level to save latency
_VISION_CLIENT = None
_DB_CLIENT = None

def _get_clients():
    global _VISION_CLIENT, _DB_CLIENT
    if _VISION_CLIENT is None:
        _VISION_CLIENT = VisionEmbeddingGenerator()
    if _DB_CLIENT is None:
        _DB_CLIENT = FirestoreClient()
    return _VISION_CLIENT, _DB_CLIENT

def search_similar_products(image_bytes: bytes, query: str = None, limit: int = 5, auto_crop: bool = True) -> tuple[List[Dict[str, Any]], bool]:
    """
    Takes image bytes, generates an embedding (optionally guided by a query), 
    and finds the nearest matches in Firestore.
    
    Returns (results, was_cropped).
    """
    from image_utils import crop_screenshot_bottom
    
    was_cropped = False
    if auto_crop:
        image_bytes, was_cropped = crop_screenshot_bottom(image_bytes)
        if was_cropped:
            import logging
            logger = logging.getLogger("search_tools")
            logger.info("Image identified as screenshot and auto-cropped.")
    config = get_config()
    vision, db_client = _get_clients()
    
    from vertexai.vision_models import Image
    import logging
    logger = logging.getLogger("search_tools")
    
    logger.info(f"Generating embedding for {len(image_bytes)} bytes (Query context: '{query}')...")
    
    try:
        image = Image(image_bytes)
    except Exception as e:
        logger.error(f"Failed to create Image object: {e}")
        raise ValueError(f"Could not create Vertex AI Image from bytes: {e}")
    
    try:
        # Pass the user query to contextual_text to help the model focus on the right object
        embeddings = vision.model.get_embeddings(
            image=image,
            contextual_text=query,
            dimension=1408
        )
    except Exception as e:
        logger.error(f"Vertex AI Embedding Error: {str(e)}")
        raise
    
    if not embeddings or not embeddings.image_embedding:
        logger.warning("No embeddings returned from Vertex AI")
        return []
    
    query_vector = embeddings.image_embedding
    logger.info(f"✓ Generated embedding vector with {len(query_vector)} dimensions")

    # 2. Perform Vector Search in Firestore
    collection_name = config.get("FIRESTORE_PRODUCTS_COLLECTION", "products")
    logger.info(f"Querying Firestore collection: {collection_name}")
    collection = db_client.db.collection(collection_name)
    
    threshold = 0.6 # Similarity > 40% (Distance < 0.6) - Increased to 0.6 to support very noisy screenshots or distant matches
    
    try:
        vector_query = collection.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit,
            distance_result_field="vector_distance"
        )
    except Exception as e:
        logger.error(f"Firestore vector query error: {e}")
        raise
    
    results = []
    for doc in vector_query.stream():
        data = doc.to_dict()
        distance = data.get("vector_distance", 1.0)
        
        if distance > threshold:
            logger.info(f"Skipping result {doc.id} due to distance {distance:.3f} > {threshold}")
            continue
            
        # Add metadata to result
        data["doc_id"] = doc.id
        # distance is already in data because of distance_result_field="vector_distance"
        
        if "embedding" in data:
            del data["embedding"]
        results.append(data)
    
    logger.info(f"✓ Found {len(results)} relevant results from Firestore")
    return results, was_cropped
