import os
import sys
import pathlib
import logging

# Use the venv
venv_python = "/Users/jeremykhothesting.com/ecom-applicatiebeheer/venv/bin/python3"
if os.path.exists(venv_python) and sys.executable != venv_python:
    os.execv(venv_python, [venv_python] + sys.argv)

logging.basicConfig(level=logging.INFO)
from tools.search_tools import search_similar_products

def test_fallback_search():
    # Use a dummy image (or a real one if available, but let's try a small transparent pixel as bytes)
    # Actually, Vertex AI might fail on tiny images, but let's try a simple 1x1 PNG
    dummy_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    
    print("Testing search_similar_products (should trigger fallback if vector index returns 0)...")
    try:
        results = search_similar_products(dummy_png)
        print(f"\nFinal Results ({len(results)}):")
        for i, res in enumerate(results, 1):
            print(f"{i}. {res.get('entity_id')} - {res.get('name')} (Similarity: {res.get('_similarity', 'N/A')})")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_fallback_search()
