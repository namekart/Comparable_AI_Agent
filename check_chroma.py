#!/usr/bin/env python3
"""
Script to check what's actually stored in ChromaDB.
"""

import chromadb
from chromadb.config import Settings
import config

def check_chroma():
    """Check ChromaDB contents"""

    # Initialize ChromaDB client
    client = chromadb.PersistentClient(
        path=config.CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False)
    )

    # Get collection
    collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # Get all documents
    results = collection.get(include=["documents", "metadatas"])

    print(f"Total documents: {len(results['documents'])}")
    print("\nDocuments and metadata:")

    for i, (doc, metadata) in enumerate(zip(results['documents'], results['metadatas'])):
        print(f"\n{i+1}. Domain: {metadata['domain']}")
        print(f"   Categories: {metadata['primary_category']} / {metadata['secondary_category']}")
        print(f"   TLD: {metadata['tld']}, Length: {metadata['length']}")
        print(f"   Document: {doc[:100]}...")

if __name__ == "__main__":
    check_chroma()


