from __future__ import annotations

from io import BytesIO

import pytest

from app.ingestion.upload import (
    DocumentUploadStore,
    UploadRejectedError,
    UploadTooLargeError,
)


def test_upload_store_enforces_size_utf8_and_domain_policy(tmp_path) -> None:
    store = DocumentUploadStore(tmp_path / "documents", max_bytes=12)

    with pytest.raises(UploadTooLargeError):
        store.store(BytesIO(b"x" * 13), filename="large.txt", domain="rh")
    with pytest.raises(UploadRejectedError):
        store.store(BytesIO(b"\xff\xfe"), filename="binary.txt", domain="rh")
    with pytest.raises(UploadRejectedError):
        store.store(BytesIO(b"valid text"), filename="note.txt", domain="web")

    assert not list((tmp_path / "documents").rglob(".upload-*"))


@pytest.mark.parametrize("filename", ["../note.txt", "CON.txt", "report?.md"])
def test_upload_store_rejects_unsafe_filenames(tmp_path, filename: str) -> None:
    store = DocumentUploadStore(tmp_path / "documents")

    with pytest.raises(UploadRejectedError):
        store.store(BytesIO(b"valid text"), filename=filename, domain="rh")
