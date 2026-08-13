import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import {
  knowledgeApi,
  type Domain,
  type QueryRequest,
  type QueryResponse,
} from './api';
import {
  AnswerPanel,
  EmptyAnswer,
  EvidenceGuide,
  EvidencePanel,
  formatDomain,
  formatIngestMessage,
  getErrorMessage,
  getSystemSummary,
  Icon,
  LoadingAnswer,
  LoadingEvidence,
  QueryError,
  StatusPanel,
  type IndexState,
  type StatusState,
} from './components';

type RequestPhase = 'idle' | 'loading' | 'success' | 'error';

const MAX_QUESTION_LENGTH = 4000;

const suggestions: Array<{ question: string; domain: Domain; label: string }> = [
  {
    question: 'Como proceder em um incidente de severidade SEV-1?',
    domain: 'engenharia',
    label: 'Engenharia',
  },
  {
    question: 'Qual é a política de home office e vale-refeição?',
    domain: 'rh',
    label: 'Pessoas',
  },
  {
    question: 'Quais são os direitos dos titulares segundo a política de LGPD?',
    domain: 'juridico',
    label: 'Jurídico',
  },
  {
    question: 'Como a API interna descreve autenticação e limites de uso?',
    domain: 'api_spec',
    label: 'APIs',
  },
];

export default function App() {
  const [question, setQuestion] = useState('');
  const [domain, setDomain] = useState<Domain | ''>('');
  const [topK, setTopK] = useState(4);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [queryPhase, setQueryPhase] = useState<RequestPhase>('idle');
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<QueryRequest | null>(null);
  const [announcement, setAnnouncement] = useState('Pronto para receber uma pergunta.');
  const [systemState, setSystemState] = useState<StatusState>({ phase: 'loading' });
  const [indexState, setIndexState] = useState<IndexState>({ phase: 'idle' });

  const questionInputRef = useRef<HTMLTextAreaElement>(null);
  const queryAbortRef = useRef<AbortController | null>(null);
  const statusAbortRef = useRef<AbortController | null>(null);
  const indexAbortRef = useRef<AbortController | null>(null);

  const loadStatus = useCallback(async () => {
    statusAbortRef.current?.abort();
    const controller = new AbortController();
    statusAbortRef.current = controller;
    setSystemState((current) => ({ phase: 'loading', data: current.data }));

    try {
      const data = await knowledgeApi.status(controller.signal);
      if (!controller.signal.aborted) {
        setSystemState({ phase: 'ready', data });
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setSystemState((current) => ({
        phase: 'error',
        data: current.data,
        error: getErrorMessage(error),
      }));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    return () => statusAbortRef.current?.abort();
  }, [loadStatus]);

  useEffect(() => {
    const focusQuestion = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.matches('input, textarea, select, [contenteditable="true"]');
      if (event.key === '/' && !isTyping) {
        event.preventDefault();
        questionInputRef.current?.focus();
      }
    };

    window.addEventListener('keydown', focusQuestion);
    return () => window.removeEventListener('keydown', focusQuestion);
  }, []);

  useEffect(() => {
    if (queryPhase !== 'success' && queryPhase !== 'error') return;

    const targetId = queryPhase === 'success' ? 'answer-heading' : 'query-error-heading';
    const frame = window.requestAnimationFrame(() => document.getElementById(targetId)?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [queryPhase]);

  useEffect(() => () => {
    queryAbortRef.current?.abort();
    indexAbortRef.current?.abort();
  }, []);

  const runQuery = useCallback(async (request: QueryRequest) => {
    queryAbortRef.current?.abort();
    const controller = new AbortController();
    queryAbortRef.current = controller;
    setLastRequest(request);
    setQueryPhase('loading');
    setQueryError(null);
    setValidationError(null);
    setResponse(null);
    setAnnouncement('Consulta iniciada. Buscando evidências na base corporativa.');

    try {
      const nextResponse = await knowledgeApi.query(request, controller.signal);
      if (!controller.signal.aborted) {
        setResponse(nextResponse);
        setQueryPhase('success');
        setAnnouncement(
          nextResponse.grounded && nextResponse.citations.length > 0
            ? `Resposta pronta com ${nextResponse.citations.length} ${nextResponse.citations.length === 1 ? 'fonte' : 'fontes'}.`
            : 'Resposta pronta, mas sem evidência suficiente para confirmação.',
        );
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      const message = getErrorMessage(error);
      setQueryError(message);
      setQueryPhase('error');
      setAnnouncement(`A consulta falhou. ${message}`);
    }
  }, []);

  const submitCurrentQuestion = useCallback(() => {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setValidationError('Escreva uma pergunta antes de consultar a base.');
      questionInputRef.current?.focus();
      return;
    }

    void runQuery({ question: trimmedQuestion, domain: domain || null, top_k: topK });
  }, [domain, question, runQuery, topK]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitCurrentQuestion();
  };

  const handleQuestionChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setQuestion(event.target.value);
    if (validationError) setValidationError(null);
  };

  const handleQuestionKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submitCurrentQuestion();
    }
  };

  const chooseSuggestion = (suggestion: typeof suggestions[number]) => {
    setQuestion(suggestion.question);
    setDomain(suggestion.domain);
    setValidationError(null);
    setQueryError(null);
    setResponse(null);
    setQueryPhase('idle');
    questionInputRef.current?.focus();
  };

  const retryLastQuery = () => {
    if (lastRequest) void runQuery(lastRequest);
  };

  const reindexDocuments = async () => {
    indexAbortRef.current?.abort();
    const controller = new AbortController();
    indexAbortRef.current = controller;
    setIndexState({ phase: 'loading', message: 'Relendo os documentos configurados…' });

    try {
      const result = await knowledgeApi.ingest(controller.signal);
      if (controller.signal.aborted) return;
      setIndexState({ phase: 'success', message: formatIngestMessage(result) });
      void loadStatus();
    } catch (error) {
      if (controller.signal.aborted) return;
      setIndexState({ phase: 'error', message: getErrorMessage(error) });
    }
  };

  let answerContent: ReactNode = <EmptyAnswer />;
  let evidenceContent: ReactNode = <EvidenceGuide />;

  if (queryPhase === 'loading') {
    answerContent = <LoadingAnswer />;
    evidenceContent = <LoadingEvidence />;
  } else if (queryPhase === 'error') {
    answerContent = (
      <QueryError
        error={queryError ?? 'Não foi possível concluir a consulta.'}
        onRetry={lastRequest ? retryLastQuery : undefined}
      />
    );
  } else if (response && lastRequest) {
    answerContent = <AnswerPanel response={response} question={lastRequest.question} />;
    evidenceContent = <EvidencePanel response={response} />;
  }

  const systemSummary = getSystemSummary(systemState);
  const showSuggestions = queryPhase === 'idle' && !response;
  const queryDescriptionIds = [
    'query-help',
    validationError ? 'question-error' : '',
    domain === 'web' ? 'web-research-note' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>

      <header className="topbar">
        <div className="topbar-inner">
          <a className="brand-lockup" href="#main-content" aria-label="Axiom Tech — Base de conhecimento">
            <span className="brand-mark" aria-hidden="true">A</span>
            <span><strong>Axiom Tech</strong><small>Base de conhecimento</small></span>
          </a>

          <p className="trust-statement"><Icon name="check" size={16} /> Respostas internas com origem rastreável</p>

          <a className={`system-link system-link--${systemSummary.tone}`} href="#system-status">
            <span className="status-dot" aria-hidden="true" />
            <span>{systemSummary.label}</span>
          </a>
        </div>
      </header>

      <main id="main-content" className="main-content">
        <section className="workspace-heading" aria-labelledby="workspace-title">
          <div>
            <p>Conhecimento interno</p>
            <h1 id="workspace-title">Consulte a base corporativa.</h1>
            <p className="workspace-description">Faça uma pergunta de trabalho. A resposta só é apresentada como verificada quando houver fontes rastreáveis ao lado.</p>
          </div>
          <kbd aria-label="Atalho: barra para focar a pergunta">/</kbd>
        </section>

        <div className="workspace-grid">
          <div className="primary-column">
            <form className="query-form" onSubmit={handleSubmit} aria-busy={queryPhase === 'loading'}>
              <div className="query-label-row">
                <label htmlFor="corporate-question">Sua pergunta</label>
                <span>{question.length.toLocaleString('pt-BR')} / {MAX_QUESTION_LENGTH.toLocaleString('pt-BR')}</span>
              </div>

              <div className={`question-field ${validationError ? 'question-field--error' : ''}`}>
                <Icon name="search" size={20} />
                <textarea
                  id="corporate-question"
                  ref={questionInputRef}
                  value={question}
                  onChange={handleQuestionChange}
                  onKeyDown={handleQuestionKeyDown}
                  placeholder="Ex.: qual é o procedimento para um incidente SEV-1?"
                  rows={3}
                  maxLength={MAX_QUESTION_LENGTH}
                  aria-describedby={queryDescriptionIds}
                  aria-invalid={validationError ? true : undefined}
                  disabled={queryPhase === 'loading'}
                />
              </div>

              {validationError && <p className="field-error" id="question-error" role="alert"><Icon name="warning" size={15} />{validationError}</p>}

              <details className="query-options">
                <summary>
                  <span><Icon name="settings" size={16} /> {domain ? `Área: ${formatDomain(domain)}` : 'Ajustar área e quantidade de evidências'}</span>
                  <Icon name="chevron" size={16} />
                </summary>
                <div className="query-options-panel">
                  <div className="control-group">
                    <label htmlFor="domain">Área da busca</label>
                    <select
                      id="domain"
                      value={domain}
                      onChange={(event) => setDomain(event.target.value as Domain | '')}
                      disabled={queryPhase === 'loading'}
                    >
                      <option value="">Detectar automaticamente</option>
                      <option value="rh">Pessoas & cultura</option>
                      <option value="juridico">Jurídico & LGPD</option>
                      <option value="engenharia">Engenharia & operações</option>
                      <option value="api_spec">Repositórios & APIs</option>
                      <option value="web">Pesquisa técnica externa</option>
                    </select>
                  </div>
                  <div className="control-group control-group--compact">
                    <label htmlFor="evidence-count">Máximo de evidências</label>
                    <select
                      id="evidence-count"
                      value={topK}
                      onChange={(event) => setTopK(Number(event.target.value))}
                      disabled={queryPhase === 'loading'}
                    >
                      <option value={2}>2 trechos</option>
                      <option value={4}>4 trechos</option>
                      <option value={6}>6 trechos</option>
                    </select>
                  </div>
                </div>
              </details>

              {domain === 'web' && (
                <p className="web-research-note" id="web-research-note">
                  <Icon name="warning" size={15} /> A pesquisa externa só é executada quando configurada e usa domínios previamente permitidos.
                </p>
              )}

              <div className="query-actions">
                <p id="query-help"><span>Enter</span> envia · <span>Shift + Enter</span> cria uma linha</p>
                <button className="button button--primary" type="submit" disabled={queryPhase === 'loading'}>
                  <Icon name={queryPhase === 'loading' ? 'refresh' : 'arrow-up'} size={17} />
                  {queryPhase === 'loading' ? 'Consultando…' : 'Consultar base'}
                </button>
              </div>
            </form>

            {showSuggestions && (
              <section className="suggestions" aria-labelledby="suggestions-heading">
                <div className="suggestions-heading">
                  <h2 id="suggestions-heading">Perguntas frequentes</h2>
                  <p>Use um exemplo ou escreva a sua.</p>
                </div>
                <ul className="suggestion-list">
                  {suggestions.map((suggestion) => (
                    <li key={suggestion.question}>
                      <button type="button" onClick={() => chooseSuggestion(suggestion)}>
                        <span>{suggestion.question}</span>
                        <small>{suggestion.label}</small>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="response-region" id="response" aria-label="Resultado da consulta">
              {answerContent}
            </section>
          </div>

          <aside className="companion-column" aria-label="Evidências e estado da base">
            {evidenceContent}
            <StatusPanel
              state={systemState}
              indexState={indexState}
              onRefresh={() => void loadStatus()}
              onReindex={() => void reindexDocuments()}
            />
          </aside>
        </div>

        <p className="live-announcement sr-only" aria-live="polite" aria-atomic="true">{announcement}</p>
      </main>

      <footer className="footer">
        <p>Axiom Tech · Respostas internas devem permanecer vinculadas às fontes.</p>
        <a href="#main-content">Voltar ao início</a>
      </footer>
    </div>
  );
}
