# First OCI Deployment with the Oracle OCI Cloud MCP Server

## Status and scope

This is the first-deployment runbook for Axiom Tech V3. It does not claim that a cloud resource, public URL, screenshot, or LangSmith production project has already been created.

The baseline target is an OCI Compute VM running the existing Docker Compose topology:

```text
Internet -> OCI VCN/subnet -> Compute VM -> Nginx frontend :8080
                                      -> FastAPI API :8000
                                      -> Block Volume mounted at /data/chroma
                                      -> OCI Vault materialized runtime secret file
                                      -> LangSmith/NVIDIA HTTPS egress when explicitly enabled
```

This target is intentional for the first go-live because the default ChromaDB index needs durable writable storage. OCI Container Instances are suitable for stateless containers, but their writable data volume is ephemeral; use them only after moving the vector store to a managed/durable service.

## Challenge acceptance mapping

The deployment satisfies the “at least one OCI service” requirement through OCI Compute. OCI Vault and Block Volume are recommended hardening additions. OCI Container Registry (OCIR) is recommended for repeatable image delivery but is not required for the first public proof if the VM builds the tagged release locally.

The final README still needs a sanitized screenshot or short video showing:

- the online browser URL;
- an answer generated from a known internal document;
- at least one visible citation;
- no credentials, private IPs, terminals, or confidential document content.

See [challenge-checklist.md](challenge-checklist.md).

## 1. Prepare local MCP access

Install `uv` and an OCI CLI profile on the operator machine. The Oracle OCI Cloud MCP server uses the official OCI Python SDK and exposes generic discovery, description, and invocation tools. It does not replace OCI IAM authorization.

Run the server over stdio:

```powershell
uvx oracle.oci-cloud-mcp-server@latest
```

Add it to the MCP client configuration used for the deployment session. Keep this configuration outside the repository:

```json
{
  "mcpServers": {
    "oracle-oci-cloud-mcp-server": {
      "command": "uvx",
      "args": ["oracle.oci-cloud-mcp-server@latest"],
      "env": {
        "OCI_CONFIG_PROFILE": "axiom-deploy",
        "OCI_MCP_AUTH_TYPE": "api_key",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

For a short-lived local session, authenticate with the OCI CLI session flow:

```powershell
oci session authenticate --region=<region> --tenancy-name=<tenancy_name>
```

For repeatable deployment automation, use a dedicated API-key profile or an OCI principal with least privilege. Do not place `~/.oci/config`, private keys, session tokens, or API keys in this repository.

### 1.1 Authenticate and register the MCP host

Installing the package with `uvx` starts the server only when the MCP client launches it. The client that this deployment session uses must also register the server and be restarted or reloaded before the OCI tools become available.

For a local API-key profile, keep the OCI CLI configuration outside this repository, for example in `%USERPROFILE%\\.oci\\config` on Windows:

```ini
[axiom-deploy]
user=ocid1.user.oc1..<user-ocid>
fingerprint=<api-key-fingerprint>
key_file=C:\\Users\\<user>\\.oci\\oci_api_key.pem
tenancy=ocid1.tenancy.oc1..<tenancy-ocid>
region=<oci-region>
```

Validate the profile without printing credentials:

```powershell
oci iam region list --profile axiom-deploy --output json
```

Then register the server in the MCP client configuration used by the assistant:

```json
{
  "mcpServers": {
    "oracle-oci-cloud-mcp-server": {
      "command": "uvx",
      "args": ["oracle.oci-cloud-mcp-server@latest"],
      "env": {
        "OCI_CONFIG_PROFILE": "axiom-deploy",
        "FASTMCP_LOG_LEVEL": "ERROR"
      }
    }
  }
}
```

After reloading the MCP client, the session should expose tools such as `list_oci_clients`, `find_oci_api`, `describe_oci_operation`, and `invoke_oci_api`. If those tools are absent, the server is installed locally but not connected to the assistant session; do not paste the OCI config or private key into chat.

## 2. Supply deployment inputs without committing them

Keep the following values in a local deployment parameter file or secret manager, not in Git:

```text
OCI_REGION=<region>
OCI_COMPARTMENT_OCID=<compartment-ocid>
OCI_AVAILABILITY_DOMAIN=<availability-domain>
OCI_SUBNET_OCID=<subnet-ocid>
OCI_IMAGE_TAG=<immutable-git-tag>
OCI_SSH_PUBLIC_KEY=<ssh-public-key>
OPERATOR_CIDR=<your-public-ip>/32
```

Prefer an existing VCN and subnet for the first run. If one does not exist, create a small public subnet with an internet gateway and restrict SSH to `OPERATOR_CIDR`. Allow only the application port needed for the first smoke test (`8080`); use a load balancer and TLS before treating the endpoint as a long-lived production service.

## 3. Use MCP in a read-before-write sequence

The server’s normal workflow is: discover a client/method, describe its exact contract, then invoke it. Use compact responses and never request full secret payloads.

Examples of the tool calls are shown below in the Oracle MCP server’s native tool vocabulary:

```json
{
  "tool": "find_oci_api",
  "arguments": {
    "query": "list availability domains",
    "limit": 3,
    "include_params": true
  }
}
```

Then describe the operation returned by discovery before invoking it:

```json
{
  "tool": "describe_oci_operation",
  "arguments": {
    "client_fqn": "oci.identity.IdentityClient",
    "operation": "list_availability_domains"
  }
}
```

Use `invoke_oci_api` for read-only discovery first. Keep response fields narrow:

```json
{
  "tool": "invoke_oci_api",
  "arguments": {
    "client_fqn": "oci.identity.IdentityClient",
    "operation": "list_availability_domains",
    "params": {
      "compartment_id": "<compartment-ocid>"
    },
    "fields": ["name", "id"],
    "max_results": 10,
    "result_mode": "summary"
  }
}
```

Repeat discovery/description for the exact operations needed by the chosen topology. Typical SDK families are:

| Purpose | OCI SDK client family | Typical operations |
| --- | --- | --- |
| Inspect tenancy and placement | `oci.identity.IdentityClient` | `list_regions`, `list_availability_domains` |
| Inspect or create networking | `oci.core.VirtualNetworkClient` | `list_vcns`, `list_subnets`, `create_vcn`, `create_subnet`, `create_internet_gateway`, `create_route_table` |
| Inspect or create compute | `oci.core.ComputeClient` | `list_instances`, `list_shapes`, `launch_instance`, `get_instance` |
| Durable Chroma storage | `oci.core.BlockstorageClient` and `oci.core.ComputeClient` | `create_volume`, `get_volume`, `attach_volume`, `get_volume_attachment` |
| Runtime secrets | `oci.secrets.SecretsClient` | `get_secret_bundle` (metadata/content access only when explicitly required) |
| Optional image registry | `oci.artifacts.ArtifactsClient` | `create_container_repository`, repository/image inspection operations |

Before each mutating call, confirm the compartment, region, display name, CIDR, shape, and lifecycle target. Use immutable release tags; do not deploy `latest` as the only rollback reference.

## 4. Create or select OCI resources

The minimum first run is:

1. Select a compartment, region, availability domain, VCN, and subnet.
2. Ensure the subnet routes internet traffic through an internet gateway or NAT appropriate to the chosen layout.
3. Allow SSH only from the operator CIDR and allow the frontend port from the intended reviewer audience.
4. Launch an OCI Compute VM with a supported Linux image and an SSH public key.
5. Attach a Block Volume and mount it on the VM at `/var/lib/axiom-data`.
6. Create an OCI Vault secret containing the runtime `.env` payload described below.
7. Grant the VM’s dynamic group permission to read only that secret bundle.

The mutating operation payloads vary by OCI region, image, shape, and SDK version. Always call `describe_oci_operation` immediately before `invoke_oci_api`; use the returned request-model fields rather than copying an old payload from this document.

A least-privilege policy normally has the shape below. Replace the group, compartment, and secret scope according to the tenancy’s IAM policy; an administrator must approve it:

```text
Allow dynamic-group axiom-compute-dg to read secret-bundles in compartment <secret-compartment>
```

Do not grant the deployment profile tenancy-wide write permissions when compartment-scoped permissions are sufficient.

## 5. SSH handoff and remote pre-flight

The application deployment can be completed over SSH after the OCI VM exists. Do not send a private key, passphrase, OCI API key, NVIDIA key, LangSmith key, or Vault secret value through chat. Keep the private key on the operator workstation and use an SSH agent when possible.

Create an SSH alias in the operator's local OpenSSH configuration, for example `C:\\Users\\<user>\\.ssh\\config`:

```sshconfig
Host axiom-oci
    HostName <public-ip-or-dns>
    User opc
    Port 22
    IdentityFile C:\Users\<user>\.ssh\axiom-oci
    IdentitiesOnly yes
```

Use `opc` for the standard Oracle Linux image or `ubuntu` for an Ubuntu image. Verify the host fingerprint in the OCI Console before accepting it locally. Prefer an agent-backed key:

```powershell
ssh-add C:\Users\<user>\.ssh\axiom-oci
ssh -o BatchMode=yes axiom-oci 'printf "SSH_OK\n"; hostname; whoami; uname -a'
```

The deployment handoff needs only these non-secret values:

```text
SSH alias or public host
SSH username and port
Immutable Git tag or commit
Runtime Vault secret OCID
Block Volume mount path
Public browser hostname or IP
```

The first remote command is read-only. Confirm the host, OS, free disk, Docker status, mounted Block Volume, and OCI principal before installing or changing anything:

```bash
set -eu
hostname
whoami
cat /etc/os-release
df -h
docker version
mountpoint /var/lib/axiom-data
oci os ns get
```

If any pre-flight value is wrong, stop and correct the target before continuing. Never format or mount an unrecognized block device automatically.

## 6. Build and start the release on the VM

Install Docker using the distribution’s supported method, clone the public repository at the immutable release tag, and create the application directory:

```bash
sudo mkdir -p /opt/axiom
sudo chown "$USER":"$USER" /opt/axiom
git clone https://github.com/andrecodexvictor/Axiom-Tech.git /opt/axiom
cd /opt/axiom
git fetch --tags
git checkout <immutable-git-tag>
```

Mount the Block Volume at `/var/lib/axiom-data`, then create the runtime file from OCI Vault. The following pattern writes the secret locally with restrictive permissions without printing its value:

```bash
umask 077
mkdir -p /opt/axiom
oci secrets secret-bundle get \
  --secret-id "<runtime-secret-ocid>" \
  --query 'data.secret-bundle-content.content' \
  --raw-output | base64 --decode > /opt/axiom/.env
chmod 600 /opt/axiom/.env
```

The Vault secret content should be a complete dotenv payload, for example:

```dotenv
AXIOM_DOCUMENTS_DIR=/app/documentos
AXIOM_CHROMA_PATH=/data/chroma
AXIOM_VECTOR_BACKEND=chroma
AXIOM_NVIDIA_ENABLED=true
NVIDIA_MODEL=meta/llama-3.1-70b-instruct
NVIDIA_API_KEY=<stored-in-vault>
AXIOM_CORS_ORIGINS=http://<public-host>:8080
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<stored-in-vault>
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=axiom-tech-v3
LANGSMITH_HIDE_INPUTS=true
LANGSMITH_HIDE_OUTPUTS=true
```

The angle-bracket values above are placeholders only. Store real provider values in the secret, and never paste them into this file, a terminal transcript, or an MCP request. Add `LANGSMITH_WORKSPACE_ID` only when the LangSmith key requires it. Add `SERPER_API_KEY` and `AXIOM_WEB_ENABLED=true` only when the explicit web route has been approved.

For the first smoke test, the repository Compose file builds both images on the VM. Mount the Block Volume at `/var/lib/axiom-data`, then use the versioned `docker-compose.oci.yml` override so ChromaDB persists at `/var/lib/axiom-data/chroma`. Do not place the Chroma index on the VM’s ephemeral boot disk.

```bash
docker compose -f docker-compose.yml -f docker-compose.oci.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.oci.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.oci.yml ps
```

If the release is delivered through OCIR, build and push immutable `api:<tag>` and `frontend:<tag>` images, then use a non-versioned local Compose override that references those exact image tags. Keep the registry login token in OCI Vault or the operator’s credential helper.

## 7. Ingest, verify, and record the run

Run the explicit ingestion pass once the API is healthy:

```bash
curl --fail http://127.0.0.1:8000/api/v1/health
curl --fail http://127.0.0.1:8000/api/v1/status
docker compose -f docker-compose.yml -f docker-compose.oci.yml exec api python -m app.main --ingest
curl --fail http://127.0.0.1:8080/api/v1/health
```

Then submit one known, non-sensitive question through the browser and verify:

- the answer is grounded and displays at least one citation;
- `/api/v1/status` reports Chroma as the active vector backend;
- `/api/v1/status` reports LangSmith `enabled=true` and `configured=true` when tracing is intended;
- the LangSmith project receives the graph trace and, in NVIDIA mode, the nested provider span;
- a container restart retains the index and the answer still cites the expected source.

Record the release tag, UTC timestamp, public URL, health result, ingestion counts, status summary, and LangSmith project name in the deployment record. Do not record key values or raw prompts.

## 8. Rollback

Keep the previous immutable release tag and the Block Volume. To roll back, check out the previous tag, rebuild or pull the matching images, and run the OCI Compose override again. Do not run `docker compose down -v` during a rollback: that deletes the local Chroma volume and its indexed data.

If the endpoint is compromised or a credential may have leaked, revoke and rotate the affected key first, update the OCI Vault secret, recreate `.env` with mode `600`, and restart the API container. A LangSmith key shared outside the secret store must be considered compromised and replaced.

## References

- [Oracle MCP repository](https://github.com/oracle/mcp)
- [OCI Cloud MCP Server README](https://github.com/oracle/mcp/blob/main/src/oci-cloud-mcp-server/README.md)
- [OCI Container Instances creation guide](https://docs.oracle.com/en-us/iaas/Content/container-instances/creating-a-container-instance.htm)
- [OCI Vault secret management](https://docs.oracle.com/en-us/iaas/Content/secret-management/Concepts/manage-secrets.htm)
- [OCI secret contents retrieval](https://docs.oracle.com/en-us/iaas/Content/secret-management/Tasks/get-secrets-contents.htm)
