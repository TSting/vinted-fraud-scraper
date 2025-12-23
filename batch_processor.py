import time
from typing import List, Dict, Any
from inriver_client import InRiverClient
from vision_client import VisionEmbeddingGenerator
from firestore_client import FirestoreClient
from image_utils import download_image, calculate_image_hash
from app_config import get_config

class BatchProcessor:
    def __init__(self, dry_run: bool = False):
        self.config = get_config()
        self.inriver = InRiverClient(self.config["IN_RIVER_BASE_URL"], self.config["ECOM_INRIVER_API_KEY"])
        self.vision = VisionEmbeddingGenerator()
        self.db = FirestoreClient()
        self.dry_run = dry_run
        
    def process_batch(self, start_index: int, limit: int) -> Dict[str, Any]:
        """
        Processes a single batch of products.
        """
        stats = {
            "batch_start": start_index,
            "processed": 0,
            "skipped": 0,
            "updated": 0,
            "failed": 0
        }
        
        formula = self.config.get("INRIVER_FILTER_FORMULA", "C")
        min_year = self.config.get("INRIVER_FILTER_MIN_YEAR", 2025)
        
        print(f"--- Processing Batch: start={start_index}, limit={limit} (Filter: {formula}, Year >= {min_year}) ---")
        
        # 1. Fetch products from InRiver with filters
        try:
            data_criteria = [
                {
                    "fieldTypeId": "ItemBusinessFormula",
                    "value": formula,
                    "operator": "Equal"
                },
                {
                    "fieldTypeId": "ItemSeasonYear",
                    "value": min_year,
                    "operator": "GreaterThanOrEqual"
                }
            ]
            products = self.inriver.get_products(start_index, limit, data_criteria=data_criteria)
        except Exception as e:
            print(f"Failed to fetch batch from InRiver: {e}")
            stats["failed"] = limit
            return stats

        if not products:
            print("No products found in this range.")
            return stats

        for product in products:
            stats["processed"] += 1
            entity_id = product.get("entity_id")
            pmc_name = product.get("ProductNameCommercial")
            
            # Use configured image field
            image_field = self.config.get("INRIVER_IMAGE_FIELD", "MainImage")
            image_url = product.get(image_field) or product.get("MainImage")

            if not image_url:
                print(f"[{entity_id}] Skip: No image URL found.")
                stats["skipped"] += 1
                continue

            try:
                # 2. Incremental check via Hash
                # Download and hash immediately (we need it for skip check)
                image_bytes = download_image(image_url)
                if not image_bytes:
                    raise ValueError(f"Could not download image from {image_url}")
                
                current_hash = calculate_image_hash(image_bytes)
                
                # Check Firestore
                existing_doc = self.db.get_product(entity_id)
                if existing_doc and existing_doc.get("image_hash") == current_hash:
                    # Skip if hash matches
                    print(f"[{entity_id}] Skip: Image hash unchanged ({current_hash[:8]}...)")
                    stats["skipped"] += 1
                    continue

                # 3. Generate Embedding (if not dry run)
                print(f"[{entity_id}] Processing: {pmc_name}...")
                embedding = None
                if not self.dry_run:
                    embedding = self.vision.get_embedding(image_url)
                    if not embedding:
                        raise ValueError("Failed to generate embedding")
                
                # 4. Upsert to Firestore
                if not self.dry_run:
                    product_data = {
                        "entity_id": entity_id,
                        "name": pmc_name,
                        "image_url": image_url,
                        "image_hash": current_hash,
                        "embedding": embedding,
                        "last_updated": time.time()
                    }
                    self.db.upsert_product(product_data)
                    stats["updated"] += 1
                    print(f"[{entity_id}] ✅ Success.")
                else:
                    print(f"[{entity_id}] Dry-run: Embedding generated (simulated) and stored (simulated).")
                    stats["updated"] += 1

            except Exception as e:
                print(f"[{entity_id}] ❌ Error: {e}")
                stats["failed"] += 1
                # Log error to Firestore
                if not self.dry_run:
                    error_doc = {
                        "entity_id": entity_id,
                        "error_message": str(e),
                        "timestamp": time.time()
                    }
                    try:
                        self.db.db.collection(self.config["FIRESTORE_ERRORS_COLLECTION"]).add(error_doc)
                    except:
                        pass # Ignore secondary errors during error logging

        return stats

    def run(self, total_limit: int = 500):
        """
        Runs the full batch process up to total_limit.
        """
        batch_size = 50 # Internal loop batch size (can be smaller than CLI arg for safety)
        processed_so_far = 0
        
        overall_stats = {
            "total_processed": 0,
            "total_updated": 0,
            "total_skipped": 0,
            "total_failed": 0,
            "start_time": time.time()
        }

        while processed_so_far < total_limit:
            current_batch_limit = min(batch_size, total_limit - processed_so_far)
            batch_stats = self.process_batch(processed_so_far, current_batch_limit)
            
            overall_stats["total_processed"] += batch_stats["processed"]
            overall_stats["total_updated"] += batch_stats["updated"]
            overall_stats["total_skipped"] += batch_stats["skipped"]
            overall_stats["total_failed"] += batch_stats["failed"]
            
            processed_so_far += current_batch_limit
            if batch_stats["processed"] < current_batch_limit:
                # No more products
                break
        
        overall_stats["end_time"] = time.time()
        duration = overall_stats["end_time"] - overall_stats["start_time"]
        
        print("\n" + "="*30)
        print("BATCH PROCESSING COMPLETE")
        print(f"Duration: {duration:.2f}s")
        print(f"Processed: {overall_stats['total_processed']}")
        print(f"Updated:   {overall_stats['total_updated']}")
        print(f"Skipped:   {overall_stats['total_skipped']}")
        print(f"Failed:    {overall_stats['total_failed']}")
        print("="*30)
        
        return overall_stats
