import os
import vertexai
from vertexai.vision_models import MultiModalEmbeddingModel, Image
from typing import List, Optional
from app_config import get_config
from image_utils import download_image
import io

class VisionEmbeddingGenerator:
    def __init__(self):
        config = get_config()
        self.project_id = config.get("GOOGLE_CLOUD_PROJECT")
        self.location = config.get("VERTEX_LOCATION", "europe-west1")
        
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT is required for VisionEmbeddingGenerator")

        vertexai.init(project=self.project_id, location=self.location)
        # Using multimodalembedding model which supports 1024 dimensions
        self.model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")

    def get_embedding(self, image_bytes: bytes) -> Optional[List[float]]:
        """
        Generates 1408-dimensional embedding for the given image bytes.
        """
        try:
            if not image_bytes:
                return None

            # Create Vertex AI Image object from bytes
            image = Image(image_bytes)

            # Generate embedding with dimension=1408
            embeddings = self.model.get_embeddings(
                image=image,
                dimension=1408
            )
            
            if embeddings and embeddings.image_embedding:
                return embeddings.image_embedding
            return None

        except Exception as e:
            print(f"Error generating embedding: {e}")
            return None
