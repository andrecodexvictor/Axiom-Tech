"""Bounded, atomic storage for documents uploaded into the local corpus."""

from __future__ import annotations

import json
import os
import re
import threading
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.agents.routing import INTERNAL_DOMAINS
from app.ingestion.loader import DocumentLoader


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_EXPANDED_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5_000
_COPY_CHUNK_BYTES = 64 * 1024
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_OFFICE_MARKERS = {
    ".docx": "word/document.xml",
    ".pptx": "ppt/presentation.xml",
    ".xlsx": "xl/workbook.xml",
}


class UploadRejectedError(ValueError):
    """Raised when an upload violates the corpus policy."""


class UploadTooLargeError(UploadRejectedError):
    """Raised when an upload exceeds the bounded request size."""


@dataclass(frozen=True)
class StoredDocument:
    path: Path
    relative_path: str
    filename: str
    domain: str
    file_type: str
    size_bytes: int


class DocumentUploadStore:
    """Validate and atomically add one immutable file to the corpus."""

    _commit_lock = threading.Lock()

    def __init__(self, documents_dir: Path, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
        self.documents_dir = Path(documents_dir).resolve()
        self.max_bytes = max(1, int(max_bytes))

    def store(self, stream: BinaryIO, *, filename: str, domain: str) -> StoredDocument:
        safe_name = self._safe_filename(filename)
        safe_domain = self._safe_domain(domain)
        extension = Path(safe_name).suffix.lower()
        if extension not in DocumentLoader.SUPPORTED_EXTENSIONS:
            raise UploadRejectedError("Document type is not supported")

        target_dir = (self.documents_dir / safe_domain).resolve()
        self._assert_inside_root(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = (target_dir / safe_name).resolve()
        self._assert_inside_root(target)
        temporary = target_dir / f".upload-{uuid.uuid4().hex}{extension}"

        try:
            size = self._copy_bounded(stream, temporary)
            self._validate_content(temporary, extension)
            self._validate_extractable(temporary)
            with self._commit_lock:
                if target.exists():
                    raise FileExistsError("A document with this name already exists")
                # Reserve the final name without overwriting an existing corpus
                # file, then atomically replace our own empty reservation.
                target.touch(exist_ok=False)
                try:
                    os.replace(temporary, target)
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return StoredDocument(
            path=target,
            relative_path=target.relative_to(self.documents_dir).as_posix(),
            filename=safe_name,
            domain=safe_domain,
            file_type=extension.lstrip("."),
            size_bytes=size,
        )

    def _copy_bounded(self, stream: BinaryIO, target: Path) -> int:
        size = 0
        with target.open("xb") as handle:
            while True:
                chunk = stream.read(_COPY_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > self.max_bytes:
                    raise UploadTooLargeError("Document exceeds the upload size limit")
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if size == 0:
            raise UploadRejectedError("Document is empty")
        return size

    @staticmethod
    def _safe_filename(filename: str) -> str:
        value = unicodedata.normalize("NFC", str(filename or "")).strip()
        if not value or value in {".", ".."}:
            raise UploadRejectedError("A valid filename is required")
        if value != Path(value).name or _INVALID_FILENAME.search(value):
            raise UploadRejectedError("Filename contains a path or unsupported characters")
        if (
            value.endswith((".", " "))
            or len(value) > 180
            or Path(value).stem.upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise UploadRejectedError("Filename is not supported")
        return value

    @staticmethod
    def _safe_domain(domain: str) -> str:
        value = str(domain or "").strip().lower()
        if value not in INTERNAL_DOMAINS:
            raise UploadRejectedError("Upload domain is not supported")
        return value

    def _assert_inside_root(self, path: Path) -> None:
        try:
            path.relative_to(self.documents_dir)
        except ValueError as exc:
            raise PermissionError("Upload target is outside the documents directory") from exc

    @classmethod
    def _validate_content(cls, path: Path, extension: str) -> None:
        if extension == ".pdf":
            with path.open("rb") as handle:
                signature = handle.read(5)
            if signature != b"%PDF-":
                raise UploadRejectedError("PDF signature is invalid")
            return
        if extension in _OFFICE_MARKERS:
            cls._validate_office_archive(path, _OFFICE_MARKERS[extension])
            return
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise UploadRejectedError("Text documents must use UTF-8") from exc
        if "\x00" in text:
            raise UploadRejectedError("Text document contains binary data")
        if extension == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                raise UploadRejectedError("JSON document is invalid") from exc

    @staticmethod
    def _validate_office_archive(path: Path, marker: str) -> None:
        if not zipfile.is_zipfile(path):
            raise UploadRejectedError("Office document container is invalid")
        try:
            with zipfile.ZipFile(path) as archive:
                members = archive.infolist()
                names = {item.filename for item in members}
                expanded = sum(max(0, item.file_size) for item in members)
        except (OSError, zipfile.BadZipFile) as exc:
            raise UploadRejectedError("Office document container is invalid") from exc
        if "[Content_Types].xml" not in names or marker not in names:
            raise UploadRejectedError("Office document type does not match its extension")
        if len(members) > MAX_ARCHIVE_MEMBERS or expanded > MAX_EXPANDED_ARCHIVE_BYTES:
            raise UploadRejectedError("Office document expands beyond the safe limit")

    def _validate_extractable(self, path: Path) -> None:
        try:
            documents = DocumentLoader.load_file(path, source_root=self.documents_dir)
        except Exception as exc:
            raise UploadRejectedError("Document content could not be extracted") from exc
        if not any(str(item.get("content", "")).strip() for item in documents):
            raise UploadRejectedError("Document has no extractable text")
