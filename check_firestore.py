#!/usr/bin/env python3
"""Quick check for Firestore products - uses environment variables"""
import os
import sys

# Set environment to use the venv if needed
venv_python = "/Users/jeremykhothesting.com/ecom-applicatiebeheer/venv/bin/python3"
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

# Now we're in the venv
from google.cloud import firestore
from app_config import get_config

try:
    config = get_config()
    db = firestore.Client(
        project=config.get("GOOGLE_CLOUD_PROJECT"), 
        database=config.get("FIRESTORE_DATABASE")
    )
    
    # Get count and sample
    collection_name = config.get("FIRESTORE_PRODUCTS_COLLECTION", "products")
    products = db.collection(collection_name).limit(5).stream()
    products_list = list(products)
    
    print(f"✓ Connected to Firestore (project: {db.project}, database: {config.get('FIRESTORE_DATABASE')})")
    print(f"✓ {collection_name} collection has {len(products_list)} documents (showing first 5)")
    
    if products_list:
        first_doc = products_list[0].to_dict()
        has_embedding = 'embedding' in first_doc
        
        if has_embedding:
            embedding = first_doc['embedding']
            print(f"✓ Products have embeddings!")
            print(f"✓ Embedding dimension: {len(embedding)}")
            print(f"\nSample product fields: {list(first_doc.keys())[:15]}")
        else:
            print(f"❌ Products DO NOT have embeddings")
            print(f"   Available fields: {list(first_doc.keys())}")
            print(f"\n⚠️  You need to run batch_processor.py to add embeddings")
    else:
        print(f"❌ No products found in collection")
        print(f"   Run batch_processor.py to populate the database")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
