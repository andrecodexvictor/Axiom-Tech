# Axiom Tech — Assistente corporativo com IA

O Axiom Tech é um agente inteligente que responde perguntas sobre documentos corporativos, apresenta as fontes utilizadas e informa quando a base interna não possui evidência suficiente. A aplicação atende políticas de RH, jurídico/LGPD, engenharia, especificações de API e pesquisa técnica externa controlada.

O agente lê e processa documentos PDF, CSV, Excel, Word, PowerPoint, Markdown, JSON e HTML. A ingestão preserva domínio, tipo de arquivo, caminho relativo e metadados de página, slide ou planilha para que as respostas apresentem citações verificáveis.

## Entrega do desafio

| Requisito | Evidência no projeto | Estado |
| --- | --- | --- |
| Repositório público no GitHub | [andrecodexvictor/Axiom-Tech](https://github.com/andrecodexvictor/Axiom-Tech) | Concluído |
| Descrição, arquitetura e tecnologias | Este README e [docs/architecture.md](docs/architecture.md) | Concluído |
| Agente funcional baseado em documentos | LangGraph, ingestão multiformato, ChromaDB e interface React | Concluído |
| Código para ler e processar documentos | [app/ingestion/loader.py](app/ingestion/loader.py) | Concluído |
| Deploy em serviço OCI | OCI Compute, API Gateway, Docker Compose, OCI Vault e Block Volume | Gateway criado; regra TCP/443 pendente |
| Link público sem depender do IP | Hostname HTTPS gerado pelo Oracle API Gateway | Em validação de rede |
| Captura da aplicação online | docs/evidence e link desta seção | Pendente captura final |
| Deploy automático por commit | [workflow de deploy OCI](.github/workflows/deploy-oci.yml) | Preparado para teste |

Endpoint Oracle criado para a demonstração: https://hbdmwrkfrff2rrhsh4myxy2cyu.apigateway.sa-saopaulo-1.oci.customer-oci.com. A variável PUBLIC_URL do ambiente production do GitHub deve usar esse endereço ou um domínio customizado configurado sobre o API Gateway.

## Visão geral da arquitetura

```text
Navegador
   |
   v
Oracle API Gateway: HTTPS e hostname público
   |
   v
Nginx frontend: React/Vite
   |
   v
FastAPI /api/v1
   |
   v
LangGraph StateGraph
   |----------------------|
   v                      v
Ingestão e recuperação   Gateway de modelo
   |                      |
   v                      v
ChromaDB + Block Volume  NVIDIA NIM opcional
   |
   v
documentos/

LangGraph e chamadas de modelo -> LangSmith opcional, com inputs/outputs ocultos
Segredos de runtime -> OCI Vault
```

O fluxo corporativo é baseado em evidências: o agente recupera trechos, avalia a cobertura, pode reescrever a busca até duas vezes e sintetiza somente quando existem fontes suficientes. Quando a base não sustenta a resposta, o sistema retorna uma limitação explícita em vez de inventar uma citação.

## Tecnologias e ferramentas

- Python 3.11+
- FastAPI e Uvicorn
- LangGraph e LangChain
- LangSmith para observabilidade opcional
- ChromaDB como vector store padrão
- Gateway explícito para modo local, NVIDIA NIM ou OpenAI
- React, TypeScript, Vite e pnpm
- Docker e Docker Compose
- OCI Compute, VCN, Security Lists/NSGs, Vault e Block Volume
- GitHub Actions para CI e deploy automático
- Oracle API Gateway para HTTPS e hostname público

Pinecone e pesquisa web são adaptadores opcionais. O sistema não declara esses recursos como ativos quando não estão configurados.

## Estrutura do projeto

```text
app/                         API FastAPI, agentes, grafo e adaptadores
app/ingestion/               Leitura e normalização de documentos
frontend/                    Console web React/Vite
documentos/                  Corpus corporativo de exemplo
tests/                       Testes backend
docker/                      Configuração do Nginx frontend
deploy/Caddyfile             Alternativa de reverse proxy para domínio próprio
docs/                        Arquitetura, API, deploy, ADRs e evidências
.github/workflows/           CI e deploy automático
docker-compose.yml           Topologia local
docker-compose.oci.yml       Persistência em Block Volume na OCI
docker-compose.gateway.yml   Topologia da VM atrás do Oracle API Gateway
docker-compose.public.yml    Alternativa Caddy, portas 80/443 e HTTPS
```

## Execução local

### 1. Configurar o ambiente

PowerShell:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Os padrões locais funcionam sem chaves de nuvem. O modo determinístico permite validar ingestão, recuperação, citações e fallback antes de habilitar um provedor de modelo.

### 2. Iniciar a API

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Endpoints principais:

```text
GET  /api/v1/health
GET  /api/v1/status
POST /api/v1/query
POST /api/v1/ingest
GET  /api/v1/sources
POST /api/v1/embeddings/rebuild
```

### 3. Iniciar o frontend

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

Se o pnpm não estiver instalado:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

### 4. Executar imagens publicadas pelo GitHub Actions

```bash
export RELEASE_SHA=<commit-de-40-caracteres>
export AXIOM_API_IMAGE=ghcr.io/andrecodexvictor/axiom-tech-api:sha-$RELEASE_SHA
export AXIOM_FRONTEND_IMAGE=ghcr.io/andrecodexvictor/axiom-tech-frontend:sha-$RELEASE_SHA
docker compose pull
docker compose up -d --no-build
```

O frontend ficará em http://localhost:8080 e a API em http://localhost:8000.
O repositório não faz build de imagem na máquina local ou na VM; para
desenvolvimento sem imagens, use os processos Python e Vite das etapas acima.

## Ingestão e uso do agente

A ingestão é explícita e idempotente. Pela API:

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d "{}"
```

Veja quais arquivos estão integrados e se algum precisa de atualização:

```bash
curl http://localhost:8000/api/v1/sources
```

Para recalcular todos os vetores com o provider/modelo de embeddings ativo:

```bash
curl -X POST http://localhost:8000/api/v1/embeddings/rebuild
```

Uma consulta fundamentada:

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Como devo responder a um incidente SEV-1?","domain":"engenharia","top_k":4}'
```

O código responsável pela leitura multiformato está em app/ingestion/loader.py. Exemplo direto de leitura de um CSV:

```python
from pathlib import Path

from app.ingestion.loader import DocumentLoader

documents = DocumentLoader.load_file(
    Path("documentos/rh/benefits_homeoffice_policy.csv")
)

print(documents[0]["content"])
print(documents[0]["metadata"])
```

O mesmo loader possui caminhos específicos para PDF, DOCX, XLSX, PPTX, JSON, HTML, Markdown e texto. PDF e PowerPoint preservam o número da página ou do slide quando disponível; planilhas preservam o nome da aba.

Para ampliar o conhecimento interno, coloque arquivos aprovados em uma pasta de domínio dentro de `documentos/` (por exemplo, `documentos/financeiro/relatorio.md`) e execute a ingestão. O painel **Documentos disponíveis** mostra o arquivo, tipo, tamanho, estado e quantidade de trechos; a ação **Gerar embeddings novamente** recalcula todos os vetores com o provider atualmente configurado. O inventário não exibe o conteúdo do documento no navegador.

Pesquisa externa é uma fonte separada e opt-in: configure `AXIOM_WEB_ENABLED=true`, uma `SERPER_API_KEY` e uma allowlist HTTPS em `AXIOM_WEB_ALLOWLIST`. Sem os três itens, perguntas com domínio `web` permanecem desativadas e não fazem chamadas externas.

## Exemplos de perguntas e respostas

### Política de home office

Pergunta:

```text
Qual é o subsídio mensal de home office?
```

Resposta fundamentada esperada:

```text
O subsídio de home office é de R$ 350,00 por mês para colaboradores remotos e híbridos. A fonte é a política de benefícios de RH.
```

Citação esperada:

```text
documentos/rh/benefits_homeoffice_policy.csv
```

### Incidente SEV-1

Pergunta:

```text
Como devo responder a um incidente de severidade SEV-1?
```

Resposta fundamentada esperada:

```text
O incidente deve ser tratado como uma indisponibilidade crítica: designar imediatamente um Incident Commander, abrir uma war room, publicar atualizações a cada 30 minutos e observar o SLA de resposta de 15 minutos e resolução de 4 horas.
```

Citação esperada:

```text
documentos/engenharia/incident_resilience_manual.md
```

### Especificação de API

Pergunta:

```text
Qual endpoint registra um incidente operacional?
```

Resposta fundamentada esperada:

```text
O endpoint é POST /incidents. Ele exige autenticação e aceita título, severidade SEV-1/SEV-2/SEV-3, serviço e descrição.
```

Citação esperada:

```text
documentos/api_spec/internal_endpoints.json
```

As respostas reais podem variar na redação, mas devem manter as evidências apresentadas pela API. Uma pergunta sem suporte suficiente deve retornar grounded=false e não deve fabricar uma fonte.

## Observabilidade, embeddings e chaves de IA

O modo local não exige segredos. Uma rota remota é sempre explícita; por
exemplo, NVIDIA com fallback local apenas para falhas transitórias:

```dotenv
AXIOM_LLM_PROVIDER=nvidia
AXIOM_LLM_FALLBACK=deterministic
NVIDIA_API_KEY=<provider-key>
NVIDIA_MODEL=meta/muse-glimmer-30b
```

OpenAI usa `AXIOM_LLM_PROVIDER=openai`, `OPENAI_API_KEY` e `OPENAI_MODEL`.
Uma ordem avançada pode ser declarada em `AXIOM_LLM_ROUTES`; a presença de uma
chave nunca seleciona o provedor implicitamente. Endpoints OpenAI customizados
exigem HTTPS e `AXIOM_OPENAI_ALLOW_CUSTOM_BASE_URL=true`.

Embeddings semânticos também são opt-in e usam um espaço vetorial separado do
gateway de síntese:

```dotenv
AXIOM_EMBEDDING_PROVIDER=openai
AXIOM_EMBEDDING_API_KEY=<embedding-key>
AXIOM_EMBEDDING_MODEL=nvidia/nemotron-3-embed-1b
AXIOM_EMBEDDING_DIMENSIONS=2048
AXIOM_EMBEDDING_BASE_URL=https://integrate.api.nvidia.com/v1
AXIOM_EMBEDDING_INPUT_TYPE=auto
```

O cliente também entende automaticamente o modo
`passage` na indexação e `query` na busca para a variante
`nvidia/llama-nemotron-embed-1b-v2`.

Trocar provider, modelo, dimensão ou endpoint de embeddings seleciona uma nova
coleção física versionada; execute a ingestão explícita depois da mudança. Uma
falha remota de embedding nunca cai silenciosamente para o hashing local.

LangSmith é habilitado separadamente:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<service-key>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=axiom-tech-v3
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

As chaves devem ficar no OCI Vault ou em outro secret manager. Nunca coloque credenciais em Git, Dockerfile, imagem, logs, screenshots, perguntas ou argumentos MCP. Consulte [docs/observability.md](docs/observability.md).

## Deploy na OCI

O primeiro deploy usa OCI Compute com Docker Compose:

```text
OCI Compute VM
  -> VCN/subnet
  -> Security List ou NSG
  -> frontend 8080 privado
  -> API 8000 somente na rede Docker
  -> ChromaDB em OCI Block Volume
  -> runtime .env materializado pelo OCI Vault

Oracle API Gateway público
  -> HTTP backend para <VM_PRIVATE_IP>:8080
```

O procedimento manual completo está em [docs/oci-mcp-deployment.md](docs/oci-mcp-deployment.md), e o tutorial de autenticação está em [docs/oci-mcp-authentication-guide.md](docs/oci-mcp-authentication-guide.md).

### URL pública Oracle sem depender do IP da aplicação

O API Gateway fornece um hostname HTTPS Oracle sem exigir que o usuário registre um domínio:

1. Crie um API Gateway `PUBLIC` em uma subnet regional pública.
2. Crie um deployment com rota wildcard e backend HTTP apontando para o IP privado da VM na porta 8080.
3. Libere TCP 443 de forma stateful na Security List ou NSG da subnet do Gateway.
4. Configure `PUBLIC_URL` com o hostname `*.apigateway.<region>.oci.customer-oci.com`.
5. Configure `PUBLIC_URL` no ambiente `production` do GitHub. O workflow aplica a
   composição específica da VM com imagens imutáveis; não há build na VM.

O Gateway é o ponto público; a VM não precisa expor as portas 80/443. Depois de validar o Gateway, a regra pública TCP/8080 da VM deve ser removida ou restringida ao CIDR do Gateway.

O endpoint Oracle já foi criado, mas a validação externa depende da regra TCP/443 na Security List. O Caddy continua disponível como alternativa quando o projeto possuir um domínio próprio.

## Deploy automático por commit

Os workflows constroem e publicam imagens multi-arquitetura (`linux/amd64` e
`linux/arm64`) no GHCR. O arquivo
[.github/workflows/deploy-oci.yml](.github/workflows/deploy-oci.yml) publica a
branch `main` por SSH somente depois que o workflow **Axiom CI** termina com
sucesso. O deploy:

1. conecta à VM;
2. busca exatamente o commit aprovado;
3. preserva o .env ignorado do servidor;
4. autentica temporariamente a VM no GHCR com o token do próprio workflow;
5. valida o Compose e baixa as imagens `sha-<commit>`;
6. reinicia API e frontend com `--no-build`;
7. executa a reindexação apenas quando solicitada manualmente;
8. verifica o health check local e o link público.

Configure no GitHub um ambiente chamado production.

Secrets do ambiente:

```text
OCI_SSH_PRIVATE_KEY
OCI_KNOWN_HOSTS
```

Variables do ambiente:

```text
OCI_DEPLOY_HOST
OCI_DEPLOY_USER=ubuntu
OCI_DEPLOY_PATH=/opt/axiom
PUBLIC_URL=https://hbdmwrkfrff2rrhsh4myxy2cyu.apigateway.sa-saopaulo-1.oci.customer-oci.com
```

OCI_KNOWN_HOSTS deve conter a chave do host SSH da VM verificada no OCI Console, obtida pelo operador com:

```bash
ssh-keyscan -H "$OCI_DEPLOY_HOST"
```

Verifique a fingerprint antes de salvar o valor. A chave privada SSH deve ser adicionada somente como GitHub Environment Secret; nunca como arquivo no repositório.

O workflow pode ser executado manualmente com workflow_dispatch, mas o caminho normal é:

```text
git commit
git push origin main
        |
        v
Axiom CI (testes + imagens GHCR)
        |
        v
Deploy OCI
        |
        v
PUBLIC_URL
```

## Evidência do deploy

Antes de enviar o desafio, crie uma captura sem informações sensíveis contendo:

- o endereço HTTPS público;
- a interface do Axiom Tech carregada;
- uma pergunta conhecida;
- a resposta;
- pelo menos uma citação visível;
- o status online da aplicação.

Salve a captura sanitizada em docs/evidence/axiom-live.png ou um vídeo curto em docs/evidence/axiom-live.mp4 e adicione o link nesta seção. Não mostre chaves, terminal SSH, IP privado, conteúdo confidencial do corpus ou payload bruto do LangSmith.

## Validação

Backend:

```bash
python -m pytest -q
python -m compileall -q app
```

Frontend:

```bash
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend check
pnpm --dir frontend build
```

Compose:

```bash
docker compose config --quiet
```

Consulte também [docs/challenge-checklist.md](docs/challenge-checklist.md) para o registro final de evidências.
