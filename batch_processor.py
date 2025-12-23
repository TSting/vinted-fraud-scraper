import time
from typing import List, Dict, Any
from inriver_client import InRiverClient
from vision_client import VisionEmbeddingGenerator
from firestore_client import FirestoreClient
from image_utils import download_image, calculate_image_hash, is_valid_image
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
        Processes a single batch of Items.
        Each Item may have multiple images; each image becomes a searchable document.
        """
        stats = {
            "batch_start": start_index,
            "items_processed": 0,
            "images_indexed": 0,
            "skipped": 0,
            "failed": 0
        }
        
        formula = self.config.get("INRIVER_FILTER_FORMULA", "C")
        min_year = self.config.get("INRIVER_FILTER_MIN_YEAR", 2025)
        
        print(f"--- Processing Batch: start={start_index}, limit={limit} (Filter: {formula}, Year >= {min_year}) ---")
        
        # 1. Fetch Items from InRiver with filters
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
            items = self.inriver.get_products(start_index, limit, data_criteria=data_criteria)
        except Exception as e:
            print(f"Failed to fetch batch from InRiver: {e}")
            stats["failed"] = limit
            return stats

        if not items:
            print("No items found in this range.")
            return stats

        for item in items:
            stats["items_processed"] += 1
            item_id = item.get("entity_id")
            item_fields = item.get("item_fields", {})
            product_fields = item.get("product_fields", {})
            image_urls = item.get("image_urls", [])
            
            item_code = item_fields.get("ItemCode", "N/A")
            # Resolve name from nested dictionary (Product Name)
            names = product_fields.get("ProductNameCommercial", {})
            if isinstance(names, dict):
                p_name = names.get("nl-NL") or names.get("en-GB") or "Naamloos"
            else:
                p_name = str(names) or "Naamloos"

            if not image_urls:
                print(f"[Item {item_id}] Skip: No image URLs found.")
                stats["skipped"] += 1
                continue

            print(f"[Item {item_id} | {item_code}] Processing {len(image_urls)} images for: {p_name}...")

            for idx, image_url in enumerate(image_urls):
                doc_id = f"item_{item_id}_{idx}"
                try:
                    # 2. Download and Validate
                    image_bytes = download_image(image_url)
                    if not image_bytes:
                        # download_image already logs video skip or error
                        stats["skipped"] += 1
                        continue
                    
                    if not is_valid_image(image_bytes):
                        print(f"  - [Image {idx}] Skip: Invalid image format at {image_url}")
                        stats["skipped"] += 1
                        continue
                        
                    current_hash = calculate_image_hash(image_bytes)
                    
                    # Check Firestore
                    existing_doc = self.db.get_product(doc_id)
                    if existing_doc and existing_doc.get("image_hash") == current_hash:
                        # Skip if hash matches
                        stats["skipped"] += 1
                        continue

                    # 3. Generate Embedding (if not dry run)
                    embedding = None
                    if not self.dry_run:
                        embedding = self.vision.get_embedding(image_bytes)
                        if not embedding:
                            raise ValueError(f"Failed to generate embedding for image {idx}")
                    
                    # 4. Upsert to Firestore
                    if not self.dry_run:
                        product_data = {
                            "doc_id": doc_id,
                            "item_id": item_id,
                            "item_code": item_code,
                            "name": names, # Store full dict
                            "image_url": image_url,
                            "image_hash": current_hash,
                            "embedding": embedding,
                            "last_updated": time.time(),
                            "parent_product_id": product_fields.get("product_entity_id")
                        }
                        self.db.upsert_product(product_data)
                        stats["images_indexed"] += 1
                    else:
                        print(f"  - Dry-run: Image {idx} processed (simulated).")
                        stats["images_indexed"] += 1

                except Exception as e:
                    print(f"  - [Image {idx}] ❌ Error: {e}")
                    stats["failed"] += 1
                    # Log error
                    if not self.dry_run:
                        error_doc = {
                            "doc_id": doc_id,
                            "item_id": item_id,
                            "item_code": item_code,
                            "error_message": str(e),
                            "timestamp": time.time()
                        }
                        try:
                            self.db.db.collection(self.config["FIRESTORE_ERRORS_COLLECTION"]).add(error_doc)
                        except:
                            pass

        return stats

    def run(self, total_limit: int = 500):
        """
        Runs the full batch process up to total_limit.
        """
        batch_size = 50 # Internal loop batch size (can be smaller than CLI arg for safety)
        processed_so_far = 0
        
        overall_stats = {
            "total_items_processed": 0,
            "total_images_indexed": 0,
            "total_skipped": 0,
            "total_failed": 0,
            "start_time": time.time()
        }

        while processed_so_far < total_limit:
            current_batch_limit = min(batch_size, total_limit - processed_so_far)
            batch_stats = self.process_batch(processed_so_far, current_batch_limit)
            
            overall_stats["total_items_processed"] += batch_stats["items_processed"]
            overall_stats["total_images_indexed"] += batch_stats["images_indexed"]
            overall_stats["total_skipped"] += batch_stats["skipped"]
            overall_stats["total_failed"] += batch_stats["failed"]
            
            processed_so_far += current_batch_limit
            if batch_stats["items_processed"] < current_batch_limit:
                # No more items
                break
        
        overall_stats["end_time"] = time.time()
        duration = overall_stats["end_time"] - overall_stats["start_time"]
        
        print("\n" + "="*30)
        print("BATCH PROCESSING COMPLETE")
        print(f"Duration: {duration:.2f}s")
        print(f"Items Processed: {overall_stats['total_items_processed']}")
        print(f"Images Indexed:  {overall_stats['total_images_indexed']}")
        print(f"Skipped:         {overall_stats['total_skipped']}")
        print(f"Failed:          {overall_stats['total_failed']}")
        print("="*30)
        
        return overall_stats
