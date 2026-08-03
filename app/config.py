import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

class Settings:
    # 3-Tier NVIDIA NIM API Keys
    KIMI_API_KEY: str = os.getenv("KIMI_API_KEY", "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")
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "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")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "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")

    PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    PINECONE_INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "axiom-tech-knowledge")
    PINECONE_ENVIRONMENT: str = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
    
    DOCUMENTS_DIR: Path = BASE_DIR / "documentos"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

settings = Settings()
