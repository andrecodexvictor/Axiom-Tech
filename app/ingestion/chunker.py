"""Stable, overlap-aware document chunking."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Tuple

from app.config import settings


class DocumentChunker:
    """Split normalized loader documents and attach deterministic chunk identifiers."""

    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
    ) -> None:
        if int(chunk_size) < 64:
            raise ValueError("chunk_size must be at least 64 characters")
        if int(chunk_overlap) < 0:
            raise ValueError("chunk_overlap must not be negative")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = int(chunk_size)
        self.chunk_overlap = int(chunk_overlap)

    def split_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        chunked_docs: List[Dict[str, Any]] = []
        for document in documents:
            content = self._normalize_text(str(document.get("content", "")))
            metadata = dict(document.get("metadata", {}))
            if not content:
                continue

            source_key = str(
                metadata.get("source_key")
                or metadata.get("path")
                or metadata.get("source", "unknown")
            )
            location_key = "|".join(
                "{0}={1}".format(key, metadata[key])
                for key in ("page", "slide", "sheet")
                if metadata.get(key) is not None
            )
            document_id = hashlib.sha256(
                "{0}\0{1}".format(source_key, location_key).encode("utf-8")
            ).hexdigest()
            pieces = self._split_with_spans(content)
            for index, (start, end, chunk_text) in enumerate(pieces):
                content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                stable_key = "{0}\0{1}\0{2}\0{3}".format(
                    document_id, index, start, content_hash
                ).encode("utf-8")
                chunk_id = hashlib.sha256(stable_key).hexdigest()
                chunk_metadata = dict(metadata)
                chunk_metadata.update(
                    {
                        "chunk_id": chunk_id,
                        "chunk_index": index,
                        "chunk_count": len(pieces),
                        "chunk_chars": len(chunk_text),
                        "char_start": start,
                        "char_end": end,
                        "word_count": len(re.findall(r"\S+", chunk_text)),
                        "document_id": document_id,
                        "source_key": source_key,
                        "content_hash": content_hash,
                    }
                )
                section = self._section_at(content, start)
                if section:
                    chunk_metadata["section"] = section
                chunked_docs.append({"id": chunk_id, "content": chunk_text, "metadata": chunk_metadata})
        return chunked_docs

    def _recursive_split(self, text: str) -> List[str]:
        """Compatibility helper retained for callers that used the old private API."""

        normalized = self._normalize_text(text)
        return [value for _, _, value in self._split_with_spans(normalized)]

    def _split_with_spans(self, text: str) -> List[Tuple[int, int, str]]:
        if not text:
            return []
        if len(text) <= self.chunk_size:
            return [(0, len(text), text)]

        separators = ("\n\n", "\n", ". ", " ")
        chunks: List[Tuple[int, int, str]] = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = min(text_length, start + self.chunk_size)
            if end < text_length:
                minimum_boundary = start + max(
                    self.chunk_overlap + 1, int(self.chunk_size * 0.55)
                )
                for separator in separators:
                    candidate = text.rfind(separator, minimum_boundary, end)
                    if candidate >= minimum_boundary:
                        end = candidate + len(separator)
                        break

            raw = text[start:end]
            left_trim = len(raw) - len(raw.lstrip())
            right_trim = len(raw) - len(raw.rstrip())
            content_start = start + left_trim
            content_end = end - right_trim
            value = text[content_start:content_end]
            if value:
                chunks.append((content_start, content_end, value))
            if end >= text_length:
                break

            next_start = max(start + 1, content_end - self.chunk_overlap)
            # Do not start a chunk in the middle of a word.  Moving forward may
            # shorten overlap slightly but keeps citations and excerpts readable.
            while (
                next_start < content_end
                and next_start > 0
                and not text[next_start - 1].isspace()
            ):
                next_start += 1
            while next_start < text_length and text[next_start].isspace():
                next_start += 1
            if next_start >= content_end:
                next_start = max(start + 1, end - self.chunk_overlap)
            start = next_start
        return chunks

    @staticmethod
    def _normalize_text(value: str) -> str:
        text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
        text = "".join(
            character
            for character in text
            if character in {"\n", "\t"} or unicodedata.category(character) != "Cc"
        )
        # Preserve leading indentation in code blocks and structured documents;
        # only trailing horizontal whitespace is semantically empty.
        lines = [re.sub(r"[ \t]+$", "", line) for line in text.split("\n")]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    @staticmethod
    def _section_at(text: str, start: int) -> str:
        prior = text[:start]
        headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", prior)
        if not headings and start == 0:
            headings = re.findall(r"(?m)^#{1,6}\s+(.+?)\s*$", text[:500])
        return headings[-1][:240] if headings else ""
