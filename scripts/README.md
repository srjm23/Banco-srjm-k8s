# Scripts opcionais do projeto

A instalação principal está no [README da raiz](../README.md) e usa Helm, kubectl e Vault CLI, sem Python. Estes scripts automatizam validações, empacotamento, documentação e o fluxo histórico de migração para Vault.

## Pré-requisitos

Execute na raiz do repositório com Python 3 e Helm. O bootstrap também requer kubectl e acesso ao cluster. O gerador PDF utiliza ReportLab.

```bash
python3 -m venv /tmp/banco-srjm-python
. /tmp/banco-srjm-python/bin/activate
python3 -m pip install PyYAML reportlab
```

## Comandos

| Script | Finalidade | Altera o cluster? |
| --- | --- | --- |
| `validate-manifests.py` | Confere recursos, referências e selectors dos manifests Kustomize | Não |
| `validate-helm.py` | Lint e verificações de paridade, referências e opções dos charts | Não |
| `package-helm.py` | Valida, renderiza, empacota e gera o índice Helm | Não |
| `generate-guide-pdf.py` | Gera o PDF do guia didático | Não |
| `bootstrap-vault.py` | Inicializa/desbloqueia Vault, migra Secrets e configura autenticação/políticas | **Sim** |

### Validar e empacotar

```bash
python3 scripts/validate-manifests.py
python3 scripts/validate-helm.py
python3 scripts/package-helm.py --url https://srjm23.github.io/Banco-srjm-k8s/
```

O empacotamento já executa as verificações Helm. As saídas ficam em `build/helm-rendered/` e `helm/repository/`. O script não publica no GitHub Pages nem instala os charts. Consulte [publicação](../helm/README.md).

### Gerar PDF

```bash
python3 scripts/generate-guide-pdf.py
```

Saída: [guia-didatico-banco-srjm.pdf](../docs/guia-didatico-banco-srjm.pdf). O conteúdo segue o gerador e suas fontes; não é uma conversão automática do README atual.

## Bootstrap Vault: fluxo histórico, separado da instalação manual

**Limitação atual:** `bootstrap-vault.py` fixa `CONTEXT = 'eks-new'` e namespace `banco-srjm`; não recebe `--context` ou os parâmetros do README. Não o execute supondo que utilizará o contexto atual. Para outro cluster, prefira o [procedimento manual parametrizado](../docs/vault-cli.md).

Pré-requisitos: Vault instalado com TLS e armazenamento, cert-manager/ESO disponíveis e quatro Secrets iniciais existentes:

- `banco-srjm/postgres-secret`, `backend-secret`, `backend-application`.
- `cert-manager/cloudflare-api-token-secret`.

O script migra esses Secrets; não inventa credenciais nem as obtém dos charts. Os placeholders frontend/Mailpit foram removidos por não serem consumidos pelos workloads.

Para uma migração inicial autorizada no contexto `eks-new`:

```bash
python3 scripts/bootstrap-vault.py
kubectl --context eks-new apply -k k8s/external-secrets
kubectl --context eks-new wait --for=condition=Ready \
  clustersecretstore/vault-banco clustersecretstore/vault-cert-manager --timeout=180s
kubectl --context eks-new -n banco-srjm wait --for=condition=Ready externalsecret --all --timeout=180s
kubectl --context eks-new -n cert-manager wait --for=condition=Ready \
  externalsecret/cloudflare-api-token-secret --timeout=180s
python3 scripts/bootstrap-vault.py --verify-and-finalize
```

O bootstrap grava chaves em `.secrets/vault-init.json`, configura KV v2/políticas, migra os dados e atualiza a CA pública em `k8s/external-secrets/vault-ca.yaml`. A finalização verifica sincronização e isolamento antes de revogar root. Proteja e faça backup das chaves e dos dados Raft.

Esse fluxo aplica ExternalSecrets da aplicação por Kustomize. Antes de instalar os charts, adote esses recursos ou use `--set externalSecrets.enabled=false` em banco/backend para reutilizá-los. Não misture os dois procedimentos de bootstrap.

### Operação após bootstrap pelo script

```bash
python3 scripts/bootstrap-vault.py --unseal
python3 scripts/bootstrap-vault.py --admin-token
python3 scripts/bootstrap-vault.py --verify-and-finalize
```

- `--unseal`: desbloqueia usando o arquivo local de inicialização.
- `--admin-token`: autentica por Kubernetes e grava token temporário em `.secrets/vault-admin-token`.
- `--verify-and-finalize`: verifica os quatro Secrets e as políticas; revoga root quando ainda presente.

Essas opções dependem do estado local criado pelo script. Um Vault inicializado manualmente não possui automaticamente esse arquivo. O script abre port-forward na porta local 18200 e pode modificar recursos/arquivos mesmo nos modos de operação.
