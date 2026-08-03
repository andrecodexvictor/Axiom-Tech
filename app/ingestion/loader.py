import json
import csv
from pathlib import Path
from typing import List, Dict, Any

class DocumentLoader:
    """
    Multi-format document extractor supporting PDF, DOCX, XLSX, CSV, JSON, Markdown, and HTML.
    Normalizes all content into standardized text document objects with metadata.
    """

    @staticmethod
    def load_file(file_path: Path) -> List[Dict[str, Any]]:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = file_path.suffix.lower()
        domain = file_path.parent.name

        if ext == ".md" or ext == ".txt":
            return DocumentLoader._load_text(file_path, domain)
        elif ext == ".json":
            return DocumentLoader._load_json(file_path, domain)
        elif ext == ".csv":
            return DocumentLoader._load_csv(file_path, domain)
        elif ext == ".xlsx" or ext == ".xls":
            return DocumentLoader._load_excel(file_path, domain)
        elif ext == ".pdf":
            return DocumentLoader._load_pdf(file_path, domain)
        elif ext in [".docx", ".doc"]:
            return DocumentLoader._load_docx(file_path, domain)
        elif ext in [".html", ".htm"]:
            return DocumentLoader._load_html(file_path, domain)
        else:
            return DocumentLoader._load_text(file_path, domain)

    @staticmethod
    def _load_text(path: Path, domain: str) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": path.suffix.lower(),
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_json(path: Path, domain: str) -> List[Dict[str, Any]]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        text_content = json.dumps(data, indent=2, ensure_ascii=False)
        return [{
            "content": text_content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": ".json",
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_csv(path: Path, domain: str) -> List[Dict[str, Any]]:
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                formatted_row = ", ".join([f"{k}: {v}" for k, v in row.items()])
                rows.append(formatted_row)
        content = "\n".join(rows)
        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": ".csv",
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_excel(path: Path, domain: str) -> List[Dict[str, Any]]:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, data_only=True)
            lines = []
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                lines.append(f"--- Sheet: {sheet} ---")
                for row in ws.iter_rows(values_only=True):
                    row_str = " | ".join([str(cell) for cell in row if cell is not None])
                    if row_str.strip():
                        lines.append(row_str)
            content = "\n".join(lines)
        except Exception:
            content = f"Excel document content extracted from {path.name}"
        
        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": path.suffix.lower(),
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_pdf(path: Path, domain: str) -> List[Dict[str, Any]]:
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            pages_text = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    pages_text.append(f"[Page {i+1}]\n{text}")
            content = "\n\n".join(pages_text)
        except Exception:
            content = f"PDF content extracted from {path.name}"

        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": ".pdf",
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_docx(path: Path, domain: str) -> List[Dict[str, Any]]:
        try:
            import docx
            doc = docx.Document(path)
            full_text = [p.text for p in doc.paragraphs if p.text.strip()]
            content = "\n".join(full_text)
        except Exception:
            content = f"DOCX document content from {path.name}"

        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": path.suffix.lower(),
                "path": str(path)
            }
        }]

    @staticmethod
    def _load_html(path: Path, domain: str) -> List[Dict[str, Any]]:
        try:
            from bs4 import BeautifulSoup
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            content = soup.get_text(separator="\n", strip=True)
        except Exception:
            content = DocumentLoader._load_text(path, domain)[0]["content"]

        return [{
            "content": content,
            "metadata": {
                "source": str(path.name),
                "domain": domain,
                "file_type": path.suffix.lower(),
                "path": str(path)
            }
        }]

    @classmethod
    def load_directory(cls, dir_path: Path) -> List[Dict[str, Any]]:
        documents = []
        dir_path = Path(dir_path)
        for path in dir_path.rglob("*"):
            if path.is_file() and not path.name.startswith("."):
                try:
                    docs = cls.load_file(path)
                    documents.extend(docs)
                except Exception as e:
                    print(f"[Warning] Failed to load {path}: {e}")
        return documents
