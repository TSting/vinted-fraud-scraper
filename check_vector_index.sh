#!/bin/bash
# Quick script to check Firestore vector index status

echo "Checking Firestore vector indexes for project: ecom-agents"
echo ""

gcloud firestore indexes composite list \
  --project=ecom-agents \
  --format="table(name,state,queryScope,fields)" \
  --filter="collectionGroup:products"

echo ""
echo "Looking for vector index with:"
echo "  - Collection: products"
echo "  - Field: embedding"
echo "  - Type: VECTOR (dimension 1408)"
echo ""
echo "Status meanings:"
echo "  CREATING - Index is being built (can take 10-30 min)"
echo "  READY    - Index is ready for use"
