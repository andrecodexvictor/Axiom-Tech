import { memo, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  isAbortError,
  knowledgeApi,
  type Citation,
  type IngestResponse,
  type QueryResponse,
  type SourcesResponse,
  type SourcePreview,
  type SystemStatus,
} from './api';

export type StatusState = {
  phase: 'loading' | 'ready' | 'error';
  data?: SystemStatus;
  error?: string;
};

export type IndexState = {
  phase: 'idle' | 'loading' | 'success' | 'error';
  message?: string;
};

export type SourceState = {
  phase: 'loading' | 'ready' | 'error';
  data?: SourcesResponse;
  error?: string;
};

export type IconName =
  | 'arrow-up'
  | 'book'
  | 'check'
  | 'clock'
  | 'chevron'
  | 'copy'
  | 'database'
  | 'external-link'
  | 'file'
  | 'info'
  | 'nodes'
  | 'refresh'
  | 'search'
  | 'settings'
  | 'upload'
  | 'warning';

const domainLabels: Record<string, string> = {
  rh: 'Pessoas & cultura',
  juridico: 'Jurídico & LGPD',
  engenharia: 'Engenharia & operações',
  api_spec: 'Repositórios & APIs',
  estrategico: 'Estratégia & governança',
  comunicacao: 'Comunicação & institucional',
  web: 'Pesquisa técnica externa',
  geral: 'Base corporativa',
};

const specialistLabels: Record<string, string> = {
  hr: 'Pessoas & cultura',
  hr_specialist: 'Pessoas & cultura',
  doc_agent: 'Pessoas & cultura',
  legal: 'Jurídico & conformidade',
  legal_specialist: 'Jurídico & conformidade',
  legal_agent: 'Jurídico & conformidade',
  engineering: 'Engenharia & operações',
  engineering_operations: 'Engenharia & operações',
  engineering_agent: 'Engenharia & operações',
  repository: 'Repositórios & APIs',
  repo_agent: 'Repositórios & APIs',
  estrategico: 'Estratégia & governança',
  strategic: 'Estratégia & governança',
  strategic_agent: 'Estratégia & governança',
  strategic_planning: 'Estratégia & governança',
  strategy_specialist: 'Estratégia & governança',
  comunicacao: 'Comunicação & institucional',
  communication: 'Comunicação & institucional',
  communication_agent: 'Comunicação & institucional',
  corporate_communications: 'Comunicação & institucional',
  communication_specialist: 'Comunicação & institucional',
  web_research: 'Pesquisa técnica externa',
};

const responseModeLabels: Record<string, string> = {
  concise: 'Direta (concisa)',
  detailed: 'Detalhada',
  checklist: 'Checklist',
  evidence: 'Evidências',
};

const traceNodeLabels: Record<string, string> = {
  supervisor: 'Classificação da pergunta',
  classify: 'Classificação da pergunta',
  route: 'Definição da área',
  retrieve: 'Busca de evidências',
  retrieval: 'Busca de evidências',
  grade: 'Verificação das evidências',
  rewrite: 'Ajuste da busca',
  synthesize: 'Preparação da resposta',
  generate: 'Preparação da resposta',
  web_research: 'Pesquisa externa permitida',
};

const traceEventLabels: Record<string, string> = {
  started: 'Iniciada',
  completed: 'Concluída',
  passed: 'Aprovada',
  fallback: 'Resposta limitada',
  rewrite: 'Busca ajustada',
  routed: 'Encaminhada',
  retrieved: 'Fontes recuperadas',
};

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
  };

  switch (name) {
    case 'arrow-up':
      return <svg {...common}><path d="M12 18V6m0 0-5 5m5-5 5 5" /></svg>;
    case 'book':
      return <svg {...common}><path d="M4.5 5.5A2.5 2.5 0 0 1 7 3h11v16H7a2.5 2.5 0 0 0-2.5 2.5v-16Z" /><path d="M7 3v16" /></svg>;
    case 'check':
      return <svg {...common}><path d="m5 12 4.2 4.2L19 6.5" /></svg>;
    case 'clock':
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.2 2" /></svg>;
    case 'chevron':
      return <svg {...common}><path d="m8 10 4 4 4-4" /></svg>;
    case 'copy':
      return <svg {...common}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg>;
    case 'database':
      return <svg {...common}><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /></svg>;
    case 'external-link':
      return <svg {...common}><path d="M14 5h5v5M19 5l-8 8" /><path d="M17 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5" /></svg>;
    case 'file':
      return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></svg>;
    case 'info':
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M12 12v4" /></svg>;
    case 'nodes':
      return <svg {...common}><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="m7.7 7.1 2.7 8.1M16.3 7.1l-2.7 8.1M8 6h8" /></svg>;
    case 'refresh':
      return <svg {...common}><path d="M20 11a8 8 0 0 0-14.6-4.6L3 9" /><path d="M3 4v5h5M4 13a8 8 0 0 0 14.6 4.6L21 15" /><path d="M21 20v-5h-5" /></svg>;
    case 'search':
      return <svg {...common}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>;
    case 'settings':
      return <svg {...common}><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h7M15 18h5" /><circle cx="16" cy="6" r="2" /><circle cx="8" cy="12" r="2" /><circle cx="13" cy="18" r="2" /></svg>;
    case 'upload':
      return <svg {...common}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>;
    case 'warning':
      return <svg {...common}><path d="M10.3 4.2 2.7 18a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 4h.01" /></svg>;
  }
}

export function formatResponseMode(mode?: string): string {
  if (!mode) return 'Direta';
  return responseModeLabels[mode] ?? sentenceCase(mode);
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return 'Algo inesperado interrompeu a solicitação. Tente novamente.';
}

function sentenceCase(value: string): string {
  const normalized = value.replace(/[_-]+/g, ' ').trim();
  return normalized ? normalized.charAt(0).toUpperCase() + normalized.slice(1) : 'Não informado';
}

export function formatDomain(domain: string): string {
  return domainLabels[domain] ?? sentenceCase(domain);
}

export function formatSpecialist(specialist: string): string {
  return specialistLabels[specialist] ?? sentenceCase(specialist);
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('pt-BR').format(value);
}

function formatDuration(value: number): string {
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1).replace('.', ',')} s`;
}

function pluralize(value: number, singular: string, plural: string): string {
  return `${formatCount(value)} ${value === 1 ? singular : plural}`;
}

export function formatIngestMessage(result: IngestResponse): string {
  const changed = result.inserted + result.updated;
  const parts = [
    pluralize(changed, 'trecho atualizado', 'trechos atualizados'),
    pluralize(result.unchanged, 'trecho já atual', 'trechos já atuais'),
  ];

  if (result.skipped > 0) {
    parts.push(pluralize(result.skipped, 'arquivo ignorado', 'arquivos ignorados'));
  }

  return `Índice concluído: ${parts.join(', ')}.`;
}

export function getSystemSummary(state: StatusState): {
  label: string;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
} {
  if (state.phase === 'loading' && !state.data) {
    return { label: 'Verificando a base', tone: 'neutral' };
  }

  if (state.phase === 'error') {
    return {
      label: state.data ? 'Status desatualizado' : 'Serviço indisponível',
      tone: 'danger',
    };
  }

  if (state.data?.status === 'empty' || state.data?.vector_store.ready === false) {
    return { label: 'Índice sem documentos', tone: 'warning' };
  }

  if (state.data?.status === 'ok') {
    return { label: 'Base disponível', tone: 'success' };
  }

  return { label: 'Operação limitada', tone: 'warning' };
}

function AnswerText({ answer }: { answer: string }) {
  const blocks = answer.trim().split(/\n\s*\n/).filter(Boolean);

  if (blocks.length === 0) {
    return <p className="answer-empty">O serviço não devolveu texto para esta resposta.</p>;
  }

  return (
    <div className="answer-copy">
      {blocks.map((block, index) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean);
        const isUnordered = lines.every((line) => /^[-*•]\s+/.test(line));
        const isOrdered = lines.every((line) => /^\d+[.)]\s+/.test(line));

        if (isUnordered) {
          return (
            <ul key={`answer-block-${index}`}>
              {lines.map((line, lineIndex) => (
                <li key={`answer-line-${index}-${lineIndex}`}>{line.replace(/^[-*•]\s+/, '')}</li>
              ))}
            </ul>
          );
        }

        if (isOrdered) {
          return (
            <ol key={`answer-block-${index}`}>
              {lines.map((line, lineIndex) => (
                <li key={`answer-line-${index}-${lineIndex}`}>{line.replace(/^\d+[.)]\s+/, '')}</li>
              ))}
            </ol>
          );
        }

        return <p key={`answer-block-${index}`}>{lines.join('\n')}</p>;
      })}
    </div>
  );
}

export function LoadingAnswer() {
  return (
    <section className="answer-panel answer-panel--loading" aria-busy="true" aria-labelledby="loading-answer-heading">
      <p className="sr-only" id="loading-answer-heading">Consultando a base corporativa.</p>
      <div className="loading-answer-heading" aria-hidden="true">
        <span className="skeleton skeleton--label" />
        <span className="skeleton skeleton--title" />
      </div>
      <div className="skeleton-copy" aria-hidden="true">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton skeleton--short" />
        <span className="skeleton" />
        <span className="skeleton skeleton--medium" />
      </div>
      <div className="skeleton-facts" aria-hidden="true">
        <span className="skeleton skeleton--medium" />
        <span className="skeleton skeleton--short" />
      </div>
      <p className="loading-message">Buscando trechos, verificando aderência e preparando a síntese…</p>
    </section>
  );
}

function responseHasEvidence(response: QueryResponse): boolean {
  return response.grounded && response.citations.length > 0;
}

export const AnswerPanel = memo(function AnswerPanel({ response, question }: { response: QueryResponse; question: string }) {
  const hasEvidence = responseHasEvidence(response);

  return (
    <article className="answer-panel" aria-labelledby="answer-heading">
      <header className="answer-question">
        <p>Sua pergunta</p>
        <h2 id="answer-heading" tabIndex={-1}>{question}</h2>
      </header>

      <div className="answer-status-row">
        <h3>Resposta</h3>
        <span className={`grounding-badge grounding-badge--${hasEvidence ? 'verified' : 'caution'}`}>
          <Icon name={hasEvidence ? 'check' : 'warning'} size={15} />
          {hasEvidence
            ? `${pluralize(response.citations.length, 'fonte verificada', 'fontes verificadas')}`
            : 'Evidência insuficiente'}
        </span>
      </div>

      {!hasEvidence && (
        <div className="integrity-note" role="note">
          <Icon name="warning" size={18} />
          <div>
            <strong>Não trate esta resposta como confirmação.</strong>
            <p>A base não devolveu evidência suficiente. Confirme a informação com o documento ou responsável da área antes de agir.</p>
          </div>
        </div>
      )}

      <AnswerText answer={response.answer} />

      <dl className="answer-facts" aria-label="Contexto da resposta">
        <div><dt>Área consultada</dt><dd>{formatDomain(response.domain)}</dd></div>
        <div><dt>Rota responsável</dt><dd>{formatSpecialist(response.specialist)}</dd></div>
        {response.response_mode && (
          <div><dt>Modo da resposta</dt><dd>{formatResponseMode(response.response_mode)}</dd></div>
        )}
        {response.rewrite_count > 0 && (
          <div><dt>Ajustes de busca</dt><dd>{formatCount(response.rewrite_count)}</dd></div>
        )}
        {response.duration_ms != null && response.duration_ms > 0 && (
          <div><dt>Tempo total</dt><dd>{formatDuration(response.duration_ms)}</dd></div>
        )}
      </dl>

      <details className="trace-disclosure">
        <summary>
          <span><Icon name="nodes" size={17} /> Como a consulta foi processada</span>
          <span>{pluralize(response.trace.length, 'etapa', 'etapas')} <Icon name="chevron" size={16} /></span>
        </summary>
        {response.trace.length > 0 ? (
          <ol className="trace-list">
            {response.trace.map((trace, index) => (
              <li key={`${trace.node}-${trace.event}-${index}`}>
                <div>
                  <strong>{traceNodeLabels[trace.node] ?? sentenceCase(trace.node)}</strong>
                  <span>{traceEventLabels[trace.event] ?? sentenceCase(trace.event)}</span>
                </div>
                <p>{trace.details}</p>
              </li>
            ))}
          </ol>
        ) : <p className="trace-empty">O serviço não informou etapas desta consulta.</p>}
      </details>
    </article>
  );
});

export function EmptyAnswer() {
  return (
    <section className="empty-answer" aria-labelledby="empty-answer-heading">
      <div className="empty-answer-icon"><Icon name="book" size={21} /></div>
      <div>
        <h2 id="empty-answer-heading">A resposta aparecerá aqui.</h2>
        <p>Quando houver suporte no corpus, você verá a síntese, a área responsável e cada fonte usada na verificação.</p>
      </div>
    </section>
  );
}

export function QueryError({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <section className="error-state" role="alert" aria-labelledby="query-error-heading">
      <Icon name="warning" size={21} />
      <div>
        <h2 id="query-error-heading" tabIndex={-1}>Não foi possível concluir a consulta</h2>
        <p>{error}</p>
      </div>
      {onRetry && (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          <Icon name="refresh" size={16} />
          Tentar novamente
        </button>
      )}
    </section>
  );
}

function getCitationLocator(citation: Citation): string {
  if (citation.page != null) return `Página ${citation.page}`;
  if (citation.slide != null) return `Slide ${citation.slide}`;
  if (citation.sheet) return `Planilha ${citation.sheet}`;
  return `Trecho ${citation.chunk_index + 1}`;
}

function getSafeExternalUrl(url?: string): string | undefined {
  if (!url) return undefined;

  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : undefined;
  } catch {
    return undefined;
  }
}

function CitationItem({ citation, order }: { citation: Citation; order: number }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle');
  const copyResetTimerRef = useRef<number | null>(null);
  const safeUrl = getSafeExternalUrl(citation.url);
  const locator = getCitationLocator(citation);
  const score = Number.isFinite(citation.score)
    ? Math.max(0, Math.min(100, Math.round(citation.score * 100)))
    : null;

  const copyReference = async () => {
    const reference = [
      citation.source,
      formatDomain(citation.domain),
      citation.file_type ? citation.file_type.toUpperCase() : 'Documento',
      locator,
      citation.path,
      safeUrl,
    ].filter(Boolean).join(' · ');

    try {
      if (!navigator.clipboard) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(reference);
      setCopyState('copied');
      if (copyResetTimerRef.current != null) window.clearTimeout(copyResetTimerRef.current);
      copyResetTimerRef.current = window.setTimeout(() => {
        copyResetTimerRef.current = null;
        setCopyState('idle');
      }, 1800);
    } catch {
      setCopyState('error');
    }
  };

  useEffect(() => () => {
    if (copyResetTimerRef.current != null) window.clearTimeout(copyResetTimerRef.current);
  }, []);

  return (
    <li className="source-item">
      <div className="source-heading">
        <span className="source-order" aria-hidden="true">{order}</span>
        <div>
          <h3>{citation.source}</h3>
          <p>{formatDomain(citation.domain)} · {citation.file_type?.toUpperCase() || 'DOCUMENTO'}</p>
        </div>
      </div>

      <dl className="source-locator">
        <div><dt>Localizador</dt><dd>{locator}</dd></div>
        {score != null && <div><dt>Correspondência</dt><dd>{score}%</dd></div>}
      </dl>

      {citation.path && <code className="source-path" title={citation.path}>{citation.path}</code>}

      <div className="source-actions">
        <button className="text-action" type="button" onClick={() => void copyReference()}>
          <Icon name={copyState === 'copied' ? 'check' : 'copy'} size={15} />
          {copyState === 'copied' ? 'Referência copiada' : copyState === 'error' ? 'Não foi possível copiar' : 'Copiar referência'}
        </button>
        {safeUrl && (
          <a href={safeUrl} target="_blank" rel="noreferrer noopener">
            Abrir fonte <Icon name="external-link" size={14} />
          </a>
        )}
      </div>
    </li>
  );
}

export const EvidencePanel = memo(function EvidencePanel({ response }: { response: QueryResponse }) {
  const hasEvidence = responseHasEvidence(response);

  return (
    <section className="evidence-panel" aria-labelledby="evidence-heading">
      <header className="panel-heading">
        <div>
          <p>Evidências</p>
          <h2 id="evidence-heading">Fontes da resposta</h2>
        </div>
        <span>{formatCount(response.citations.length)}</span>
      </header>

      {response.citations.length > 0 ? (
        <ol className="source-list">
          {response.citations.map((citation, index) => (
            <CitationItem citation={citation} order={index + 1} key={`${citation.id}-${citation.chunk_id}-${index}`} />
          ))}
        </ol>
      ) : (
        <div className="evidence-empty">
          <Icon name="warning" size={19} />
          <div>
            <strong>Nenhuma fonte verificável foi devolvida.</strong>
            <p>Refaça a pergunta com mais contexto ou consulte o responsável pelo documento.</p>
          </div>
        </div>
      )}

      {response.citations.length > 0 && (
        <p className={`evidence-note ${hasEvidence ? '' : 'evidence-note--warning'}`}>
          {hasEvidence
            ? 'A correspondência mede proximidade na busca; confirme o conteúdo no localizador antes de tomar uma decisão.'
            : 'As fontes foram consultadas, mas não sustentaram a resposta por completo.'}
        </p>
      )}
    </section>
  );
});

export function LoadingEvidence() {
  return (
    <section className="evidence-panel evidence-panel--loading" aria-busy="true" aria-label="Carregando evidências">
      <div className="panel-heading" aria-hidden="true">
        <div><span className="skeleton skeleton--label" /><span className="skeleton skeleton--heading" /></div>
      </div>
      <div className="source-loading" aria-hidden="true">
        <span className="skeleton skeleton--medium" />
        <span className="skeleton" />
        <span className="skeleton skeleton--short" />
      </div>
      <div className="source-loading" aria-hidden="true">
        <span className="skeleton skeleton--medium" />
        <span className="skeleton" />
        <span className="skeleton skeleton--short" />
      </div>
    </section>
  );
}

export function EvidenceGuide() {
  return (
    <section className="evidence-guide" aria-labelledby="evidence-guide-heading">
      <div className="guide-icon"><Icon name="check" size={18} /></div>
      <h2 id="evidence-guide-heading">Evidência antes de eloquência.</h2>
      <p>Cada resposta confirmada deve permitir que você volte ao documento de origem.</p>
      <ul>
        <li><Icon name="file" size={16} /><span><strong>Origem identificada</strong> com área e tipo de arquivo</span></li>
        <li><Icon name="search" size={16} /><span><strong>Localizador explícito</strong> para página, slide, planilha ou trecho</span></li>
        <li><Icon name="warning" size={16} /><span><strong>Limitação visível</strong> quando o corpus não sustenta a resposta</span></li>
      </ul>
    </section>
  );
}

function getStoreLabel(backend: string): string {
  const labels: Record<string, string> = {
    chroma: 'Índice local persistente',
    memory: 'Índice temporário em memória',
    'memory-fallback': 'Índice temporário em memória',
    pinecone: 'Índice gerenciado externo',
    'pinecone-unconfigured': 'Pinecone não configurado',
    unavailable: 'Recuperação indisponível',
  };
  return labels[backend.toLowerCase()] ?? 'Índice configurado';
}

function getStoreReason(reason?: string | null): string | undefined {
  const labels: Record<string, string> = {
    chroma_unavailable: 'Chroma não pôde ser carregado; o índice temporário não persiste entre reinícios.',
    embedding_not_configured: 'Embeddings não configurados; nenhuma fonte pode ser recuperada.',
    unsupported_vector_backend: 'O backend vetorial selecionado não é suportado neste runtime.',
    pinecone_not_configured: 'Pinecone foi selecionado sem credenciais e índice configurados.',
    vector_store_unavailable: 'O armazenamento vetorial está indisponível nesta configuração.',
  };
  return reason ? labels[reason] ?? reason : undefined;
}

function getEmbeddingLabel(status: SystemStatus): string {
  const embedding = status.vector_store.embedding;
  if (!embedding?.configured) return 'Indisponível';
  if (embedding.provider === 'deterministic') {
    return `Local determinístico · ${formatCount(embedding.dimensions)} dimensões · offline`;
  }
  return `${embedding.model || embedding.provider} · ${formatCount(embedding.dimensions)} dimensões`;
}

function getModelLabel(status: SystemStatus): string {
  const primary = status.models.routes?.[0];
  if (primary && primary.provider !== 'deterministic' && !primary.configured) {
    return 'Rota remota sem credencial · fallback local';
  }
  if (!status.models.remote_enabled || primary?.provider === 'deterministic') {
    return 'Resposta local determinística';
  }
  return `${primary?.model || status.models.model || 'Síntese remota habilitada'} · credencial configurada`;
}

function getObservabilityLabel(status: SystemStatus): string {
  const observability = status.observability;
  if (!observability?.configured) return 'Desativada';
  if (!observability.enabled) return 'Configurada, tracing desligado';
  if (observability.inputs_hidden && observability.outputs_hidden) {
    return 'LangSmith ativo · conteúdo oculto';
  }
  return 'LangSmith ativo';
}

function getWebResearchLabel(status: SystemStatus): string {
  if (status.web_research?.enabled && status.web_research.configured) return 'Disponível sob solicitação';
  if (status.web_research?.enabled) return 'Indisponível nesta configuração';
  return 'Desativada';
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}

function formatSourceStatus(status: string): { label: string; tone: string } {
  const labels: Record<string, { label: string; tone: string }> = {
    indexed: { label: 'Indexado', tone: 'indexed' },
    pending: { label: 'Pendente', tone: 'pending' },
    stale: { label: 'Precisa atualizar', tone: 'stale' },
    error: { label: 'Com erro', tone: 'error' },
  };
  return labels[status] ?? { label: sentenceCase(status), tone: 'pending' };
}

export const SourceInventoryPanel = memo(function SourceInventoryPanel({
  state,
  onRefresh,
}: {
  state: SourceState;
  onRefresh: () => void;
}) {
  const data = state.data;
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<{
    phase: 'idle' | 'loading' | 'ready' | 'error';
    data?: SourcePreview;
    error?: string;
  }>({ phase: 'idle' });
  const previewAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => previewAbortRef.current?.abort(), []);

  const togglePreview = async (path: string) => {
    previewAbortRef.current?.abort();
    if (openPath === path) {
      setOpenPath(null);
      setPreview({ phase: 'idle' });
      return;
    }

    const controller = new AbortController();
    previewAbortRef.current = controller;
    setOpenPath(path);
    setPreview({ phase: 'loading' });
    try {
      const nextPreview = await knowledgeApi.sourcePreview(path, controller.signal);
      if (!controller.signal.aborted) setPreview({ phase: 'ready', data: nextPreview });
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) return;
      setPreview({ phase: 'error', error: getErrorMessage(error) });
    }
  };
  return (
    <section className="source-inventory" aria-busy={state.phase === 'loading'} aria-labelledby="source-inventory-heading">
      <header className="panel-heading">
        <div>
          <p>Corpus integrado</p>
          <h2 id="source-inventory-heading">Documentos disponíveis</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onRefresh}
          disabled={state.phase === 'loading'}
          aria-label="Atualizar documentos integrados"
        >
          <Icon name="refresh" size={16} />
        </button>
      </header>

      {state.phase === 'loading' && !data && (
        <div className="inventory-loading" aria-busy="true" aria-label="Carregando documentos integrados">
          <span className="skeleton skeleton--medium" />
          <span className="skeleton" />
          <span className="skeleton skeleton--short" />
        </div>
      )}

      {state.phase === 'error' && (
        <div className="inventory-error" role="alert">
          <p>{state.error}</p>
          <button className="text-action" type="button" onClick={onRefresh}>Tentar novamente</button>
        </div>
      )}

      {data && (
        <>
          <div className="inventory-summary">
            <strong>{formatCount(data.indexed)} de {formatCount(data.total)} arquivos indexados</strong>
            <span>{data.pending > 0 ? `${formatCount(data.pending)} precisam de atenção` : 'Corpus sincronizado'}</span>
          </div>
          <ul className="inventory-list">
            {data.sources.map((source) => {
              const stateLabel = formatSourceStatus(source.status);
              return (
                <li key={source.path} className="inventory-item">
                  <div className="inventory-item-heading">
                    <Icon name="file" size={16} />
                    <div>
                      <strong title={source.path}>{source.path}</strong>
                      <span>{formatDomain(source.domain)} · {source.file_type.toUpperCase()} · {formatBytes(source.size_bytes)}</span>
                    </div>
                    <span className={`inventory-status inventory-status--${stateLabel.tone}`}>{stateLabel.label}</span>
                  </div>
                  <div className="inventory-item-meta">
                    <span>{formatCount(source.indexed_chunks)} / {formatCount(source.expected_chunks)} trechos</span>
                    {source.message && <span>{source.message}</span>}
                  </div>
                  <button
                    className="inventory-preview-toggle"
                    type="button"
                    aria-expanded={openPath === source.path}
                    onClick={() => void togglePreview(source.path)}
                  >
                    <Icon name="book" size={14} />
                    {openPath === source.path ? 'Fechar prévia' : 'Ver conteúdo extraído'}
                  </button>
                  {openPath === source.path && (
                    <div className="inventory-preview" aria-live="polite">
                      {preview.phase === 'loading' && <p>Extraindo uma prévia segura…</p>}
                      {preview.phase === 'error' && <p role="alert">{preview.error}</p>}
                      {preview.phase === 'ready' && preview.data && (
                        <>
                          <div className="inventory-preview-meta">
                            <span>{formatCount(preview.data.extracted_sections)} seções extraídas</span>
                            {preview.data.truncated && <span>Prévia limitada</span>}
                          </div>
                          <pre>{preview.data.content || 'Nenhum texto pôde ser extraído deste arquivo.'}</pre>
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}

      <p className="inventory-note">As prévias usam o mesmo extrator do índice e são limitadas; confirme informações críticas no documento original.</p>
    </section>
  );
});

export const StatusPanel = memo(function StatusPanel({
  state,
  indexState,
  onRefresh,
  onReindex,
  onRebuildEmbeddings,
}: {
  state: StatusState;
  indexState: IndexState;
  onRefresh: () => void;
  onReindex: () => void;
  onRebuildEmbeddings: () => void;
}) {
  const status = state.data;
  const summary = getSystemSummary(state);
  const isLoading = state.phase === 'loading';
  const isIndexing = indexState.phase === 'loading';

  return (
    <section className="status-panel" id="system-status" aria-busy={isLoading || isIndexing} aria-labelledby="system-status-heading">
      <header className="panel-heading">
        <div>
          <p>Operação</p>
          <h2 id="system-status-heading">Estado da base</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          aria-label="Atualizar estado da base"
        >
          <Icon name="refresh" size={16} />
        </button>
      </header>

      <div className={`system-summary system-summary--${summary.tone}`} role="status">
        <span className="status-dot" />
        <span>{summary.label}</span>
      </div>

      {isLoading && !status && (
        <div className="status-loading" aria-busy="true" aria-label="Carregando estado da base">
          <span className="skeleton skeleton--medium" />
          <span className="skeleton" />
          <span className="skeleton skeleton--short" />
        </div>
      )}

      {state.phase === 'error' && (
        <div className="status-error" role="alert">
          <p>{state.error}</p>
          <button className="text-action" type="button" onClick={onRefresh}>Tentar novamente</button>
        </div>
      )}

      {status && (
        <dl className="system-details">
          <div><dt>Conteúdo indexado</dt><dd>{status.vector_store.source_count != null ? `${pluralize(status.vector_store.source_count, 'arquivo', 'arquivos')} · ` : ''}{pluralize(status.vector_store.document_count, 'trecho', 'trechos')}</dd></div>
          <div><dt>Armazenamento</dt><dd>{getStoreLabel(status.vector_store.backend)}</dd></div>
          <div><dt>Embeddings</dt><dd>{getEmbeddingLabel(status)}</dd></div>
          <div><dt>Modo de resposta</dt><dd>{getModelLabel(status)}</dd></div>
          <div><dt>Observabilidade</dt><dd>{getObservabilityLabel(status)}</dd></div>
          <div><dt>Pesquisa externa</dt><dd>{getWebResearchLabel(status)}</dd></div>
        </dl>
      )}

      {status?.vector_store.reason && (
        <p className="status-note status-note--warning"><Icon name="warning" size={14} />{getStoreReason(status.vector_store.reason)}</p>
      )}

      <details className="maintenance-disclosure">
        <summary><span><Icon name="settings" size={16} /> Manutenção do índice</span><Icon name="chevron" size={16} /></summary>
        <div className="maintenance-content">
          <p>Reindexar relê os documentos configurados e pode alterar a base local. Trechos sem mudança não são duplicados.</p>
          <button className="button button--secondary button--full" type="button" onClick={onReindex} disabled={isIndexing}>
            <Icon name="refresh" size={16} />
            {isIndexing ? 'Reindexando documentos…' : 'Reindexar agora'}
          </button>
          <p className="maintenance-hint">Para recalcular todos os vetores com o provider/modelo atual, use a ação abaixo.</p>
          <button className="button button--secondary button--full" type="button" onClick={onRebuildEmbeddings} disabled={isIndexing}>
            <Icon name="database" size={16} />
            {isIndexing ? 'Gerando embeddings…' : 'Gerar embeddings novamente'}
          </button>
          {indexState.message && (
            <p className={`index-feedback index-feedback--${indexState.phase}`} role={indexState.phase === 'error' ? 'alert' : 'status'}>
              <Icon name={indexState.phase === 'error' ? 'warning' : 'check'} size={15} />
              {indexState.message}
            </p>
          )}
        </div>
      </details>

      {status && <p className="status-version">Interface conectada ao contrato v{status.version}</p>}
    </section>
  );
});
