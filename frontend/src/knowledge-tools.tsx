import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from 'react';
import {
  isAbortError,
  knowledgeApi,
  type DocumentUploadResponse,
  type Domain,
} from './api';
import {
  formatDomain,
  getErrorMessage,
  Icon,
} from './components';

const MAX_UPLOAD_BYTES = 15 * 1024 * 1024; // 15 MB
const ACCEPTED_EXTENSIONS = '.md,.txt,.json,.csv,.xlsx,.pdf,.docx,.html,.htm,.pptx';
const ACCEPTED_EXTENSIONS_LIST = [
  '.md',
  '.txt',
  '.json',
  '.csv',
  '.xlsx',
  '.pdf',
  '.docx',
  '.html',
  '.htm',
  '.pptx',
];

const internalDomains: Array<{ value: Domain; label: string }> = [
  { value: 'rh', label: 'Pessoas & cultura' },
  { value: 'juridico', label: 'Jurídico & LGPD' },
  { value: 'engenharia', label: 'Engenharia & operações' },
  { value: 'api_spec', label: 'Repositórios & APIs' },
  { value: 'estrategico', label: 'Estratégia & governança' },
  { value: 'comunicacao', label: 'Comunicação & institucional' },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`;
}

function isValidExtension(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS_LIST.some((ext) => lower.endsWith(ext));
}

export interface DocumentUploadPanelProps {
  onSuccess?: (response: DocumentUploadResponse) => void;
  disabled?: boolean;
}

export function DocumentUploadPanel({ onSuccess, disabled = false }: DocumentUploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [domain, setDomain] = useState<Domain | ''>('');
  const [uploadPhase, setUploadPhase] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => uploadAbortRef.current?.abort(), []);

  const handleFileSelection = (selectedFile: File | null) => {
    if (!selectedFile) {
      setFile(null);
      return;
    }

    if (!isValidExtension(selectedFile.name)) {
      setFile(null);
      setUploadPhase('error');
      setFeedbackMessage(
        `Formato não suportado. Formatos aceitos: ${ACCEPTED_EXTENSIONS_LIST.join(', ')}.`,
      );
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    if (selectedFile.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setUploadPhase('error');
      setFeedbackMessage(
        `O arquivo excede o limite máximo permitido de 15 MB (${formatBytes(selectedFile.size)}).`,
      );
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setFile(selectedFile);
    if (uploadPhase === 'error') {
      setUploadPhase('idle');
      setFeedbackMessage(null);
    }
  };

  const handleFileInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] ?? null;
    handleFileSelection(selected);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(false);
    if (disabled || uploadPhase === 'loading') return;

    const dropped = event.dataTransfer.files?.[0] ?? null;
    if (dropped) {
      handleFileSelection(dropped);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (!disabled && uploadPhase !== 'loading') {
      setIsDragOver(true);
    }
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(false);
  };

  const handleClearFile = () => {
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!file) {
      setUploadPhase('error');
      setFeedbackMessage('Selecione um arquivo para enviar à base.');
      fileInputRef.current?.focus();
      return;
    }

    if (!domain) {
      setUploadPhase('error');
      setFeedbackMessage('Selecione a área corporativa de destino.');
      return;
    }

    uploadAbortRef.current?.abort();
    const controller = new AbortController();
    uploadAbortRef.current = controller;

    setUploadPhase('loading');
    setFeedbackMessage('Enviando e indexando documento no corpus interno…');

    try {
      const response = await knowledgeApi.uploadDocument(file, domain, controller.signal);
      if (controller.signal.aborted) return;

      setUploadPhase('success');
      setFeedbackMessage(
        `Documento "${response.filename}" adicionado com sucesso na área ${formatDomain(
          response.domain,
        )}. Total de ${response.chunks} ${response.chunks === 1 ? 'trecho indexado' : 'trechos indexados'}.`,
      );
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      onSuccess?.(response);
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) return;
      setUploadPhase('error');
      setFeedbackMessage(getErrorMessage(error));
    }
  };

  const isBusy = uploadPhase === 'loading' || disabled;

  return (
    <section
      className="upload-panel"
      aria-labelledby="upload-panel-heading"
      aria-busy={uploadPhase === 'loading'}
    >
      <header className="panel-heading">
        <div>
          <p>Adicionar conteúdo</p>
          <h2 id="upload-panel-heading">Upload de documento</h2>
        </div>
        <span className="upload-limit-badge" title="Limite máximo por arquivo">Até 15 MB</span>
      </header>

      <form className="upload-form" onSubmit={handleSubmit} noValidate>
        <p className="upload-instruction">
          Adicione um arquivo corporativo à base. Os trechos são processados e indexados imediatamente na área selecionada.
        </p>

        <div className="control-group">
          <label htmlFor="upload-domain">
            Área de destino <span aria-hidden="true">*</span>
          </label>
          <select
            id="upload-domain"
            value={domain}
            onChange={(e) => setDomain(e.target.value as Domain | '')}
            disabled={isBusy}
            required
            aria-required="true"
          >
            <option value="">Selecione a área corporativa…</option>
            {internalDomains.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label htmlFor="upload-file-input">
            Arquivo <span aria-hidden="true">*</span>
          </label>
          <div
            className={`upload-dropzone ${isDragOver ? 'upload-dropzone--drag-over' : ''} ${
              file ? 'upload-dropzone--has-file' : ''
            }`}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
          >
            <input
              id="upload-file-input"
              ref={fileInputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS}
              multiple={false}
              onChange={handleFileInputChange}
              disabled={isBusy}
              className="upload-file-input"
              aria-describedby="upload-file-hint"
            />

            {!file ? (
              <div className="upload-dropzone-content">
                <Icon name="upload" size={22} />
                <div className="upload-dropzone-text">
                  <span>
                    <strong>Escolher arquivo</strong> ou arraste aqui
                  </span>
                  <small id="upload-file-hint">
                    Formatos: .md, .txt, .json, .csv, .xlsx, .pdf, .docx, .html, .pptx
                  </small>
                </div>
              </div>
            ) : (
              <div className="upload-file-selected">
                <Icon name="file" size={20} />
                <div className="upload-file-details">
                  <strong title={file.name}>{file.name}</strong>
                  <span>{formatBytes(file.size)}</span>
                </div>
                <button
                  type="button"
                  className="upload-remove-button"
                  onClick={handleClearFile}
                  disabled={isBusy}
                  aria-label={`Remover arquivo selecionado: ${file.name}`}
                >
                  <Icon name="warning" size={14} />
                  <span>Trocar</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {uploadPhase === 'loading' && (
          <div className="upload-feedback upload-feedback--loading" role="status" aria-live="polite">
            <Icon name="refresh" size={16} />
            <span>{feedbackMessage || 'Processando documento…'}</span>
          </div>
        )}

        {uploadPhase === 'success' && feedbackMessage && (
          <div className="upload-feedback upload-feedback--success" role="status" aria-live="polite">
            <Icon name="check" size={16} />
            <span>{feedbackMessage}</span>
          </div>
        )}

        {uploadPhase === 'error' && feedbackMessage && (
          <div className="upload-feedback upload-feedback--error" role="alert" aria-live="assertive">
            <Icon name="warning" size={16} />
            <span>{feedbackMessage}</span>
          </div>
        )}

        <button
          type="submit"
          className="button button--primary button--full upload-submit-button"
          disabled={isBusy || !file || !domain}
        >
          <Icon name={uploadPhase === 'loading' ? 'refresh' : 'upload'} size={16} />
          <span>{uploadPhase === 'loading' ? 'Indexando documento…' : 'Enviar e indexar'}</span>
        </button>
      </form>
    </section>
  );
}

export function FaqSection() {
  return (
    <section className="faq-section" aria-labelledby="faq-section-heading">
      <header className="faq-header">
        <h2 id="faq-section-heading">Perguntas frequentes e diretrizes de uso</h2>
        <p className="faq-subtitle">
          Entenda como a base corporativa processa perguntas, valida evidências e protege dados internos.
        </p>
      </header>

      <div className="faq-accordion">
        <details className="faq-item">
          <summary className="faq-summary">
            <span>
              <Icon name="book" size={18} />
              Por que a aplicação existe e qual problema ela resolve?
            </span>
            <Icon name="chevron" size={16} />
          </summary>
          <div className="faq-content">
            <p>
              O <strong>Axiom Tech</strong> foi desenvolvido para solucionar a fragmentação e a insegurança na busca de informações operacionais internas:
            </p>
            <ul>
              <li>
                <strong>Busca unificada:</strong> Consolida políticas de RH, orientações de engenharia, procedimentos de incidentes, normas jurídicas/LGPD, APIs e comunicação institucional em um único ponto de consulta.
              </li>
              <li>
                <strong>Respostas com suporte verificável:</strong> A resposta só é apresentada como fundamentada quando a recuperação encontra evidência interna suficiente; sem esse suporte, o sistema recusa a confirmação.
              </li>
              <li>
                <strong>Foco no trabalho real:</strong> Entrega respostas objetivas e imediatamente acionáveis para colaboradores, engenheiros e lideranças.
              </li>
            </ul>
          </div>
        </details>

        <details className="faq-item">
          <summary className="faq-summary">
            <span>
              <Icon name="search" size={18} />
              O que é grounding e como funcionam as fontes e citações?
            </span>
            <Icon name="chevron" size={16} />
          </summary>
          <div className="faq-content">
            <p>
              <strong>Grounding</strong> (ancoragem) é o compromisso de que nenhuma resposta corporativa seja formulada sem vínculo verificável com o corpus:
            </p>
            <ul>
              <li>
                <strong>Rastreabilidade de ponta a ponta:</strong> Cada resposta exibe no painel de evidências os arquivos consultados, a área de conhecimento correspondente e um indicador de relevância do trecho recuperado.
              </li>
              <li>
                <strong>Localizador explícito:</strong> Quando o documento possui paginação, slides ou planilhas (PDF, DOCX, PPTX, XLSX), o assistente informa a página, slide, planilha ou índice do trecho exato para conferência rápida.
              </li>
              <li>
                <strong>Auditoria:</strong> É possível copiar a referência formatada e pré-visualizar o conteúdo extraído pelo inventário de fontes.
              </li>
            </ul>
          </div>
        </details>

        <details className="faq-item">
          <summary className="faq-summary">
            <span>
              <Icon name="warning" size={18} />
              O que significa o comportamento fail-closed (honestidade na incerteza)?
            </span>
            <Icon name="chevron" size={16} />
          </summary>
          <div className="faq-content">
            <p>
              Seguindo o princípio <em>"Evidência antes de eloquência"</em>, o sistema adota a postura de <strong>falha fechada e segura (fail-closed)</strong>:
            </p>
            <ul>
              <li>
                <strong>Sem inventar normas:</strong> Se os documentos indexados não contiverem evidências sólidas sobre a dúvida pesquisada, o assistente declara expressamente a insuficiência de dados.
              </li>
              <li>
                <strong>Aviso de integridade:</strong> Uma sinalização em destaque alerta para não utilizar a resposta como confirmação oficial em processos críticos.
              </li>
              <li>
                <strong>Orientação humana:</strong> O usuário é direcionado a refinar a pergunta ou procurar diretamente o responsável da respectiva área (RH, Jurídico, SRE, etc.).
              </li>
            </ul>
          </div>
        </details>

        <details className="faq-item">
          <summary className="faq-summary">
            <span>
              <Icon name="database" size={18} />
              Como funciona a privacidade e a diferença entre execução local e modelos remotos?
            </span>
            <Icon name="chevron" size={16} />
          </summary>
          <div className="faq-content">
            <p>
              O sistema foi arquitetado com controle estrito de soberania de dados:
            </p>
            <ul>
              <li>
                <strong>Padrão local e determinístico:</strong> Em sua configuração padrão, todo o armazenamento vetorial (ChromaDB local), embeddings determinísticos e rotas de síntese operam offline, garantindo que nenhum documento corporativo saia da infraestrutura interna.
              </li>
              <li>
                <strong>Modelos remotos opcionais:</strong> Gateways externos (como NVIDIA NIM ou LLMs em nuvem) são ativados estritamente por configuração explícita de administradores, utilizando canais autenticados e rotas com circuito de proteção e fallback local.
              </li>
              <li>
                <strong>Pesquisa externa controlada:</strong> A pesquisa na web não ocorre automaticamente; exige seleção intencional da rota e opera exclusivamente sobre uma lista restrita de domínios permitidos (*allowlist*).
              </li>
            </ul>
          </div>
        </details>

        <details className="faq-item">
          <summary className="faq-summary">
            <span>
              <Icon name="settings" size={18} />
              Qual a diferença entre os 4 modos de resposta disponíveis?
            </span>
            <Icon name="chevron" size={16} />
          </summary>
          <div className="faq-content">
            <p>
              Você pode ajustar a estrutura da resposta nas opções avançadas de acordo com a sua necessidade:
            </p>
            <ul>
              <li>
                <strong>Direta (<code>concise</code>):</strong> Síntese objetiva em até dois parágrafos curtos, indicada para consultas rápidas do dia a dia.
              </li>
              <li>
                <strong>Detalhada (<code>detailed</code>):</strong> Explicação completa e aprofundada com contexto, regras aplicáveis, exceções e passos práticos suportados.
              </li>
              <li>
                <strong>Checklist (<code>checklist</code>):</strong> Formatação estruturada em tópicos e itens de verificação com ações sequenciais recomendadas.
              </li>
              <li>
                <strong>Evidências (<code>evidence</code>):</strong> Foco prioritário em citações literais e trechos diretos das fontes oficiais com identificação minuciosa de cada localizador.
              </li>
            </ul>
          </div>
        </details>
      </div>
    </section>
  );
}
