# Guia de secrets no OCI Vault

Este guia explica como armazenar as credenciais do Axiom Tech no OCI Vault sem colocar valores sensíveis no Git, no README ou no GitHub Actions.

## Credenciais utilizadas

Crie um secret separado para cada credencial:

| Secret name | Variável de ambiente | Uso |
| --- | --- | --- |
| `axiom-kimi-api-key` | `KIMI_API_KEY` | Adapter legado Kimi |
| `axiom-minimax-api-key` | `MINIMAX_API_KEY` | Adapter legado MiniMax |
| `axiom-deepseek-api-key` | `DEEPSEEK_API_KEY` | Credential compatível com o gateway NVIDIA |
| `axiom-langsmith-api-key` | `LANGSMITH_API_KEY` | Tracing e observabilidade LangSmith |

Os valores ficam apenas no arquivo local ignorado `.env.local`. Nunca copie os valores para este documento.

## 1. Abrir ou criar o Vault

1. Entre na OCI Console.
2. Selecione a região `Brazil East (São Paulo)`.
3. Abra o menu de navegação e selecione **Identity & Security → Vault**.
4. Escolha o compartimento `andrevictorandrade (root)`.
5. Abra um Vault existente ou selecione **Create Vault**.
6. Dentro do Vault, confirme que existe uma chave de criptografia simétrica (`symmetric`).

Secrets precisam ser criptografados com uma chave simétrica pertencente ao mesmo Vault. Consulte a [documentação oficial de Vaults](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/managingvaults.htm).

## 2. Criar cada secret

1. Abra **Identity & Security → Secret Management → Secrets**.
2. Selecione **Create Secret**.
3. Informe o compartimento `andrevictorandrade (root)`.
4. Selecione o Vault e a chave simétrica.
5. Em **Secret Generation**, selecione **Manual**.
6. Em **Secret Type Template**, selecione **Plain Text**.
7. Em **Secret Contents**, cole somente o valor da credencial, sem aspas e sem o nome da variável.
8. Informe o `Secret name` correspondente à tabela acima.
9. Selecione **Create Secret**.

Repita o procedimento para as quatro credenciais. A Console faz a codificação necessária antes de enviar o conteúdo ao serviço. O conteúdo máximo de um secret é 25 KB. Consulte [Creating a Secret](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/create-secret.htm).

## 3. Expiração e rotação do LangSmith

A chave LangSmith usada atualmente deve ser revogada ou substituída em até 30 dias.

É possível configurar uma regra de expiração de 30 dias para `axiom-langsmith-api-key`. Antes da expiração:

1. Gere uma nova chave no LangSmith.
2. Abra o secret `axiom-langsmith-api-key` no OCI Vault.
3. Selecione **Create Secret Version**.
4. Cole a nova chave como conteúdo manual.
5. Marque a nova versão como a versão atual.
6. Reinicie ou redeploy a aplicação para materializar a nova versão no ambiente.

O OCID do secret permanece o mesmo durante a rotação; somente a versão do conteúdo muda. Consulte [Editing a Secret](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/update-secret.htm).

## 4. Relação com o `.env` da aplicação

O arquivo local deve conter as configurações, mas nunca deve ser commitado:

```env
AXIOM_NVIDIA_ENABLED=true
NVIDIA_API_KEY=
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
AXIOM_NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1

KIMI_API_KEY=<secret-value>
MINIMAX_API_KEY=<secret-value>
DEEPSEEK_API_KEY=<secret-value>

LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<secret-value>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=axiom-tech-v3
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

`NVIDIA_API_KEY` permanece vazio porque a aplicação usa `DEEPSEEK_API_KEY` como fallback compatível para o gateway NVIDIA.

## 5. Atenção: Vault não injeta secrets automaticamente

Criar os secrets no Vault não altera automaticamente o container. O workflow atual espera que o ambiente da VM tenha o arquivo:

```text
/opt/axiom/.env
```

Para uma integração completa, a VM precisa de uma identidade dinâmica (`Dynamic Group`) e uma policy IAM que permita ler somente os secrets do Axiom Tech. Depois, um script de deploy deve buscar as versões atuais dos secrets e materializar o `.env` antes de executar o Docker Compose.

Enquanto essa integração não estiver implementada, não copie as credenciais para GitHub Variables, Dockerfile, imagens ou arquivos rastreados pelo Git.

Para visualizar o conteúdo de uma versão no OCI Console, abra o secret, entre na lista de versões, abra o menu de ações e selecione **View Secret Contents**. Consulte [Getting a Secret's Contents](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/get-secrets-contents.htm).

## 6. Permitir que a VM leia os secrets

A VM precisa de uma identidade dinâmica e de uma policy IAM. A policy abaixo concede somente a leitura dos secrets do Axiom Tech; ela não concede permissão para criar, alterar ou excluir recursos.

### 6.1 Copiar o OCID da VM

No OCI Console:

1. Abra **Compute → Instances**.
2. Selecione a instância `codex-net2`.
3. Copie o OCID da instância para um local seguro fora do repositório.

Não coloque o OCID, chaves ou valores de secrets neste documento, no Git ou no chat.

### 6.2 Criar o Dynamic Group

Abra **Identity & Security → Dynamic Groups → Create Dynamic Group** e use:

```text
Name: axiom-net2-dg
Description: Axiom Tech VM Vault access
Matching rule: ALL {instance.id = '<INSTANCE_OCID>'}
```

Substitua `<INSTANCE_OCID>` somente no formulário da OCI pelo OCID real da instância `codex-net2`.

### 6.3 Criar a policy de leitura

Abra **Identity & Security → Policies**, selecione o compartimento `andrevictorandrade (root)` e crie:

```text
Name: axiom-net2-vault-read
Description: Allow Axiom VM to read its Vault secrets
```

Adicione uma declaração para cada secret criado. Use o OCID real de cada secret apenas no Console:

```text
Allow dynamic-group axiom-net2-dg to read secret-bundles in compartment andrevictorandrade where target.secret.id='<DEEPSEEK_SECRET_OCID>'
Allow dynamic-group axiom-net2-dg to read secret-bundles in compartment andrevictorandrade where target.secret.id='<MINIMAX_SECRET_OCID>'
Allow dynamic-group axiom-net2-dg to read secret-bundles in compartment andrevictorandrade where target.secret.id='<LANGSMITH_SECRET_OCID>'
```

Adicione também a declaração do Kimi somente se o secret `axiom-kimi-api-key` tiver sido criado:

```text
Allow dynamic-group axiom-net2-dg to read secret-bundles in compartment andrevictorandrade where target.secret.id='<KIMI_SECRET_OCID>'
```

Não use `manage all-resources` nem uma policy ampla na tenancy. Se a policy for criada em outro compartimento, ajuste o nome do compartimento nas declarações para o compartimento que contém os secrets.

Depois que a policy estiver criada, aguarde a propagação das permissões e siga o runbook de deploy para materializar os valores no arquivo `/opt/axiom/.env` da VM antes de recriar os containers.
