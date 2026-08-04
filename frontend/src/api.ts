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

export interface SystemStatus {
  status: 'ok' | string;
  version: string;
  vector_store: {
    backend: string;
    collection: string;
    document_count: number;
  };
  models: {
    gateway: string;
    remote_enabled: boolean;
  };
  documents_dir: string;
  web_research?: {
    enabled: boolean;
    configured: boolean;
    allowlist_hosts: number;
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

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim() ?? '';
export const API_BASE_URL = configuredBaseUrl.replace(/\/$/, '');

function getErrorMessage(payload: unknown, fallback: string): string {
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
      return detail;
    }

    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) {
      return message;
    }
  }

  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...init.headers,
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error;
    }

    throw new ApiError('Não foi possível alcançar o serviço de conhecimento.');
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
    });
  },

  status(signal?: AbortSignal) {
    return request<SystemStatus>('/api/v1/status', { signal });
  },
};
