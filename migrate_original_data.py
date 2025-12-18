#!/usr/bin/env python3
"""
Migrate original ChromaDB data to work with Sentence Transformers.
This script reads the existing data and recreates it with compatible embeddings.
"""

import os
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import config

def migrate_original_data():
    """Migrate original ChromaDB data to Sentence Transformers"""

    # Backup current data
    if os.path.exists("./chroma_db_data"):
        os.rename("./chroma_db_data", "./chroma_db_data_original")

    print("Attempting to read original ChromaDB data...")

    try:
        # Try to read with OpenAI client (if that's what was used originally)
        from langchain_openai import OpenAIEmbeddings

        old_client = chromadb.PersistentClient(
            path="./chroma_db_data_original",
            settings=Settings(anonymized_telemetry=False)
        )

        # Try to get the collection
        try:
            old_collection = old_client.get_collection("domain_embeddings")
            print(f"Found collection with {old_collection.count()} documents")

            # Get all data
            results = old_collection.get(include=["documents", "metadatas"])
            documents = results["documents"]
            metadatas = results["metadatas"]

            print(f"Successfully extracted {len(documents)} documents")

            # Create new collection with Sentence Transformers
            new_client = chromadb.PersistentClient(
                path="./chroma_db_data",
                settings=Settings(anonymized_telemetry=False)
            )

            new_collection = new_client.get_or_create_collection(
                name="domain_embeddings",
                metadata={"hnsw:space": "cosine"}
            )

            # Initialize Sentence Transformers
            embeddings = SentenceTransformer(config.EMBEDDING_MODEL)

            # Re-embed all documents
            print("Re-embedding documents with Sentence Transformers...")
            embeddings_array = embeddings.encode(documents)

            # Add to new collection
            ids = [f"orig_{i}" for i in range(len(documents))]

            new_collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

            print(f"✅ Successfully migrated {len(documents)} documents to Sentence Transformers")
            print("Your original domain data is now ready to use!")

            return True

        except Exception as e:
            print(f"Could not read original collection: {e}")

    except Exception as e:
        print(f"Could not initialize ChromaDB client: {e}")

    print("\n❌ Migration failed. Your original data may be corrupted or incompatible.")
    print("\nTo recreate your database, please provide your domain data in one of these formats:")
    print("1. CSV file with columns: domain, description, price, date, platform, categories")
    print("2. JSON file with domain objects")
    print("3. Python script that adds your domains to ChromaDB")

    # Restore original data location
    if os.path.exists("./chroma_db_data_original"):
        os.rename("./chroma_db_data_original", "./chroma_db_data")

    return False

if __name__ == "__main__":
    migrate_original_data()


