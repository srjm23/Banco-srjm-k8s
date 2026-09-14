# Vault e External Secrets — operação

O Vault armazena as credenciais em KV v2. O ESO autentica por identidades Kubernetes e sincroniza quatro Secrets: PostgreSQL, variáveis do backend, arquivo Spring e token Cloudflare. Configurações comuns permanecem em ConfigMaps. Base64 não é criptografia.

| Store | Namespace permitido | Caminho lógico KV v2 |
| --- | --- | --- |
| `vault-banco` | `banco-srjm` | `secret/banco-srjm/*` |
| `vault-cert-manager` | `cert-manager` | `secret/cert-manager/cloudflare-api-token-secret` |

A instalação utiliza TLS interno, Service ClusterIP e Raft em PVC gp3 de 5 GiB, com uma réplica. Não oferece alta disponibilidade ou auto-unseal. Os placeholders frontend/Mailpit foram removidos dos arquivos por não terem consumidores.

## Instalação

- [Instalação e configuração manual, sem Python](vault-cli.md): fluxo preferido para um cluster novo e parametrizado.
- [Scripts opcionais](../scripts/README.md): bootstrap e operação do ambiente histórico `eks-new`, com quatro Secrets de origem.
- [Inventário dos manifestos](../k8s/README.md): TLS, stores, identidades e recursos consumidores.

Escolha um fluxo de bootstrap. O procedimento manual não produz automaticamente o arquivo local esperado pelo script Python.

## Diagnóstico e acesso

```bash
kubectl -n vault get pods,pvc
kubectl get clustersecretstores
kubectl get externalsecrets -A
kubectl -n vault exec vault-0 -- vault status
```

Se `Sealed: true`, execute duas vezes, informando chaves diferentes nos prompts ocultos:

```bash
kubectl -n vault exec -it vault-0 -- vault operator unseal
kubectl -n vault exec -it vault-0 -- vault operator unseal
kubectl wait --for=condition=Ready clustersecretstore/vault-banco clustersecretstore/vault-cert-manager --timeout=180s
```

Não inicialize novamente um Vault existente. Proteja as chaves de unseal e faça backup dos snapshots Raft. O arquivo `.secrets/vault-init.json` existe somente quando gerado pelo bootstrap do projeto; na instalação manual, utilize o arquivo/backup criado por aquele procedimento.

Para acessar a UI:

```bash
kubectl -n vault port-forward svc/vault 8200:8200
```

Abra `https://localhost:8200` utilizando a CA interna. Obtenha o token pela identidade administrativa configurada no [guia CLI](vault-cli.md) ou pelo [script de administração](../scripts/README.md), conforme o fluxo adotado.

## Atualizações

O ESO consulta os dados a cada minuto. Alterações de variáveis de ambiente exigem nova revisão Knative, por exemplo atualizando `configVersion` no chart. A rotação de senha PostgreSQL exige alterar a senha do banco já inicializado e coordenar seus consumidores.

Os charts banco/backend gerenciam os três ExternalSecrets da aplicação no fluxo Helm novo. O token Cloudflare e os stores são compartilhados. Não reaplique a base Kustomize sobre recursos adotados por Helm/Argo.
