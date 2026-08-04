import {
  useCallback,
  useEffect,
  useRef,
  useState,
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
  formatIngestMessage,
  getErrorMessage,
  Icon,
  LoadingAnswer,
  NavigationContent,
  QueryError,
  StatusRail,
  type IndexState,
  type StatusState,
} from './components';

type RequestPhase = 'idle' | 'loading' | 'success' | 'error';

const suggestions: Array<{ question: string; domain: Domain }> = [
  { question: 'Como proceder em um incidente de severidade SEV-1?', domain: 'engenharia' },
  { question: 'Qual é a política de home office e vale-refeição?', domain: 'rh' },
  { question: 'Quais são os direitos dos titulares segundo a política de LGPD?', domain: 'juridico' },
  { question: 'Como a API interna descreve autenticação e limites de uso?', domain: 'api_spec' },
];

export default function App() {
  const [question, setQuestion] = useState('');
  const [domain, setDomain] = useState<Domain | ''>('');
  const [topK, setTopK] = useState(4);
  const [queryPhase, setQueryPhase] = useState<RequestPhase>('idle');
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<QueryRequest | null>(null);
  const [systemState, setSystemState] = useState<StatusState>({ phase: 'loading' });
  const [indexState, setIndexState] = useState<IndexState>({ phase: 'idle' });
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);

  const questionInputRef = useRef<HTMLTextAreaElement>(null);
  const navigationDialogRef = useRef<HTMLDialogElement>(null);
  const queryAbortRef = useRef<AbortController | null>(null);
  const statusAbortRef = useRef<AbortController | null>(null);

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
      setSystemState((current) => ({ phase: 'error', data: current.data, error: getErrorMessage(error) }));
    }
  }, []);

  useEffect(() => {
    void loadStatus();
    return () => statusAbortRef.current?.abort();
  }, [loadStatus]);

  useEffect(() => {
    const focusSearchWithShortcut = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping = target?.matches('input, textarea, select, [contenteditable="true"]');
      if (event.key === '/' && !isTyping) {
        event.preventDefault();
        questionInputRef.current?.focus();
      }
    };

    window.addEventListener('keydown', focusSearchWithShortcut);
    return () => window.removeEventListener('keydown', focusSearchWithShortcut);
  }, []);

  useEffect(() => {
    const closeOnDesktop = () => {
      const dialog = navigationDialogRef.current;
      if (window.innerWidth >= 960 && dialog?.open) dialog.close();
    };

    window.addEventListener('resize', closeOnDesktop);
    return () => window.removeEventListener('resize', closeOnDesktop);
  }, []);

  const runQuery = useCallback(async (request: QueryRequest) => {
    queryAbortRef.current?.abort();
    const controller = new AbortController();
    queryAbortRef.current = controller;
    setLastRequest(request);
    setQueryPhase('loading');
    setQueryError(null);
    setResponse(null);

    try {
      const nextResponse = await knowledgeApi.query(request, controller.signal);
      if (!controller.signal.aborted) {
        setResponse(nextResponse);
        setQueryPhase('success');
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      setQueryError(getErrorMessage(error));
      setQueryPhase('error');
    }
  }, []);

  useEffect(() => () => queryAbortRef.current?.abort(), []);

  const submitCurrentQuestion = useCallback(() => {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      setQueryError('Escreva uma pergunta para consultar a base corporativa.');
      setQueryPhase('error');
      questionInputRef.current?.focus();
      return;
    }

    void runQuery({ question: trimmedQuestion, domain: domain || null, top_k: topK });
  }, [domain, question, runQuery, topK]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    submitCurrentQuestion();
  };

  const handleQuestionKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      submitCurrentQuestion();
    }
  };

  const chooseSuggestion = (suggestion: typeof suggestions[number]) => {
    setQuestion(suggestion.question);
    setDomain(suggestion.domain);
    setQueryError(null);
    setQueryPhase('idle');
    questionInputRef.current?.focus();
  };

  const retryLastQuery = () => {
    if (lastRequest) void runQuery(lastRequest);
  };

  const reindexDocuments = async () => {
    setIndexState({ phase: 'loading' });
    try {
      const result = await knowledgeApi.ingest();
      setIndexState({ phase: 'success', message: formatIngestMessage(result) });
      void loadStatus();
    } catch (error) {
      setIndexState({ phase: 'error', message: getErrorMessage(error) });
    }
  };

  const openMobileNavigation = () => {
    const dialog = navigationDialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
      setMobileNavigationOpen(true);
    }
  };

  const closeMobileNavigation = () => {
    const dialog = navigationDialogRef.current;
    if (dialog?.open) dialog.close();
    setMobileNavigationOpen(false);
  };

  let answerContent: ReactNode = <EmptyAnswer />;
  if (queryPhase === 'loading') {
    answerContent = <LoadingAnswer />;
  } else if (queryPhase === 'error') {
    answerContent = <QueryError error={queryError ?? 'Não foi possível concluir a consulta.'} onRetry={lastRequest ? retryLastQuery : undefined} />;
  } else if (response && lastRequest) {
    answerContent = <AnswerPanel response={response} question={lastRequest.question} />;
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Pular para o conteúdo</a>

      <aside className="desktop-sidebar">
        <NavigationContent recentQuestion={response && lastRequest ? lastRequest.question : undefined} />
      </aside>

      <dialog
        className="mobile-navigation-dialog"
        ref={navigationDialogRef}
        aria-label="Navegação do espaço de conhecimento"
        onClose={() => setMobileNavigationOpen(false)}
      >
        <aside className="mobile-sidebar">
          <button className="icon-button mobile-close" type="button" onClick={closeMobileNavigation} aria-label="Fechar navegação"><Icon name="close" size={19} /></button>
          <NavigationContent onNavigate={closeMobileNavigation} recentQuestion={response && lastRequest ? lastRequest.question : undefined} />
        </aside>
      </dialog>

      <div className="workspace">
        <header className="topbar">
          <button className="icon-button mobile-menu" type="button" onClick={openMobileNavigation} aria-label="Abrir navegação" aria-expanded={mobileNavigationOpen}><Icon name="menu" size={20} /></button>
          <div className="topbar-title"><span>Knowledge workspace</span><strong>Axiom Tech</strong></div>
          <div className="topbar-status" role="status"><span className={`status-dot ${systemState.data?.status === 'ok' ? 'status-dot--online' : 'status-dot--offline'}`} /><span>{systemState.data?.status === 'ok' ? 'Índice conectado' : 'Verificando índice'}</span></div>
        </header>

        <main id="main-content" className="main-content">
          <section className="query-introduction" id="ask" aria-labelledby="workspace-title">
            <div>
              <p className="section-label">Assistente de conhecimento interno</p>
              <h1 id="workspace-title">Encontre a resposta certa, com a fonte ao lado.</h1>
              <p>Consulte documentos corporativos e acompanhe como a resposta foi construída.</p>
            </div>
            <span className="keyboard-hint" aria-label="Atalho de teclado: barra para focar a pergunta">/ para buscar</span>
          </section>

          <div className="workspace-grid">
            <div className="query-column">
              <form className="query-form" onSubmit={handleSubmit}>
                <label className="sr-only" htmlFor="corporate-question">Sua pergunta</label>
                <div className="question-field">
                  <Icon name="search" size={20} />
                  <textarea
                    id="corporate-question"
                    ref={questionInputRef}
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={handleQuestionKeyDown}
                    placeholder="Pergunte sobre uma política, um procedimento ou uma especificação…"
                    rows={2}
                    aria-describedby="query-help"
                    disabled={queryPhase === 'loading'}
                  />
                </div>
                <div className="query-controls">
                  <div className="control-group">
                    <label htmlFor="domain">Contexto</label>
                    <select id="domain" value={domain} onChange={(event) => setDomain(event.target.value as Domain | '')} disabled={queryPhase === 'loading'}>
                      <option value="">Detectar automaticamente</option>
                      <option value="rh">Pessoas & cultura</option>
                      <option value="juridico">Jurídico & LGPD</option>
                      <option value="engenharia">Engenharia</option>
                      <option value="api_spec">Especificações de API</option>
                      <option value="web">Pesquisa técnica externa</option>
                    </select>
                  </div>
                  <div className="control-group control-group--compact">
                    <label htmlFor="evidence-count">Fontes</label>
                    <select id="evidence-count" value={topK} onChange={(event) => setTopK(Number(event.target.value))} disabled={queryPhase === 'loading'}>
                      <option value={2}>2</option><option value={4}>4</option><option value={6}>6</option>
                    </select>
                  </div>
                  <button className="button button--primary" type="submit" disabled={queryPhase === 'loading'}>
                    {queryPhase === 'loading' ? <Icon name="refresh" size={17} /> : <Icon name="arrow-up" size={17} />}
                    {queryPhase === 'loading' ? 'Consultando…' : 'Consultar'}
                  </button>
                </div>
                <p id="query-help" className="query-help">Use Ctrl + Enter para enviar. As respostas priorizam fontes internas verificáveis.</p>
              </form>

              <section className="suggestions" aria-labelledby="suggestions-heading">
                <div className="suggestions-heading"><p className="section-label" id="suggestions-heading">Perguntas para começar</p><span>Escolha uma e ajuste se precisar</span></div>
                <div className="suggestion-list">
                  {suggestions.map((suggestion) => (
                    <button className="suggestion" type="button" key={suggestion.question} onClick={() => chooseSuggestion(suggestion)}><Icon name="spark" size={16} /><span>{suggestion.question}</span></button>
                  ))}
                </div>
              </section>

              <div className="response-region" id="response" aria-live="polite">{answerContent}</div>
            </div>

            <div id="system"><StatusRail state={systemState} indexState={indexState} onRefresh={() => void loadStatus()} onReindex={() => void reindexDocuments()} /></div>
          </div>
        </main>
      </div>
    </div>
  );
}
