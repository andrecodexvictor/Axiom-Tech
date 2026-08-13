export type Domain = 'rh' | 'juridico' | 'engenharia' | 'api_spec' | 'web';

export interface QueryRequest {
  question: string;
  domain?: Domain | null;
  top_k?: number;
}

export interface Citation {
  id: string;
  source: string;
  domain: string;
  file_type: string;
  chunk_id: string;
  chunk_index: number;
  score: number;
  path?: string;
  url?: string;
  page?: number;
  slide?: number;
  sheet?: string;
}

export interface TraceEvent {
  node: string;
  event: string;
  details: string;
}

export interface QueryResponse {
  answer: string;
  domain: string;
  specialist: string;
  citations: Citation[];
  trace: TraceEvent[];
  rewrite_count: number;
  grounded: boolean;
  duration_ms?: number;
  timings_ms?: Record<string, number>;
}

export interface IngestFile {
  source: string;
  status: string;
  chunks: number;
  message?: string;
}

export interface IngestResponse {
  received: number;
  inserted: number;
  updated: number;
  unchanged: number;
  skipped: number;
  files: IngestFile[];
}

export interface SourceStatus {
  path: string;
  domain: string;
  file_type: string;
  size_bytes: number;
  modified_at: string;
  indexed_chunks: number;
  expected_chunks: number;
  status: 'indexed' | 'pending' | 'stale' | 'error' | string;
  message?: string;
}

export interface SourcesResponse {
  total: number;
  indexed: number;
  pending: number;
  sources: SourceStatus[];
}

export interface SystemStatus {
  status: 'ok' | string;
  version: string;
  vector_store: {
    backend: string;
    collection: string;
    physical_collection?: string;
    document_count: number;
    source_count?: number | null;
    ready?: boolean;
    reason?: string | null;
    embedding?: {
      provider: string;
      model?: string;
      dimensions: number;
      fingerprint: string;
      mode: string;
      configured: boolean;
    };
    retrieval?: {
      strategy: string;
      candidate_multiplier: number;
      min_score: number;
      lexical_weight: number;
      mmr_lambda: number;
    };
  };
  models: {
    gateway: string;
    remote_enabled: boolean;
    model?: string;
    fallback?: string;
    routes?: Array<{
      name: string;
      provider: string;
      model?: string;
      configured: boolean;
      circuit_state: string;
    }>;
  };
  documents_dir: string;
  web_research?: {
    enabled: boolean;
    configured: boolean;
    allowlist_hosts: number;
  };
  observability?: {
    provider: string;
    enabled: boolean;
    configured: boolean;
    project: string;
    inputs_hidden: boolean;
    outputs_hidden: boolean;
  };
}

export class ApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

const REQUEST_TIMEOUT_MS = 45_000;
const MAINTENANCE_TIMEOUT_MS = 180_000;

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? '';
export const API_BASE_URL = configuredBaseUrl.replace(/\/$/, '');

function getErrorMessage(payload: unknown, fallback: string): string {
  const limit = (value: string) => value.trim().slice(0, 280);

  if (typeof payload === 'string' && payload.trim()) {
    const text = payload.trim();
    const looksLikeMarkup = /^\s*</.test(text) || /<\/?(?:html|body|head|script)\b/i.test(text);
    if (!looksLikeMarkup && text.length <= 280) {
      return text;
    }
  }

  if (payload && typeof payload === 'object') {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) {
      return limit(detail);
    }

    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) {
      return limit(message);
    }
  }

  return fallback;
}

export function isAbortError(error: unknown): boolean {
  return (error instanceof DOMException && error.name === 'AbortError')
    || (error instanceof Error && error.name === 'AbortError');
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const forwardAbort = () => controller.abort();
  init.signal?.addEventListener('abort', forwardAbort, { once: true });

  let response: Response;

  try {
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } catch (error) {
    if (timedOut) {
      throw new ApiError('O serviço demorou mais que o esperado. Tente novamente.');
    }

    if (isAbortError(error)) {
      throw error;
    }

    throw new ApiError('Não foi possível alcançar o serviço de conhecimento.');
  } finally {
    window.clearTimeout(timeoutId);
    init.signal?.removeEventListener('abort', forwardAbort);
  }

  const contentType = response.headers.get('content-type') ?? '';
  const payload: unknown = contentType.includes('application/json')
    ? await response.json().catch(() => undefined)
    : await response.text().catch(() => undefined);

  if (!response.ok) {
    throw new ApiError(
      getErrorMessage(payload, `A solicitação falhou (${response.status}).`),
      response.status,
    );
  }

  return payload as T;
}

export const knowledgeApi = {
  query(payload: QueryRequest, signal?: AbortSignal) {
    return request<QueryResponse>('/api/v1/query', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  },

  ingest(signal?: AbortSignal) {
    return request<IngestResponse>('/api/v1/ingest', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    }, MAINTENANCE_TIMEOUT_MS);
  },

  rebuildEmbeddings(signal?: AbortSignal) {
    return request<IngestResponse>('/api/v1/embeddings/rebuild', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    }, MAINTENANCE_TIMEOUT_MS);
  },

  sources(signal?: AbortSignal) {
    return request<SourcesResponse>('/api/v1/sources', { signal, cache: 'no-store' });
  },

  status(signal?: AbortSignal) {
    return request<SystemStatus>('/api/v1/status', { signal, cache: 'no-store' });
  },
};
