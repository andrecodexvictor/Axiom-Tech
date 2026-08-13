# syntax=docker/dockerfile:1.7

ARG PYTHON_BASE=python:3.11-slim-trixie@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff
ARG NODE_BASE=node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32
ARG NGINX_BASE=nginx:1.29-alpine-slim@sha256:c9366b8c560169b101ca0e5422ed063b20779e6454c2326b9c9704225c9b0c08

FROM ${PYTHON_BASE} AS api-dependencies

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

COPY requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv "${VIRTUAL_ENV}" \
    && "${VIRTUAL_ENV}/bin/pip" install -r requirements.txt \
    && find "${VIRTUAL_ENV}" -type d -name __pycache__ -prune -exec rm -rf {} +

FROM ${PYTHON_BASE} AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    HOME=/app \
    AXIOM_DOCUMENTS_DIR=/app/documentos \
    AXIOM_CHROMA_PATH=/data/chroma \
    AXIOM_CHROMA_COLLECTION=axiom_knowledge \
    AXIOM_VECTOR_BACKEND=chroma \
    AXIOM_EMBEDDING_PROVIDER=deterministic \
    AXIOM_EMBEDDING_DIMENSIONS=384 \
    AXIOM_NVIDIA_ENABLED=false \
    AXIOM_WEB_ENABLED=false

WORKDIR /app

RUN groupadd --system axiom \
    && useradd --system --gid axiom --home-dir /app --no-create-home axiom \
    && mkdir -p /data/chroma \
    && chown -R axiom:axiom /data /app

COPY --from=api-dependencies /opt/venv /opt/venv
COPY --chown=axiom:axiom app ./app
COPY --chown=axiom:axiom documentos ./documentos

USER axiom
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM ${NODE_BASE} AS frontend-build

ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:${PATH}

WORKDIR /workspace/frontend

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN --mount=type=cache,id=axiom-pnpm-store,target=/pnpm/store \
    pnpm config set store-dir /pnpm/store \
    && pnpm install --frozen-lockfile

COPY frontend/index.html frontend/tsconfig.json frontend/vite.config.ts ./
COPY frontend/src ./src

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm build

FROM ${NGINX_BASE} AS frontend

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=frontend-build /workspace/frontend/dist /usr/share/nginx/html

EXPOSE 80
