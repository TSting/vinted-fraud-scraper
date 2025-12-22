import math
import google.cloud.firestore as firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from typing import List, Dict, Any
from vision_client import VisionEmbeddingGenerator
from firestore_client import FirestoreClient
from app_config import get_config

def search_similar_products(image_bytes: bytes, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Takes image bytes, generates an embedding, and finds the nearest matches in Firestore.
    """
    config = get_config()
    vision = VisionEmbeddingGenerator()
    db_client = FirestoreClient()
    
    # 1. Generate Embedding from Bytes
    # Note: VisionEmbeddingGenerator.get_embedding currently takes a URL
    # I should update it or use the model directly here.
    # Actually, let's update vision_client.py to support bytes.
    
    from vertexai.vision_models import Image
    import logging
    logger = logging.getLogger("search_tools")
    
    logger.info(f"Generating embedding for {len(image_bytes)} bytes of type {type(image_bytes)}...")
    
    try:
        image = Image(image_bytes)
    except Exception as e:
        logger.error(f"Failed to create Image object: {e}")
        raise ValueError(f"Could not create Vertex AI Image from bytes: {e}")
    
    try:
        embeddings = vision.model.get_embeddings(
            image=image,
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
    
    # Use find_nearest for vector search
    # Requires a vector index on the 'embedding' field
    try:
        vector_query = collection.find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_vector),
            distance_measure=DistanceMeasure.COSINE,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Firestore vector query error: {e}")
        raise
    
    results = []
    for doc in vector_query.stream():
        data = doc.to_dict()
        # Remove the large embedding vector from result for cleaner display
        if "embedding" in data:
            del data["embedding"]
        results.append(data)
    
    logger.info(f"✓ Found {len(results)} results from Firestore")
    
    # 3. Fallback: Manual Cosine Similarity Scan
    if not results:
        logger.info("Fallback: Performing in-memory similarity scan...")
        all_docs = collection.limit(500).stream()
        
        candidates = []
        for doc in all_docs:
            data = doc.to_dict()
            if "embedding" in data:
                # Calculate cosine similarity
                emb = data["embedding"]
                
                # Pure Python cosine similarity
                dot_product = sum(a * b for a, b in zip(query_vector, emb))
                norm_a = math.sqrt(sum(a * a for a in query_vector))
                norm_b = math.sqrt(sum(b * b for b in emb))
                
                if norm_a > 0 and norm_b > 0:
                    similarity = dot_product / (norm_a * norm_b)
                    data["_similarity"] = similarity
                    # Remove large embedding for output
                    del data["embedding"]
                    candidates.append(data)
        
        # Sort by similarity descending
        candidates.sort(key=lambda x: x.get("_similarity", 0), reverse=True)
        results = candidates[:limit]
        logger.info(f"✓ Fallback found {len(results)} results via manual scan")

    return results
