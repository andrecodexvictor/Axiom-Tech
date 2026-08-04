import type { ReactNode } from 'react';
import {
  ApiError,
  type Citation,
  type IngestResponse,
  type QueryResponse,
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

export type IconName =
  | 'arrow-up'
  | 'book'
  | 'check'
  | 'chevron'
  | 'close'
  | 'database'
  | 'file'
  | 'menu'
  | 'nodes'
  | 'refresh'
  | 'search'
  | 'spark'
  | 'warning';

const domainLabels: Record<string, string> = {
  rh: 'Pessoas & cultura',
  juridico: 'Jurídico & LGPD',
  engenharia: 'Engenharia',
  api_spec: 'Especificações de API',
  web: 'Pesquisa técnica externa',
  geral: 'Conhecimento geral',
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
    case 'chevron':
      return <svg {...common}><path d="m8 10 4 4 4-4" /></svg>;
    case 'close':
      return <svg {...common}><path d="m6 6 12 12M18 6 6 18" /></svg>;
    case 'database':
      return <svg {...common}><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /></svg>;
    case 'file':
      return <svg {...common}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" /><path d="M14 2v6h6M8 13h8M8 17h6" /></svg>;
    case 'menu':
      return <svg {...common}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
    case 'nodes':
      return <svg {...common}><circle cx="6" cy="6" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="12" cy="18" r="2" /><path d="m7.7 7.1 2.7 8.1M16.3 7.1l-2.7 8.1M8 6h8" /></svg>;
    case 'refresh':
      return <svg {...common}><path d="M20 11a8 8 0 0 0-14.6-4.6L3 9" /><path d="M3 4v5h5M4 13a8 8 0 0 0 14.6 4.6L21 15" /><path d="M21 20v-5h-5" /></svg>;
    case 'search':
      return <svg {...common}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>;
    case 'spark':
      return <svg {...common}><path d="m12 3 1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6L12 3Z" /><path d="m19 16 .7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" /></svg>;
    case 'warning':
      return <svg {...common}><path d="M10.3 4.2 2.7 18a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4m0 4h.01" /></svg>;
  }
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return 'Algo inesperado interrompeu a solicitação. Tente novamente.';
}

export function formatDomain(domain: string): string {
  return domainLabels[domain] ?? domain.replace(/[_-]/g, ' ');
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat('pt-BR').format(value);
}

export function formatIngestMessage(result: IngestResponse): string {
  const changed = result.inserted + result.updated;
  const verb = changed === 1 ? 'atualização aplicada' : 'atualizações aplicadas';
  const unchanged = result.unchanged === 1 ? 'arquivo já estava atual' : 'arquivos já estavam atuais';

  if (changed === 0) {
    return `Índice verificado: ${result.unchanged} ${unchanged}.`;
  }

  return `${changed} ${verb}; ${result.unchanged} ${unchanged}.`;
}

function AnswerText({ answer }: { answer: string }) {
  const paragraphs = answer.trim().split(/\n\s*\n/).filter(Boolean);

  return (
    <div className="answer-copy">
      {paragraphs.map((paragraph, index) => {
        const lines = paragraph.split('\n').filter(Boolean);
        const isList = lines.length > 1 && lines.every((line) => /^[-*•]\s+/.test(line));

        if (isList) {
          return (
            <ul key={`${paragraph}-${index}`}>
              {lines.map((line) => <li key={line}>{line.replace(/^[-*•]\s+/, '')}</li>)}
            </ul>
          );
        }

        return <p key={`${paragraph}-${index}`}>{paragraph}</p>;
      })}
    </div>
  );
}

export function LoadingAnswer() {
  return (
    <section className="answer-panel answer-panel--loading" aria-busy="true" aria-labelledby="answer-heading">
      <div className="answer-heading-row">
        <div>
          <span className="skeleton skeleton--label" />
          <span className="skeleton skeleton--title" />
        </div>
        <span className="skeleton skeleton--badge" />
      </div>
      <div className="skeleton-copy" aria-hidden="true">
        <span className="skeleton" />
        <span className="skeleton" />
        <span className="skeleton skeleton--short" />
        <span className="skeleton" />
      </div>
      <div className="loading-sources" aria-hidden="true">
        <span className="skeleton skeleton--label" />
        <span className="skeleton" />
        <span className="skeleton skeleton--medium" />
      </div>
      <p className="sr-only">Consultando as fontes internas e preparando uma resposta fundamentada.</p>
    </section>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="sources-empty">Nenhuma fonte foi devolvida para esta resposta.</p>;
  }

  return (
    <ol className="source-list">
      {citations.map((citation, index) => {
        const score = Math.max(0, Math.min(100, Math.round(citation.score * 100)));
        const locator = citation.page
          ? `página ${citation.page}`
          : citation.slide
            ? `slide ${citation.slide}`
            : citation.sheet
              ? `planilha ${citation.sheet}`
              : `trecho ${citation.chunk_index + 1}`;
        return (
          <li className="source-item" key={`${citation.id}-${citation.chunk_id}`}>
            <span className="source-order" aria-hidden="true">{index + 1}</span>
            <div className="source-main">
              <strong>{citation.source}</strong>
              <span>{formatDomain(citation.domain)} · {citation.file_type.toUpperCase()} · {locator}</span>
              {citation.path && <code title={citation.path}>{citation.path}</code>}
              {citation.url && (
                <a href={citation.url} target="_blank" rel="noreferrer noopener">
                  Abrir fonte externa
                </a>
              )}
            </div>
            <span className="source-score" aria-label={`${score}% de relevância`}>{score}%</span>
          </li>
        );
      })}
    </ol>
  );
}

export function AnswerPanel({ response, question }: { response: QueryResponse; question: string }) {
  return (
    <article className="answer-panel" aria-labelledby="answer-heading">
      <header className="answer-heading-row">
        <div>
          <p className="section-label">Resposta fundamentada</p>
          <h2 id="answer-heading">{question}</h2>
        </div>
        <span className={`grounding-badge ${response.grounded ? 'grounding-badge--verified' : 'grounding-badge--caution'}`}>
          <Icon name={response.grounded ? 'check' : 'warning'} size={15} />
          {response.grounded ? 'Com fontes internas' : 'Evidência limitada'}
        </span>
      </header>

      {!response.grounded && (
        <div className="integrity-note" role="note">
          <Icon name="warning" size={18} />
          <p>Esta resposta não encontrou evidência interna suficiente para uma confirmação completa. Verifique a fonte antes de agir.</p>
        </div>
      )}

      <AnswerText answer={response.answer} />

      <dl className="response-metadata" aria-label="Metadados da resposta">
        <div><dt>Área</dt><dd>{formatDomain(response.domain)}</dd></div>
        <div><dt>Especialista</dt><dd>{response.specialist}</dd></div>
        <div><dt>Evidências</dt><dd>{formatCount(response.citations.length)} fontes</dd></div>
        <div><dt>Ajustes de busca</dt><dd>{formatCount(response.rewrite_count)}</dd></div>
      </dl>

      <section className="sources-section" id="sources" aria-labelledby="sources-heading">
        <div className="subsection-heading">
          <div>
            <p className="section-label">Rastreabilidade</p>
            <h3 id="sources-heading">Fontes consultadas</h3>
          </div>
          <span>{formatCount(response.citations.length)} itens</span>
        </div>
        <CitationList citations={response.citations} />
      </section>

      <details className="trace-disclosure">
        <summary>
          <span><Icon name="nodes" size={17} /> Trajeto da consulta</span>
          <span>{formatCount(response.trace.length)} eventos <Icon name="chevron" size={16} /></span>
        </summary>
        {response.trace.length > 0 ? (
          <ol className="trace-list">
            {response.trace.map((trace, index) => (
              <li key={`${trace.node}-${trace.event}-${index}`}>
                <div><strong>{trace.node}</strong><span>{trace.event}</span></div>
                <p>{trace.details}</p>
              </li>
            ))}
          </ol>
        ) : <p className="trace-empty">O serviço não informou eventos desta consulta.</p>}
      </details>
    </article>
  );
}

export function EmptyAnswer() {
  return (
    <section className="empty-answer" aria-labelledby="empty-answer-heading">
      <div className="empty-answer-icon"><Icon name="book" size={22} /></div>
      <div>
        <h2 id="empty-answer-heading">Comece por uma pergunta que exija evidência.</h2>
        <p>O Axiom consulta políticas, procedimentos, especificações e documentos internos antes de responder.</p>
      </div>
    </section>
  );
}

export function QueryError({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <section className="error-state" role="alert" aria-labelledby="query-error-heading">
      <Icon name="warning" size={22} />
      <div><h2 id="query-error-heading">A resposta não pôde ser preparada</h2><p>{error}</p></div>
      {onRetry && (
        <button className="button button--secondary" type="button" onClick={onRetry}>
          <Icon name="refresh" size={16} />
          Tentar novamente
        </button>
      )}
    </section>
  );
}

export function StatusRail({
  state,
  indexState,
  onRefresh,
  onReindex,
}: {
  state: StatusState;
  indexState: IndexState;
  onRefresh: () => void;
  onReindex: () => void;
}) {
  const status = state.data;
  const isLoading = state.phase === 'loading' && !status;
  const isIndexing = indexState.phase === 'loading';

  return (
    <aside className="status-rail" aria-label="Estado do sistema">
      <section className="rail-section">
        <div className="rail-heading">
          <div><p className="section-label">Índice corporativo</p><h2>Pronto para consultar</h2></div>
          <button className="icon-button" type="button" onClick={onRefresh} disabled={state.phase === 'loading'} aria-label="Atualizar status do sistema"><Icon name="refresh" size={17} /></button>
        </div>
        {isLoading && <div className="status-skeleton" aria-busy="true"><span className="skeleton skeleton--medium" /><span className="skeleton" /><span className="skeleton skeleton--short" /></div>}
        {status && (
          <>
            <div className="system-health" role="status"><span className={`status-dot ${status.status === 'ok' ? 'status-dot--online' : 'status-dot--offline'}`} /><span>{status.status === 'ok' ? 'Serviço disponível' : 'Estado requer atenção'}</span></div>
            <dl className="system-details">
              <div><dt><Icon name="database" size={16} /> Fragmentos</dt><dd>{formatCount(status.vector_store.document_count)}</dd></div>
              <div><dt><Icon name="book" size={16} /> Armazenamento</dt><dd>{status.vector_store.backend}</dd></div>
              <div><dt><Icon name="spark" size={16} /> Modelo</dt><dd>{status.models.remote_enabled ? status.models.gateway : 'Modo local'}</dd></div>
              {status.web_research && (
                <div><dt><Icon name="search" size={16} /> Pesquisa web</dt><dd>{status.web_research.configured ? 'Configurada' : 'Desativada'}</dd></div>
              )}
            </dl>
          </>
        )}
        {state.phase === 'error' && <div className="rail-error" role="alert"><p>{state.error}</p><button className="text-button" type="button" onClick={onRefresh}>Tentar status novamente</button></div>}
      </section>

      <section className="rail-section rail-section--index">
        <div className="rail-heading rail-heading--stacked">
          <div><p className="section-label">Manutenção</p><h2>Atualizar o índice</h2></div>
          <p>Releia os documentos configurados sem duplicar trechos já indexados.</p>
        </div>
        <button className="button button--secondary button--full" type="button" onClick={onReindex} disabled={isIndexing}>
          <Icon name={isIndexing ? 'refresh' : 'database'} size={17} />
          {isIndexing ? 'Atualizando índice…' : 'Reindexar documentos'}
        </button>
        {indexState.message && <p className={`index-feedback index-feedback--${indexState.phase}`} role={indexState.phase === 'error' ? 'alert' : 'status'}><Icon name={indexState.phase === 'error' ? 'warning' : 'check'} size={16} />{indexState.message}</p>}
      </section>

      {status && <p className="rail-footer">v{status.version} · coleção {status.vector_store.collection}</p>}
    </aside>
  );
}

export function NavigationContent({ onNavigate, recentQuestion }: { onNavigate?: () => void; recentQuestion?: string }) {
  return (
    <>
      <div className="brand-lockup"><span className="brand-mark" aria-hidden="true"><span /></span><span>Axiom <strong>Tech</strong></span></div>
      <nav className="primary-navigation" aria-label="Navegação principal">
        <a href="#ask" aria-current="page" onClick={onNavigate}><Icon name="search" size={18} />Consultar conhecimento</a>
        <a href="#response" onClick={onNavigate}><Icon name="book" size={18} />Fontes e evidências</a>
        <a href="#system" onClick={onNavigate}><Icon name="database" size={18} />Estado do índice</a>
      </nav>
      <div className="sidebar-divider" />
      <section className="sidebar-context" aria-labelledby="workspace-heading"><p className="sidebar-label" id="workspace-heading">Espaço atual</p><p>Base corporativa</p><span>Políticas, engenharia, jurídico e APIs</span></section>
      {recentQuestion && <section className="sidebar-context sidebar-context--recent" aria-labelledby="recent-heading"><p className="sidebar-label" id="recent-heading">Última consulta</p><p title={recentQuestion}>{recentQuestion}</p></section>}
      <p className="sidebar-security"><Icon name="check" size={15} /> Respostas com rastreabilidade</p>
    </>
  );
}

export type AnswerContent = ReactNode;
