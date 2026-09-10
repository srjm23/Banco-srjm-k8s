# Helm — Banco SRJM com Knative

O chart `helm/banco-srjm` usa Knative por padrão e acompanha os manifestos atuais
em `k8s/`. Instale uma release por namespace. O namespace é definido por
`--namespace`; não existe template de Namespace no chart.

## Recursos

- Services Knative `backend` (cluster-local) e `frontend` (sem restrição cluster-local).
- DomainMapping do domínio público para o frontend, Certificate e ClusterDomainClaim.
- PostgreSQL em StatefulSet, PVC, Service `postgres` e `postgres-headless`.
- Mailpit em Deployment e Service, desabilitável por values.
- ConfigMaps de aplicação/Nginx, StorageClass opcional e Secrets opcionais.

O chart não instala Knative, Istio, cert-manager nem AWS Load Balancer Controller.
Ele usa o ingress Istio existente (no ambiente atual, `istio-ingress/istio-ingress`). Não
cria o balanceador externo; consulte [Classic ELB](../docs/istio-aws-classic.md). Gateways/VirtualServices manuais e Deployments de
frontend/backend não são renderizados no modo Knative.

O fluxo é Classic ELB → Istio/Knative → frontend Nginx → backend Knative → PostgreSQL.
O Nginx encaminha `/api/` ao hostname interno do backend na porta 80, preservando
os headers necessários. Consulte [a explicação do Knative](../k8s/README.md).

## Pré-requisitos e Secrets

Knative Serving com integração Istio e DomainMapping, cert-manager e EBS CSI
precisam estar instalados. Para entrada pública, o Classic ELB deve estar provisionado e
o DNS do domínio deve apontar para ele.

Por padrão, `secrets.create=false`. Crie os Secrets no namespace da release pelo
seu mecanismo de gestão de credenciais, com estas chaves:

| Secret padrão | Chaves |
| --- | --- |
| `postgres-secret` | `POSTGRES_PASSWORD` |
| `backend-secret` | `DB_URL`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `DATA_ENCRYPTION_KEY`, `ADMINISTRATOR_CREATION_TOKEN` |

`DB_URL` pode ser `jdbc:postgresql://postgres:5432/banco_programacao` para o banco
local. Os nomes são configuráveis em `secrets.postgresName` e `secrets.backendName`.
Não são necessários Secrets separados de frontend e Mailpit nos templates atuais.

O Certificate é criado no namespace da aplicação e usa o ClusterIssuer existente
`letsencrypt-production`. O Secret TLS é emitido pelo cert-manager e referenciado
pelo DomainMapping. Para criar também o ClusterIssuer via Helm, use
`values-dns01.example.yaml`; o token Cloudflare deve existir no namespace de
recursos de cluster do cert-manager (normalmente `cert-manager`). O chart não
inclui o token.

## Validar e instalar

A partir da raiz do repositório:

```bash
cp helm/values-eks.example.yaml helm/values-eks.local.yaml
# Ajuste os valores locais, prepare os Secrets e confira o contexto Kubernetes.
helm lint helm/banco-srjm -f helm/values-eks.local.yaml
helm template banco-srjm helm/banco-srjm \
  --namespace banco-srjm -f helm/values-eks.local.yaml
python3 scripts/validate-manifests.py

helm upgrade --install banco-srjm helm/banco-srjm \
  --namespace banco-srjm --create-namespace \
  -f helm/values-eks.local.yaml --wait --timeout 10m

# Confira explicitamente as condições dos recursos Knative e TLS.
kubectl -n banco-srjm get ksvc,revisions,domainmappings,certificates
kubectl -n banco-srjm get pods,svc,pvc
```

Helm não assume automaticamente recursos já aplicados pelo Kustomize. Se a
aplicação já existe nesse namespace, planeje a adoção dos recursos antes de
instalar. Não exclua banco ou PVC para resolver conflitos. Para recursos
compartilhados existentes, use `storageClass.create=false`,
`knative.createDomainClaim=false` e `certManager.createIssuer=false`, conforme
quem os gerencia. Isso não resolve a adoção dos demais recursos da aplicação.

## Configurações principais

| Valor | Uso |
| --- | --- |
| `knative.enabled` | `true` por padrão |
| `knative.frontend`, `knative.backend` | `minScale`, `maxScale`, `containerConcurrency` e `traffic` |
| `knative.timeoutSeconds` | Timeout Knative, padrão 300 segundos |
| `knative.flywayConnectRetries` | Tentativas de conexão do Flyway, padrão 60 |
| `knative.clusterDomain` | Sufixo DNS interno, padrão `cluster.local` |
| `istio.host` | Domínio do DomainMapping e Certificate |
| `certManager.enabled` | Cria Certificate, obrigatório neste fluxo HTTPS |
| `certManager.createIssuer` | Cria ClusterIssuer; padrão `false` para reutilizar o existente |
| `postgres.persistence` | Tamanho e StorageClass do PVC |
| `storageClass.create` | Criar ou reutilizar StorageClass |
| `mailpit.enabled` | Desabilitar se houver SMTP externo; ajustar `backend.config` |
| `<componente>.image`, `<componente>.resources` | Imagens e recursos |
| `imagePullSecrets` | Credenciais de registry existentes |

Frontend e backend mantêm no mínimo 1 e no máximo 3 réplicas por revisão,
com concorrência máxima por réplica de 80 e 20, respectivamente. O sidecar Istio
é desabilitado nos pods Knative; o `queue-proxy` continua sendo gerenciado pelo
Knative. O timeout de leitura do proxy Nginx é 60 segundos.

## Fixar uma revisão ou dividir tráfego

Nos seus values locais, use nomes reais de revisões existentes da aplicação:

```yaml
knative:
  backend:
    traffic:
      - revisionName: backend-00003
        percent: 100
```

Para uma implantação gradual, informe duas revisões com percentuais somando 100.
Para acompanhar novamente a revisão pronta mais recente:

```yaml
knative:
  backend:
    traffic:
      - latestRevision: true
        percent: 100
```

O valor padrão `traffic: []` omite o campo e usa o comportamento padrão do
Knative. Prefira a configuração explícita acima ao desfazer uma fixação.
Alterar tráfego não desfaz migrações do banco.

## Secrets criados pelo chart, opcionalmente

Use um arquivo local `helm/banco-srjm/values-secrets.yaml`, ignorado pelo Git:

```yaml
secrets:
  create: true
  postgresPassword: "SUBSTITUIR"
  dataEncryptionKey: "SUBSTITUIR"
  administratorCreationToken: "SUBSTITUIR"
  databaseUrl: "" # Vazio gera jdbc:postgresql://postgres:5432/<postgres.database>.
  mailUsername: ""
  mailPassword: ""
```

Acrescente `-f helm/banco-srjm/values-secrets.yaml` à instalação. Valores sensíveis
fazem parte dos dados da release Helm; prefira gestão externa quando disponível.
Mudar o Secret não altera a senha de um PostgreSQL já inicializado.

## Atualizações e compatibilidade

A versão 0.3.0 muda o padrão de Deployments para Knative. Não faça upgrade de uma
release convencional sem planejar a migração: os tipos de recursos de
frontend/backend mudam. Para manter temporariamente o modo antigo, defina
`knative.enabled=false` e `certManager.enabled=false`.

Os templates convencionais continuam disponíveis para compatibilidade. Os valores
de gateway desse modo apontam para namespace `istio` e selector `istio: ingress`.
No modo Knative, esses valores de gateway não são usados.

Mudanças nos ConfigMaps de runtime ou Secrets gerenciados pelo Helm alteram
checksums dos templates Knative e geram novas revisões. Secrets externos exigem
uma alteração explícita no template para garantir nova revisão. Fixar o tráfego
em uma revisão antiga impede que novas revisões recebam tráfego automaticamente.

O chart preserva a StorageClass com política Helm `keep` e usa `Retain` nos
volumes. Alterações de armazenamento exigem planejamento de expansão/migração;
não representam migração automática dos dados.

A validação compara o render Helm com os manifests públicos de `k8s/`, sem exigir
os arquivos locais de Secrets referenciados pelo Kustomize. Metadados de ownership,
checksums e defaults equivalentes são normalizados. Também testa namespace
alternativo, revisão fixa, Secrets customizados e o modo convencional.
