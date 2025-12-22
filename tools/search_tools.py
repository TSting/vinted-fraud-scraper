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
    image = Image(image_bytes)
    embeddings = vision.model.get_embeddings(
        image=image,
        dimension=1408 # Native dimension for multimodalembedding@001
    )
    
    if not embeddings or not embeddings.image_embedding:
        return []
    
    query_vector = embeddings.image_embedding

    # 2. Perform Vector Search in Firestore
    collection_name = config.get("FIRESTORE_PRODUCTS_COLLECTION", "products")
    collection = db_client.db.collection(collection_name)
    
    # Use find_nearest for vector search
    # Requires a vector index on the 'embedding' field
    vector_query = collection.find_nearest(
        vector_field="embedding",
        query_vector=Vector(query_vector),
        distance_measure=DistanceMeasure.COSINE,
        limit=limit
    )
    
    results = []
    for doc in vector_query.stream():
        data = doc.to_dict()
        # Remove the large embedding vector from result for cleaner display
        if "embedding" in data:
            del data["embedding"]
        results.append(data)
        
    return results
