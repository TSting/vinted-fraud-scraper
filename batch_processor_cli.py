import argparse
import sys
from batch_processor import BatchProcessor

def main():
    parser = argparse.ArgumentParser(description="Run Batch Processor for Visual Search index ingestion.")
    parser.add_argument("--limit", type=int, default=500, help="Total number of products to process.")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing to Firestore or generating embeddings.")
    
    args = parser.parse_args()
    
    processor = BatchProcessor(dry_run=args.dry_run)
    try:
        processor.run(total_limit=args.limit)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
