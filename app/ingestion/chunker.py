from typing import List, Dict, Any
from app.config import settings

class DocumentChunker:
    """
    Splits text documents into chunks with overlapping windows for embedding & vector store indexing.
    """

    def __init__(self, chunk_size: int = settings.CHUNK_SIZE, chunk_overlap: int = settings.CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunked_docs = []
        for doc in documents:
            content = doc["content"]
            metadata = doc["metadata"]

            if not content.strip():
                continue

            chunks = self._recursive_split(content)
            for idx, chunk_text in enumerate(chunks):
                chunk_meta = metadata.copy()
                chunk_meta["chunk_id"] = f"{metadata['source']}_chunk_{idx}"
                chunk_meta["chunk_index"] = idx

                chunked_docs.append({
                    "content": chunk_text,
                    "metadata": chunk_meta
                })
        return chunked_docs

    def _recursive_split(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        separators = ["\n\n", "\n", ". ", " ", ""]
        final_chunks = []
        
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            if end >= len(text):
                final_chunks.append(text[start:])
                break

            # Find nearest separator
            split_at = end
            for sep in separators:
                pos = text.rfind(sep, start + self.chunk_overlap, end)
                if pos != -1 and pos > start:
                    split_at = pos + len(sep)
                    break
            
            chunk = text[start:split_at].strip()
            if chunk:
                final_chunks.append(chunk)
            
            start = split_at - self.chunk_overlap if (split_at - self.chunk_overlap) > start else split_at

        return final_chunks
