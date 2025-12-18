#!/usr/bin/env python3
"""
Script to populate ChromaDB with YOUR actual domain data.
Replace the sample data below with your real domain information.
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import config

def populate_your_domains():
    """Populate ChromaDB with your actual domain data"""

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

    # Clear existing data (if any)
    try:
        collection.delete(where={})
        print("Cleared existing data")
    except:
        pass

    # 🔴🔴🔴 REPLACE THIS SAMPLE DATA WITH YOUR ACTUAL DOMAIN DATA 🔴🔴🔴
    # Your domain data should include:
    # - domain: the domain name
    # - description: text description of what the domain was used for
    # - price: sale price
    # - date: sale date (YYYY-MM-DD)
    # - platform: where it was sold (GoDaddy, Sedo, etc.)
    # - primary_category: main category from DOMAIN_CATEGORIES list
    # - secondary_category: secondary category from DOMAIN_CATEGORIES list
    # - length: length of the SLD (calculated automatically)
    # - tld: TLD like .com, .ai, etc. (calculated automatically)

    your_domain_data = [
        # Domains that will match common test cases
        {
            "domain": "brandable.ai",
            "description": "Premium brandable domain perfect for AI companies and technology startups looking for memorable brand names.",
            "price": 150000,
            "date": "2024-01-15",
            "platform": "Sedo",
            "primary_category": "Brandable",
            "secondary_category": "Generic"
        },
        {
            "domain": "keyword.ai",
            "description": "Strong keyword domain for AI-related businesses and artificial intelligence service providers.",
            "price": 200000,
            "date": "2024-02-20",
            "platform": "GoDaddy",
            "primary_category": "Keyword",
            "secondary_category": "Service-based"
        },
        {
            "domain": "startup.io",
            "description": "Perfect domain for startup companies and innovative technology ventures.",
            "price": 85000,
            "date": "2024-03-10",
            "platform": "Namecheap",
            "primary_category": "Generic",
            "secondary_category": "Brandable"
        },
        {
            "domain": "tech.co",
            "description": "Technology-focused domain suitable for tech companies and software development firms.",
            "price": 120000,
            "date": "2024-01-30",
            "platform": "GoDaddy",
            "primary_category": "Service-based",
            "secondary_category": "Product-based"
        },

        # 🔴 REPLACE ABOVE WITH YOUR ACTUAL DOMAIN DATA 🔴
        # Copy this format for each of your domains:

        # {
        #     "domain": "yourdomain.com",
        #     "description": "Description of what this domain was used for when sold",
        #     "price": 50000,  # Sale price
        #     "date": "2024-01-01",  # Sale date
        #     "platform": "GoDaddy",  # Where it was sold
        #     "primary_category": "Service-based",  # From DOMAIN_CATEGORIES
        #     "secondary_category": "Product-based"  # From DOMAIN_CATEGORIES
        # },
    ]

    # Process and add data
    documents = []
    metadatas = []
    ids = []

    for i, domain_data in enumerate(your_domain_data):
        # Extract domain components
        domain_name = domain_data["domain"]
        sld = domain_name.split('.')[0]  # Get SLD (part before TLD)
        tld = '.' + '.'.join(domain_name.split('.')[1:])  # Get TLD

        # Create document (description for embedding)
        document = domain_data["description"]

        # Create metadata
        metadata = {
            "domain": domain_name,
            "tld": tld,
            "length": len(sld),
            "primary_category": domain_data["primary_category"],
            "secondary_category": domain_data["secondary_category"],
            "price": domain_data["price"],
            "date": domain_data["date"],
            "platform": domain_data["platform"],
            "desc_index": 1
        }

        documents.append(document)
        metadatas.append(metadata)
        ids.append(f"domain_{i}")

        print(f"Prepared domain: {domain_name} ({domain_data['primary_category']})")

    # Generate embeddings
    print(f"\nGenerating embeddings for {len(documents)} domains...")
    embeddings_array = embeddings.encode(documents)

    # Add to collection
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"\n[SUCCESS] Successfully added {len(documents)} domains to ChromaDB")
    print(f"Database location: {config.CHROMA_PERSIST_DIR}")
    print(f"Collection: {config.CHROMA_COLLECTION_NAME}")

    # Verify data
    count = collection.count()
    print(f"Total documents in collection: {count}")

    print("\n" + "="*60)
    print("SUCCESS: YOUR DOMAIN DATABASE IS READY!")
    print("Run 'python main.py' to test comparable domain search")
    print("="*60)

if __name__ == "__main__":
    populate_your_domains()
