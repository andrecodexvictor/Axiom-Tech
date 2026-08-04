# Guia de autenticação e primeiro deploy na OCI

Este guia registra o procedimento para publicar o Axiom Tech V3 na VM Ubuntu da Oracle Cloud, autenticar o Oracle OCI Cloud MCP Server, configurar as chaves de IA e habilitar a observabilidade do LangSmith.

## Estado atual

A aplicação já foi construída e iniciada na VM:

```text
Public IP: 137.131.132.101
SSH user: ubuntu
SSH key: C:\Users\adm\Desktop\ANDRÉ\ssh-key-2026-08-04 (1).key
Frontend: TCP 8080
API: TCP 8000, internal only
Vector store: ChromaDB
```

O deploy interno foi validado com health check, ingestão dos documentos e uma consulta fundamentada com citações. Ainda faltam:

1. liberar a porta `8080` na VCN/NSG ou Security List;
2. criar o perfil de API da OCI no computador que executa o Codex;
3. recarregar o Codex para disponibilizar as ferramentas MCP;
4. armazenar as chaves de IA e LangSmith no OCI Vault;
5. habilitar a identidade da VM para ler o segredo;
6. anexar um Block Volume para persistência de produção.

## Segurança antes de continuar

A chave do LangSmith compartilhada anteriormente deve ser revogada e substituída por uma nova chave de serviço. Qualquer chave enviada em uma conversa deve ser considerada exposta.

Não envie pelo chat:

- chaves privadas SSH;
- chaves API da OCI;
- chaves NVIDIA ou de outro provedor de IA;
- chaves LangSmith;
- conteúdo do arquivo `.env`;
- valores de secrets do OCI Vault.

A chave SSH da VM serve somente para SSH. Ela não deve ser usada como chave de autenticação do Oracle MCP.

## 1. Liberar o frontend na OCI

No OCI Console:

1. Abra `Compute -> Instances -> codex-net2`.
2. Entre na `Primary VNIC`.
3. Abra o NSG associado. Se não houver NSG, abra a Security List da subnet.
4. Adicione uma regra de entrada:

```text
Source CIDR: 0.0.0.0/0
Protocol: TCP
Destination port: 8080
Description: Axiom frontend
```

Para uma regra mais segura, substitua `0.0.0.0/0` pelo IP público do operador com `/32`.

Não libere a porta `8000` publicamente. Mantenha a porta `22` restrita ao IP do operador.

Teste no Windows:

```powershell
curl.exe --fail http://137.131.132.101:8080/api/v1/health
```

Resultado esperado:

```json
{"status":"ok","version":"3.0.0"}
```

Se o firewall UFW estiver ativo na VM:

```bash
sudo ufw allow 8080/tcp
sudo ufw status
```

As Security Lists e os Network Security Groups da OCI funcionam como firewalls virtuais. Consulte a [documentação oficial de regras de segurança](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

## 2. Criar a autenticação da OCI para o MCP

Essa chave é diferente da chave SSH.

No OCI Console:

1. Clique no perfil do usuário.
2. Abra `User settings`.
3. Acesse `API keys`.
4. Clique em `Add API key`.
5. Gere um novo par de chaves.
6. Salve a chave privada localmente como:

```text
C:\Users\adm\.oci\oci_api_key.pem
```

A OCI oferece um trecho pronto em `View configuration file`. A chave privada não é armazenada pela OCI. Consulte a [documentação oficial da API signing key](https://docs.oracle.com/en-us/iaas/Content/Identity/access/to_get_the_config_file_snippet_for_an_API_signing_key.htm).

No PowerShell:

```powershell
$ociDir = Join-Path $env:USERPROFILE ".oci"

New-Item -ItemType Directory -Force $ociDir | Out-Null

notepad (Join-Path $ociDir "config")
```

Use este formato com os valores reais:

```ini
[axiom-deploy]
user=ocid1.user.oc1..<user-ocid>
fingerprint=<fingerprint>
key_file=C:\Users\adm\.oci\oci_api_key.pem
tenancy=ocid1.tenancy.oc1..<tenancy-ocid>
region=<oci-region>
```

Não envie esse arquivo ou a chave privada pelo chat.

## 3. Registrar e recarregar o Oracle MCP no Codex

O servidor já foi registrado localmente. Confirme:

```powershell
codex mcp list
```

Se ele não aparecer, registre novamente:

```powershell
codex mcp add oracle-oci-cloud-mcp-server --env OCI_CONFIG_PROFILE=axiom-deploy --env OCI_MCP_AUTH_TYPE=api_key --env FASTMCP_LOG_LEVEL=ERROR -- uvx oracle.oci-cloud-mcp-server@latest
```

A configuração utilizada pelo MCP é:

```text
OCI_CONFIG_PROFILE=axiom-deploy
OCI_MCP_AUTH_TYPE=api_key
```

Depois:

1. Feche completamente o Codex.
2. Abra-o novamente.
3. Crie uma nova sessão ou execute `/mcp` no CLI.
4. Verifique se aparecem ferramentas como:

```text
list_oci_clients
find_oci_api
describe_oci_operation
invoke_oci_api
```

Instalar o pacote com `uvx` apenas inicia o servidor quando o cliente MCP o chama. O perfil da OCI precisa existir no computador que executa o Codex. Consulte o [README oficial do Oracle Cloud MCP Server](https://github.com/oracle/mcp/blob/main/src/oci-cloud-mcp-server/README.md) e o [manual oficial de MCP do Codex](https://learn.chatgpt.com/docs/extend/mcp.md).

## 4. Permissões IAM

Se o MCP autenticar, mas retornar `NotAuthorizedOrNotFound`, o usuário da API precisa de permissões no compartimento.

Um conjunto inicial para um grupo dedicado é:

```text
Allow group axiom-deployers to inspect instances in compartment axiom-tech
Allow group axiom-deployers to manage virtual-network-family in compartment axiom-tech
Allow group axiom-deployers to manage volume-family in compartment axiom-tech
Allow group axiom-deployers to read secret-bundles in compartment axiom-secrets
```

Se o usuário já for administrador da tenancy, essa etapa provavelmente não será necessária. Prefira permissões limitadas ao compartimento em vez de permissões amplas na tenancy.

## 5. Criar o segredo de runtime no OCI Vault

Crie um secret chamado, por exemplo:

```text
axiom-runtime-env
```

Insira o conteúdo diretamente no OCI Vault, usando novos valores de credencial:

```dotenv
AXIOM_NVIDIA_ENABLED=true
NVIDIA_API_KEY=<new-nvidia-api-key>
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
AXIOM_NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<new-langsmith-service-key>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=axiom-tech-v3
LANGSMITH_WORKSPACE_ID=
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true

AXIOM_CORS_ORIGINS=http://137.131.132.101:8080
```

A aplicação já está preparada para ativar o modelo NVIDIA, enviar traces do LangGraph para o projeto `axiom-tech-v3` e ocultar entradas e saídas sensíveis. Consulte os guias oficiais de [tracing com LangGraph](https://docs.langchain.com/langsmith/trace-with-langgraph) e [ocultação de inputs e outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs).

## 6. Permitir que a VM leia o Vault

A autenticação local do MCP e a autenticação da VM são diferentes. O MCP usa o perfil `axiom-deploy`; a VM deve usar Instance Principal.

1. Crie um Dynamic Group para a instância `codex-net2`.
2. Crie uma policy semelhante:

```text
Allow dynamic-group axiom-net2-dg to read secret-bundles in compartment axiom-secrets
```

3. Depois de instalar a OCI CLI na VM, materialize o segredo sem imprimir seu valor:

```bash
umask 077

oci secrets secret-bundle get \
  --auth instance_principal \
  --secret-id "<runtime-secret-ocid>" \
  --query 'data.secret-bundle-content.content' \
  --raw-output | base64 --decode > /opt/axiom/.env

chmod 600 /opt/axiom/.env
```

## 7. Reiniciar e validar a aplicação

Acesse a VM usando a chave SSH local:

```powershell
$sshKey = 'C:\Users\adm\Desktop\ANDRÉ\ssh-key-2026-08-04 (1).key'

ssh -i $sshKey -o IdentitiesOnly=yes ubuntu@137.131.132.101
```

Na VM:

```bash
cd /opt/axiom

sudo docker compose \
  -f docker-compose.yml \
  -f docker-compose.oci.yml \
  up -d --force-recreate

sudo docker compose ps

curl -fsS http://127.0.0.1:8000/api/v1/status
```

Depois da configuração, o status esperado será semelhante a:

```json
{
  "observability": {
    "provider": "langsmith",
    "enabled": true,
    "configured": true,
    "project": "axiom-tech-v3",
    "inputs_hidden": true,
    "outputs_hidden": true
  }
}
```

Teste externamente:

```powershell
curl.exe --fail http://137.131.132.101:8080/api/v1/health
```

Faça também uma consulta não sensível e confirme no LangSmith que o projeto recebeu o trace do grafo e, com NVIDIA habilitado, o span aninhado do provedor.

## 8. Persistência com Block Volume

O ChromaDB está atualmente no disco raiz da VM. Antes de considerar o ambiente como produção:

1. Anexe um OCI Block Volume à VM.
2. Identifique o novo dispositivo com `lsblk -f`.
3. Não formate nenhum dispositivo existente.
4. Monte o volume em `/var/lib/axiom-data`.
5. Garanta a permissão do usuário do container:

```bash
sudo chown -R 999:999 /var/lib/axiom-data
```

O override `docker-compose.oci.yml` já mapeia:

```text
/var/lib/axiom-data/chroma:/data/chroma
```

Após reiniciar o container, confirme que a ingestão e as citações continuam funcionando.

## Próxima ação

Crie o perfil `axiom-deploy`, reinicie o Codex e responda apenas:

```text
OCI MCP ready
```

Não envie o conteúdo da configuração, da chave privada ou dos secrets.
