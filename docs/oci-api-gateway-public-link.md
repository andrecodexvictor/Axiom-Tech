# Link público HTTPS com OCI API Gateway

Este guia configura o OCI API Gateway para publicar a aplicação Axiom Tech por um endereço HTTPS no formato:

```text
https://<gateway-hostname>.apigateway.sa-saopaulo-1.oci.customer-oci.com/
```

O Gateway termina o HTTPS e encaminha as requisições por HTTP para o frontend Nginx da VM de testes:

```text
Cliente HTTPS → OCI API Gateway → http://137.131.246.99:8080
```

## Pré-requisitos

- A VM `137.131.246.99` está em execução.
- A aplicação responde em `http://137.131.246.99:8080/`.
- A Security List da subnet da VM permite TCP `8080` como ingress.
- Existe um API Gateway do tipo **Public** associado a uma subnet pública.
- O deployment do Gateway está no compartimento correto.

Para um Gateway público, a subnet precisa ter conectividade adequada com a Internet. A OCI também pode exigir uma regra de ingress TCP `443` na subnet do Gateway.

## Editar o deployment

No OCI Console, abra:

**Developer Services → API Management → Gateways → `<seu gateway>` → Deployments**

Abra o deployment existente e selecione **Edit**.

### 1. Basic information

Mantenha:

| Campo | Valor |
| --- | --- |
| Name | `AxiomTechPublicDeployment` |
| Path prefix | `/` |
| Enable mTLS | Desativado |

Clique em **Next**.

### 2. Authentication

Não habilite autenticação para este ambiente de testes. Selecione **None** ou **No authentication** e avance.

### 3. Route

Na seção **Routes**, edite ou remova a rota antiga e crie uma única rota abrangente:

| Campo | Valor |
| --- | --- |
| Path | `/{request_path*}` |
| Methods | `ANY` |
| Backend | Add a single backend |
| Backend Type | `HTTP` |
| URL | `http://137.131.246.99:8080/${request.path[request_path]}` |

Se a Console não oferecer `ANY`, selecione todos os métodos necessários: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `OPTIONS` e `HEAD`.

Deixe os timeouts padrão. Como o backend usa HTTP, a opção **Disable SSL verification** não precisa ser habilitada.

Clique em **Create/Update route**, depois em **Next**, revise a configuração e selecione **Update** ou **Save changes**.

`/{request_path*}` encaminha a raiz, os arquivos estáticos do frontend e as rotas `/api/...`. A expressão `${request.path[request_path]}` preserva o caminho original ao chamar a VM.

## Validar o deployment

Aguarde o deployment ficar **Active**. Copie o hostname exibido na página de detalhes e teste:

```text
https://<gateway-hostname>/
```

Teste também a API:

```text
https://<gateway-hostname>/api/v1/health
```

A resposta esperada é semelhante a:

```json
{"status":"ok","version":"3.1.0"}
```

O hostname gerado pelo OCI continua sendo o mesmo quando o deployment existente é atualizado.

## Diagnóstico rápido

### Erro 502 ou 504

Verifique:

- TCP `8080` liberado na Security List da subnet da VM.
- A VM ainda responde diretamente em `http://137.131.246.99:8080/api/v1/health`.
- O backend está exatamente como `http://137.131.246.99:8080/${request.path[request_path]}`.
- O Gateway está **Active**.
- A subnet do Gateway possui rota e conectividade para alcançar o IP público da VM.

### Página abre, mas os arquivos ou a API falham

Confirme que a rota é `/{request_path*}` e que o método inclui `GET`, `POST` e `OPTIONS`. Uma rota somente `/` atende a página inicial, mas não cobre corretamente `/assets/...` e `/api/...`.

## Referências oficiais

- [Adicionar backend HTTP ou HTTPS ao OCI API Gateway](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayusinghttpbackend.htm)
- [Adicionar parâmetros e wildcards às rotas](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewayaddingparamswildcards.htm)
- [Criar um API deployment](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingdeployment.htm)
