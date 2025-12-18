import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from typing import List, Dict
import config
import numpy as np

class ChromaClient:
    """ Wrapper for ChromaDB operations"""

    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=config.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )

        # Use Sentence Transformers for embeddings
        self.embeddings = SentenceTransformer(config.EMBEDDING_MODEL)

        self.collection = self.client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )
    
    def query(self, query_texts: List[str], where: Dict, n_results: int = 50) -> List[Dict]:
        """Query ChromaDB with hard filters.

        Args:
            query_texts: List of description strings to embed and search
            where: Hard filter where clause
            n_results: Number of results per query

        Returns:
            List of candidates with metadata and distances
        """
        results = self.collection.query(
            query_texts=query_texts,
            where=where,
            n_results=n_results,
            include=["metadatas", "distances", "documents"]
        )

        candidates = []
        for i in range(len(results["ids"][0])):
            candidates.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "distance": results["distances"][0][i],
                "metadata": results["metadatas"][0][i]
            })

        return candidates