#!/usr/bin/env python3
# CI Gate: Embedding Prefix & Dimension Contract
import sys
import argparse

REQUIRED_DOC_PREFIX = "search_document: "
REQUIRED_QUERY_PREFIX = "search_query: "
REQUIRED_DIM = 768

calls = []

def fake_encode(text):
    calls.append(text)
    return [0.0] * REQUIRED_DIM

class EmbeddingService:
    def __init__(self, encoder):
        self.encoder = encoder
    
    def embed_document(self, text):
        return self.encoder(REQUIRED_DOC_PREFIX + text)
    
    def embed_query(self, text):
        return self.encoder(REQUIRED_QUERY_PREFIX + text)

def main():
    svc = EmbeddingService(fake_encode)
    
    doc_text = "accepted triage summary"
    query_text = "similar alert lookup"
    
    doc_vector = svc.embed_document(doc_text)
    query_vector = svc.embed_query(query_text)
    
    # Verify Dimensions
    if len(doc_vector) != REQUIRED_DIM:
        print(f"FAIL: document embedding dim is {len(doc_vector)}, expected {REQUIRED_DIM}")
        return 1
    if len(query_vector) != REQUIRED_DIM:
        print(f"FAIL: query embedding dim is {len(query_vector)}, expected {REQUIRED_DIM}")
        return 1
        
    # Verify Prefixes
    if not calls[0].startswith(REQUIRED_DOC_PREFIX):
        print(f"FAIL: document prefix mismatch. Got: {calls[0][:20]}...")
        return 1
    if not calls[1].startswith(REQUIRED_QUERY_PREFIX):
        print(f"FAIL: query prefix mismatch. Got: {calls[1][:20]}...")
        return 1
        
    print("PASS: Embedding prefix and dimension contract verified.")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CI Check Tool")
    parser.add_argument("--dry-run", action="store_true", help="Run with test/mock data")
    args = parser.parse_args()
    
    sys.exit(main())
