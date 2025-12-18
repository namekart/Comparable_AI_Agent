#!/usr/bin/env python3
"""
Script to populate ChromaDB with test domain data using Sentence Transformers.
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import config

def populate_chroma():
    """Populate ChromaDB with test domain data"""

    # Initialize ChromaDB client
    client = chromadb.PersistentClient(
        path=config.CHROMA_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False)
    )

    # Initialize Sentence Transformers
    embeddings = SentenceTransformer(config.EMBEDDING_MODEL)

    # Create or get collection
    collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    # Clear existing data
    try:
        collection.delete(where={})  # Clear all documents
        print("[INFO] Cleared existing data")
    except:
        pass

    # Sample sold domain data - diverse categories and TLDs covering all combinations
    sample_data = [
        # .com domains with appropriate lengths (18-22) and matching categories
        {
            "document": "Foundation providing educational programs and community services for nonprofit organizations.",
            "metadata": {
                "domain": "communityservicefoundation.com",
                "tld": ".com",
                "length": 25,  # Let's use a better approach - create domains with exactly the right length
                "primary_category": "Exact match",
                "secondary_category": "Service-based",
                "price": 45000,
                "date": "2024-01-15",
                "platform": "GoDaddy",
                "desc_index": 1
            }
        },
        # Create domains with length 18-22 that match the test case
        {
            "document": "Health and wellness foundation providing comprehensive community services and mental health support.",
            "metadata": {
                "domain": "wellnessfoundationinc.com",
                "tld": ".com",
                "length": 21,  # "wellnessfoundationinc" = 21 characters
                "primary_category": "Combination",
                "secondary_category": "Descriptive",
                "price": 55000,
                "date": "2024-02-20",
                "platform": "Namecheap",
                "desc_index": 1
            }
        },
        {
            "document": "Educational foundation focused on community development and social impact programs.",
            "metadata": {
                "domain": "socialimpactfoundation.com",
                "tld": ".com",
                "length": 22,  # "socialimpactfoundation" = 22 characters
                "primary_category": "Descriptive",
                "secondary_category": "Service-based",
                "price": 48000,
                "date": "2024-03-01",
                "platform": "GoDaddy",
                "desc_index": 1
            }
        },
        # .ai domains
        {
            "document": "Trust.ai is a premium .ai domain perfect for AI trust and security companies, offering certification and compliance services.",
            "metadata": {
                "domain": "trust.ai",
                "tld": ".ai",
                "length": 5,
                "primary_category": "Brandable",
                "secondary_category": "Service-based",
                "price": 150000,
                "date": "2024-02-20",
                "platform": "Sedо",
                "desc_index": 1
            }
        },
        # .io domains
        {
            "document": "TechFlow.io offers comprehensive workflow automation solutions for modern businesses and startups.",
            "metadata": {
                "domain": "techflow.io",
                "tld": ".io",
                "length": 8,
                "primary_category": "Brandable",
                "secondary_category": "Service-based",
                "price": 125000,
                "date": "2024-03-01",
                "platform": "GoDaddy",
                "desc_index": 1
            }
        },
        # .org domains
        {
            "document": "Peace Haven Foundation provides mental health services and community wellness programs.",
            "metadata": {
                "domain": "peacehaven.org",
                "tld": ".org",
                "length": 10,
                "primary_category": "Descriptive",
                "secondary_category": "Service-based",
                "price": 25000,
                "date": "2024-01-15",
                "platform": "GoDaddy",
                "desc_index": 1
            }
        },
        # More .com domains with different combinations
        {
            "document": "CloudSecure delivers advanced security solutions for cloud infrastructure protection.",
            "metadata": {
                "domain": "cloudsecure.com",
                "tld": ".com",
                "length": 11,
                "primary_category": "Combination",
                "secondary_category": "Product-based",
                "price": 180000,
                "date": "2024-01-30",
                "platform": "Sedо",
                "desc_index": 1
            }
        },
        {
            "document": "HealthTech connects healthcare providers with cutting-edge technology solutions.",
            "metadata": {
                "domain": "healthtech.com",
                "tld": ".com",
                "length": 10,
                "primary_category": "Combination",
                "secondary_category": "Service-based",
                "price": 95000,
                "date": "2024-02-10",
                "platform": "GoDaddy",
                "desc_index": 1
            }
        },
        # Domains with Generic category
        {
            "document": "Generic domain suitable for various business applications and service offerings.",
            "metadata": {
                "domain": "businesspro.com",
                "tld": ".com",
                "length": 11,
                "primary_category": "Generic",
                "secondary_category": "Service-based",
                "price": 55000,
                "date": "2023-12-01",
                "platform": "Namecheap",
                "desc_index": 1
            }
        }
    ]

    # Generate embeddings and add to ChromaDB
    documents = [item["document"] for item in sample_data]
    metadatas = [item["metadata"] for item in sample_data]
    ids = [f"domain_{i}" for i in range(len(sample_data))]

    # Generate embeddings
    print("Generating embeddings with Sentence Transformers...")
    embeddings_array = embeddings.encode(documents)

    # Add to collection
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"[SUCCESS] Successfully added {len(sample_data)} domains to ChromaDB")
    print(f"Database location: {config.CHROMA_PERSIST_DIR}")
    print(f"Collection: {config.CHROMA_COLLECTION_NAME}")

    # Verify data
    count = collection.count()
    print(f"Total documents in collection: {count}")

if __name__ == "__main__":
    populate_chroma()
