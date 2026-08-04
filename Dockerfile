# syntax=docker/dockerfile:1

FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AXIOM_DOCUMENTS_DIR=/app/documentos \
    AXIOM_CHROMA_PATH=/data/chroma \
    AXIOM_CHROMA_COLLECTION=axiom_knowledge \
    AXIOM_VECTOR_BACKEND=chroma \
    AXIOM_NVIDIA_ENABLED=false \
    AXIOM_WEB_ENABLED=false

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY documentos ./documentos

RUN groupadd --system axiom && useradd --system --gid axiom --home-dir /app axiom \
    && mkdir -p /data/chroma \
    && chown -R axiom:axiom /app /data

USER axiom
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:20-alpine AS frontend-build

WORKDIR /workspace/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN npm install --global pnpm@9.15.4 && pnpm install --frozen-lockfile

COPY frontend ./
ARG VITE_API_BASE_URL=""
RUN VITE_API_BASE_URL=$VITE_API_BASE_URL pnpm build

FROM nginx:1.27-alpine AS frontend

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
