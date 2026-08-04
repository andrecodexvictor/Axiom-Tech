"""Stable, overlap-aware document chunking."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from app.config import settings


class DocumentChunker:
    """Split normalized loader documents and attach deterministic chunk identifiers."""

    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunked_docs: List[Dict[str, Any]] = []
        for document in documents:
            content = str(document.get("content", "")).strip()
            metadata = dict(document.get("metadata", {}))
            if not content:
                continue

            source_key = str(metadata.get("source_key") or metadata.get("path") or metadata.get("source", "unknown"))
            location_key = "|".join(
                "{0}={1}".format(key, metadata[key])
                for key in ("page", "slide", "sheet")
                if metadata.get(key) is not None
            )
            for index, chunk_text in enumerate(self._recursive_split(content)):
                stable_key = f"{source_key}\0{location_key}\0{index}\0{chunk_text}".encode("utf-8")
                chunk_id = hashlib.sha256(stable_key).hexdigest()
                chunk_metadata = dict(metadata)
                chunk_metadata.update(
                    {
                        "chunk_id": chunk_id,
                        "chunk_index": index,
                        "source_key": source_key,
                        "content_hash": hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                    }
                )
                chunked_docs.append({"id": chunk_id, "content": chunk_text, "metadata": chunk_metadata})
        return chunked_docs

    def _recursive_split(self, text: str) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        separators = ("\n\n", "\n", ". ", " ")
        chunks: List[str] = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(text_length, start + self.chunk_size)
            if end == text_length:
                tail = text[start:].strip()
                if tail:
                    chunks.append(tail)
                break

            split_at = end
            for separator in separators:
                candidate = text.rfind(separator, start + 1, end)
                if candidate > start:
                    split_at = candidate + len(separator)
                    break
            value = text[start:split_at].strip()
            if value:
                chunks.append(value)
            next_start = max(start + 1, split_at - self.chunk_overlap)
            start = next_start
        return chunks
