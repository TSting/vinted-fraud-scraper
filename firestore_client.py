from google.cloud import firestore
from typing import Optional, Dict, Any
from app_config import get_config

class FirestoreClient:
    def __init__(self):
        config = get_config()
        self.project_id = config.get("GOOGLE_CLOUD_PROJECT")
        self.database = config.get("FIRESTORE_DATABASE", "visualproduct")
        self.products_collection = config.get("FIRESTORE_PRODUCTS_COLLECTION", "products")
        self.progress_collection = config.get("FIRESTORE_PROGRESS_COLLECTION", "batchProgress")
        self.errors_collection = config.get("FIRESTORE_ERRORS_COLLECTION", "processingErrors")
        
        self.db = firestore.Client(project=self.project_id, database=self.database)

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a product document by ID.
        """
        doc_ref = self.db.collection(self.products_collection).document(str(product_id))
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def upsert_product(self, product_data: Dict[str, Any]) -> None:
        """
        Upserts (creates or updates) a product document.
        product_data must contain 'entity_id' or 'id' to be used as document key.
        """
        # Use entity_id as key
        p_id = product_data.get('entity_id') or product_data.get('id')
        if not p_id:
            raise ValueError("Product data must contain 'entity_id' or 'id'")
            
        doc_ref = self.db.collection(self.products_collection).document(str(p_id))
        # Set with merge=True to avoid overwriting unrelated fields if any
        doc_ref.set(product_data, merge=True)
