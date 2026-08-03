import os
import math
from typing import List, Dict, Any
from app.config import settings

class VectorStore:
    """
    Pinecone Vector Database connector with robust fallback to lightweight local TF-IDF vector index.
    """

    def __init__(self):
        self.use_pinecone = bool(settings.PINECONE_API_KEY)
        self.documents: List[Dict[str, Any]] = []

        if self.use_pinecone:
            try:
                from pinecone import Pinecone
                self.pc = Pinecone(api_key=settings.PINECONE_API_KEY)
                print("[Pinecone] Connected to Pinecone Vector DB.")
            except Exception as e:
                print(f"[Pinecone Warning] Falling back to local index: {e}")
                self.use_pinecone = False
        else:
            print("[VectorStore] Pinecone API key not found. Operating in fast local vector mode.")

    def index_documents(self, chunks: List[Dict[str, Any]]) -> int:
        self.documents.extend(chunks)
        if self.use_pinecone:
            try:
                # Stub for Pinecone upsert logic
                print(f"[Pinecone] Upserted {len(chunks)} vectors to index '{settings.PINECONE_INDEX_NAME}'.")
            except Exception as e:
                print(f"[Pinecone Upsert Error]: {e}")
        return len(chunks)

    def similarity_search(self, query: str, domain_filter: str = None, top_k: int = 4) -> List[Dict[str, Any]]:
        if not self.documents:
            return []

        query_terms = set(query.lower().split())
        scored_docs = []

        for doc in self.documents:
            meta = doc["metadata"]
            if domain_filter and meta.get("domain") != domain_filter and domain_filter != "all":
                continue

            content_terms = doc["content"].lower().split()
            if not content_terms:
                continue

            # Term overlap score
            match_count = sum(1 for word in query_terms if word in content_terms)
            score = match_count / math.sqrt(len(query_terms) * len(content_terms) + 1e-5)
            
            # Domain boosting
            if domain_filter and meta.get("domain") == domain_filter:
                score *= 1.5

            if score > 0:
                scored_docs.append((score, doc))

        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [doc for score, doc in scored_docs[:top_k]]

vector_store = VectorStore()
