#!/usr/bin/env python3
"""Test the vector search with a sample query to see what's happening"""
import os
import sys

# Use the venv
venv_python = "/Users/jeremykhothesting.com/ecom-applicatiebeheer/venv/bin/python3"
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

from google.cloud import firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
from app_config import get_config

try:
    config = get_config()
    db = firestore.Client(
        project=config.get("GOOGLE_CLOUD_PROJECT"), 
        database=config.get("FIRESTORE_DATABASE")
    )
    collection_name = config.get("FIRESTORE_PRODUCTS_COLLECTION", "products")
    collection = db.collection(collection_name)
    
    # Get all products
    all_products = list(collection.limit(10).stream())
    print(f"Total products in collection: {len(all_products)}\n")
    
    for i, doc in enumerate(all_products, 1):
        data = doc.to_dict()
        print(f"Product {i}:")
        print(f"  ID: {doc.id}")
        print(f"  Entity ID: {data.get('entity_id', 'N/A')}")
        print(f"  Name: {data.get('name', 'N/A')}")
        print(f"  Has embedding: {'embedding' in data}")
        if 'embedding' in data:
            print(f"  Embedding dimension: {len(data['embedding'])}")
        print(f"  Image URL: {data.get('image_url', 'N/A')}")
        print(f"  All fields: {list(data.keys())}")
        print()
        
        # Try a test vector search with this product's own embedding
        if 'embedding' in data:
            print(f"  Testing vector search with product's own embedding...")
            try:
                test_vector = data['embedding']
                vector_query = collection.find_nearest(
                    vector_field="embedding",
                    query_vector=Vector(test_vector),
                    distance_measure=DistanceMeasure.COSINE,
                    limit=5
                )
                results = list(vector_query.stream())
                print(f"  ✓ Vector search returned {len(results)} results")
                if results:
                    for j, result in enumerate(results[:3], 1):
                        result_data = result.to_dict()
                        print(f"    {j}. {result_data.get('name', 'N/A')}")
            except Exception as e:
                print(f"  ❌ Vector search failed: {e}")
            print()
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
