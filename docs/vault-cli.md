# Vault e External Secrets pela CLI

Execute esta etapa após instalar Vault e ESO no [README principal](../README.md), mantendo os parâmetros daquela sessão. Requer Bash, Vault CLI, kubectl e jq; não utiliza Python. Os comandos de inicialização e `enable` destinam-se a um Vault novo. Em instalação existente, preserve mounts, políticas e credenciais e utilize sua identidade administrativa.

## 1. Acesso TLS, inicialização e unseal

Em outro terminal, informe o mesmo contexto e mantenha o port-forward aberto:

```bash
read -r -p "Contexto Kubernetes usado na instalação: " KUBE_CONTEXT
kubectl --context "$KUBE_CONTEXT" -n vault port-forward pod/vault-0 8200:8200
```

No terminal principal, prepare arquivos privados fora do repositório:

```bash
set +x
umask 077
export VAULT_WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/banco-vault.XXXXXX")"
kubectl --context "$KUBE_CONTEXT" -n vault get secret vault-server-tls \
  -o jsonpath='{.data.ca\.crt}' | base64 --decode > "$VAULT_WORK_DIR/ca.crt"
export VAULT_ADDR="https://127.0.0.1:8200"
export VAULT_CACERT="$VAULT_WORK_DIR/ca.crt"
vault status
```

`vault status` retorna código 2 enquanto selado. Confirme `Initialized=false` antes de inicializar. Execute uma única vez:

```bash
vault operator init -key-shares=3 -key-threshold=2 -format=json > "$VAULT_WORK_DIR/init.json"
```

Guarde o arquivo de inicialização em armazenamento protegido fora do diretório temporário e distribua as partes a custodiantes. Ele contém três chaves e o token root; não publique seu conteúdo. Faça também backup dos snapshots Raft. As chaves não substituem os dados do PVC.

Execute duas vezes, informando uma chave diferente em cada prompt oculto:

```bash
vault operator unseal
vault operator unseal
export VAULT_TOKEN="$(jq -r '.root_token' "$VAULT_WORK_DIR/init.json")"
vault status
```

## 2. KV v2 e autenticação Kubernetes

```bash
vault secrets enable -path=secret kv-v2
vault auth enable kubernetes
vault write auth/kubernetes/config \
  kubernetes_host=https://kubernetes.default.svc:443 \
  disable_local_ca_jwt=false disable_iss_validation=true
```

O Vault usa o token e a CA locais do seu pod para TokenReview; o chart habilita `authDelegator`. Não é necessário armazenar um token reviewer estático. [Autenticação Kubernetes](https://developer.hashicorp.com/vault/docs/auth/kubernetes).

Crie duas políticas isoladas e suas roles:

```bash
vault policy write vault-banco-reader - <<'HCL'
path "secret/data/banco-srjm/*" {
  capabilities = ["read"]
}
HCL
vault policy write vault-cert-manager-reader - <<'HCL'
path "secret/data/cert-manager/cloudflare-api-token-secret" {
  capabilities = ["read"]
}
HCL
for scope in banco cert-manager; do
  vault write "auth/kubernetes/role/vault-${scope}-reader" \
    "bound_service_account_names=vault-${scope}-reader" \
    bound_service_account_namespaces=external-secrets audience=vault \
    "token_policies=vault-${scope}-reader" token_ttl=1h token_max_ttl=1h
done
```

## 3. Credenciais iniciais e token Cloudflare

Prepare fora do Git `postgres.json`, `backend.json` e `application.yaml`, com valores reais compatíveis com a imagem da aplicação:

| Arquivo | Conteúdo |
| --- | --- |
| `postgres.json` | Objeto JSON com chave `POSTGRES_PASSWORD` e senha string |
| `backend.json` | Objeto JSON com `DB_URL` e demais variáveis sensíveis exigidas pelo backend, todas strings |
| `application.yaml` | Arquivo Spring que será montado em `/etc/banco/application.yaml` |

Com os values padrão, o banco é `banco_programacao`, usuário `banco_user`, endpoint `postgres.banco-srjm.svc.cluster.local:5432`. Ajuste a URL JDBC e o arquivo Spring para esse destino. Se mudar domínio, revise também qualquer URL absoluta nesse arquivo. As credenciais não são fornecidas pelo chart.

Informe o diretório e grave os dados. Em ambiente existente, `kv put` cria uma nova versão e substitui o conjunto de chaves do caminho: revise os arquivos antes de atualizar.

```bash
read -r -p "Diretório privado com os arquivos de credenciais: " PRIVATE_INPUT_DIR
vault kv put -mount=secret banco-srjm/postgres-secret "@$PRIVATE_INPUT_DIR/postgres.json"
vault kv put -mount=secret banco-srjm/backend-secret "@$PRIVATE_INPUT_DIR/backend.json"
jq -n --rawfile application "$PRIVATE_INPUT_DIR/application.yaml" \
  '{"application.yaml": $application}' | vault kv put -mount=secret banco-srjm/backend-application -
read -r -s -p "Token Cloudflare DNS-01: " CF_API_TOKEN
printf '\n'
test -n "$CF_API_TOKEN" && printf '%s' "$CF_API_TOKEN" | \
  vault kv put -mount=secret cert-manager/cloudflare-api-token-secret api-token=-
unset CF_API_TOKEN
```

O token entra por stdin, sem aparecer no comando executado pelo Vault ou nos values Helm. Ele precisa das permissões DNS Edit e Zone Read para a zona utilizada. [Entrada de dados no Vault CLI](https://developer.hashicorp.com/vault/docs/commands/kv/put).

## 4. Stores e sincronização Cloudflare

Crie a CA pública a partir desta instalação, sem reutilizar a CA registrada para outro cluster:

```bash
kubectl --context "$KUBE_CONTEXT" -n external-secrets create configmap vault-ca \
  --from-file="ca.crt=$VAULT_WORK_DIR/ca.crt" --dry-run=client -o yaml | kubectl --context "$KUBE_CONTEXT" apply -f -
kubectl --context "$KUBE_CONTEXT" apply -f k8s/external-secrets/vault-banco-reader.yaml
kubectl --context "$KUBE_CONTEXT" apply -f k8s/external-secrets/vault-cert-manager-reader.yaml
kubectl --context "$KUBE_CONTEXT" apply -f k8s/external-secrets/cluster-store-banco.yaml
kubectl --context "$KUBE_CONTEXT" apply -f k8s/external-secrets/cluster-store-cert-manager.yaml
kubectl --context "$KUBE_CONTEXT" wait --for=condition=Ready \
  clustersecretstore/vault-banco clustersecretstore/vault-cert-manager --timeout=180s
kubectl --context "$KUBE_CONTEXT" apply -f k8s/external-secrets/cloudflare-api-token-secret.yaml
kubectl --context "$KUBE_CONTEXT" -n cert-manager wait \
  --for=condition=Ready externalsecret/cloudflare-api-token-secret --timeout=180s
```

Não aplique `-k k8s/external-secrets` neste fluxo novo: ele também criaria recursos que pertencerão aos charts. Os placeholders frontend/Mailpit não são necessários à instalação Helm. Os três ExternalSecrets da aplicação serão criados na instalação de banco/backend.

## 5. Acesso administrativo e encerramento do bootstrap

Configure uma identidade administrativa para os caminhos do projeto antes de revogar root. A ServiceAccount `vault-admin` foi criada por `k8s/vault/`.

```bash
vault policy write banco-vault-admin - <<'HCL'
path "secret/data/banco-srjm/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "secret/data/cert-manager/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}
path "secret/metadata/banco-srjm/*" {
  capabilities = ["read", "list"]
}
path "secret/metadata/cert-manager/*" {
  capabilities = ["read", "list"]
}
HCL
vault write auth/kubernetes/role/banco-vault-admin \
  bound_service_account_names=vault-admin bound_service_account_namespaces=vault \
  audience=vault token_policies=banco-vault-admin token_ttl=15m token_max_ttl=1h
kubectl --context "$KUBE_CONTEXT" -n vault create token vault-admin --audience=vault --duration=10m | \
  vault write -field=token auth/kubernetes/login role=banco-vault-admin jwt=- > "$VAULT_WORK_DIR/admin-token"
VAULT_TOKEN="$(cat "$VAULT_WORK_DIR/admin-token")" vault kv get -mount=secret \
  banco-srjm/backend-secret > /dev/null
```

Somente após esse teste e os stores/ExternalSecret estarem Ready, revogue o token root da sessão:

```bash
vault token revoke -self
unset VAULT_TOKEN
```

O token root no arquivo inicial fica inválido; preserve as chaves de unseal. Volte à **etapa 5 do README principal** para configurar o emissor e instalar os charts.

Após reinício, repita o port-forward, configure `VAULT_ADDR`/`VAULT_CACERT` e execute `vault operator unseal` duas vezes. Para administrar os dados, repita o login Kubernetes acima e carregue o token temporário em `VAULT_TOKEN`. A UI fica em `https://localhost:8200`, usando a CA interna. Este fluxo manual não gera o estado local esperado pelo script Python de bootstrap.
