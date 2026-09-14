# Manifestos Kubernetes — função e importância

Esta pasta contém **34 recursos e quatro Kustomizations**, com um recurso por arquivo YAML. Frontend/backend usam Knative; PostgreSQL usa StatefulSet. Os manifestos permanecem como alternativa Kustomize e referência dos charts Helm.

**Use um gerenciador por recurso.** Se banco, backend e frontend são gerenciados pelo Argo CD/Helm, não aplique a base inteira com `kubectl apply -k k8s`. Os charts já incluem os 16 recursos da aplicação; plataforma, stores e emissor são dependências compartilhadas.

## Aplicação

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [namespace.yaml](namespace.yaml) | Namespace | Cria `banco-srjm` e desabilita a injeção automática de sidecar Istio. Organiza os recursos da aplicação. |
| [backend.yaml](backend.yaml) | Service Knative | Executa a API Spring Boot, com escala, revisões, probes e consumo de Secrets/ConfigMaps. `cluster-local` mantém o backend interno. |
| [backend-config.yaml](backend-config.yaml) | ConfigMap | Armazena parâmetros comuns do backend, como SMTP, URL do frontend e opções Spring, separados das credenciais. |
| [frontend.yaml](frontend.yaml) | Service Knative | Executa o frontend Nginx com recursos, escala e configuração montada. Knative gerencia as revisões e a rede. |
| [frontend-nginx.yaml](frontend-nginx.yaml) | ConfigMap | Configura o Nginx para servir a interface e encaminhar `/api/` ao backend pela rede interna. |
| [mailpit.yaml](mailpit.yaml) | Deployment | Executa o capturador de e-mails de teste. Não entrega mensagens a destinatários externos. |
| [svc-mailpit.yaml](svc-mailpit.yaml) | Service | Fornece endereço interno estável para SMTP `1025` e interface web `8025` do Mailpit. |

Os Services de frontend/backend pertencem à API `serving.knative.dev/v1`: controlam execução, revisões e roteamento. Os arquivos `svc-*.yaml` são Services Kubernetes comuns, que fornecem acesso de rede aos pods.

## PostgreSQL e armazenamento

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [postgres.yaml](postgres.yaml) | StatefulSet | Executa uma instância PostgreSQL e solicita PVC de 20 GiB por `volumeClaimTemplates`. Preserva identidade e armazenamento entre recriações do pod. |
| [postgres-config.yaml](postgres-config.yaml) | ConfigMap | Define banco, usuário e diretório de dados. A senha vem de `postgres-secret`. |
| [svc-postgres.yaml](svc-postgres.yaml) | Service | Disponibiliza o endpoint interno `postgres:5432` para os clientes do banco. |
| [svc-postgres-headless.yaml](svc-postgres-headless.yaml) | Service headless | Com `clusterIP: None`, fornece identidade DNS aos pods do StatefulSet, sem IP virtual de Service. |
| [storageclass.yaml](storageclass.yaml) | StorageClass | Define provisionamento EBS gp3 criptografado via CSI, expansão, `WaitForFirstConsumer` e retenção `Retain`. É utilizada por PostgreSQL e Vault. |

`StorageClass` define como provisionar; `PVC` solicita armazenamento; `PV/EBS` representa o volume provisionado. Não há YAML separado de PVC porque o StatefulSet o solicita. Retenção não substitui backup, e alterar o Secret não altera a senha de um banco já inicializado.

## Domínio e certificado público

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [letsencrypt-production.yaml](letsencrypt-production.yaml) | ClusterIssuer | Configura conta ACME, e-mail e autenticação DNS-01 Cloudflare. Define como emitir os certificados. |
| [certificate.yaml](certificate.yaml) | Certificate | Solicita o certificado do domínio e o Secret TLS `banco-srjm-tls`; cert-manager cuida da emissão e renovação. |
| [cluster-domain-claim.yaml](cluster-domain-claim.yaml) | ClusterDomainClaim | Reserva o uso do domínio pelo namespace `banco-srjm` no Knative. Não cria registros DNS. |
| [domain-mapping.yaml](domain-mapping.yaml) | DomainMapping | Associa o domínio ao frontend, referencia o Secret TLS e configura redirecionamento HTTP para HTTPS. |

O CNAME é configurado separadamente na Cloudflare, apontando para o Classic ELB. O token DNS-01 serve para criar/remover os TXT de validação, não para encaminhar tráfego.

## `platform/` — gateway e Knative

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [istio-ingress-classic.yaml](platform/istio-ingress-classic.yaml) | Service LoadBalancer | Expõe os pods do gateway por TCP 80/443. Em EKS com suporte legado, solicita o Classic ELB sem classe ou anotação NLB. |
| [knative-local-gateway.yaml](platform/knative-local-gateway.yaml) | Service ClusterIP | Dá acesso ao gateway das rotas Knative internas, usado no caminho do frontend ao backend. |
| [knative-serving.yaml](platform/knative-serving.yaml) | KnativeServing | Instrui o Operator a reconciliar Serving/net-istio e configura os gateways externo e local. |
| [kustomization.yaml](platform/kustomization.yaml) | Kustomization | Agrupa os três recursos na ordem de envio. |

O provedor AWS legado de Services cria o Classic ELB; o AWS Load Balancer Controller não cria Classic. O TLS termina no Istio. Os selectors dos Services e gateways são `app: istio-ingress` e `istio: ingress`; os Services ficam no namespace dos pods, `istio-ingress`.

Knative gera as rotas Istio, Deployments e Services de suas revisões. Não copie esses objetos gerados como manifests adicionais.

## `external-secrets/` — credenciais

Fluxo: **Vault → External Secrets Operator → Secret Kubernetes → consumidor**. Os YAMLs descrevem caminhos e autenticação; não contêm os valores das credenciais.

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [vault-ca.yaml](external-secrets/vault-ca.yaml) | ConfigMap | Contém a CA pública para o ESO validar o TLS do Vault. Em outro cluster, obtenha a CA daquela instalação. |
| [vault-banco-reader.yaml](external-secrets/vault-banco-reader.yaml) | ServiceAccount | Identidade Kubernetes utilizada na leitura das credenciais da aplicação. |
| [vault-cert-manager-reader.yaml](external-secrets/vault-cert-manager-reader.yaml) | ServiceAccount | Identidade separada para leitura do token Cloudflare. |
| [cluster-store-banco.yaml](external-secrets/cluster-store-banco.yaml) | ClusterSecretStore | Define conexão TLS e autenticação no Vault, permitindo consumidores em `banco-srjm`. |
| [cluster-store-cert-manager.yaml](external-secrets/cluster-store-cert-manager.yaml) | ClusterSecretStore | Define conexão com identidade própria e consumidores em `cert-manager`. |
| [postgres-secret.yaml](external-secrets/postgres-secret.yaml) | ExternalSecret | Sincroniza a senha utilizada pelo PostgreSQL e pelo backend. |
| [backend-secret.yaml](external-secrets/backend-secret.yaml) | ExternalSecret | Sincroniza variáveis sensíveis da API, incluindo sua URL de conexão. |
| [backend-application.yaml](external-secrets/backend-application.yaml) | ExternalSecret | Sincroniza `application.yaml`, montado pelo backend em `/etc/banco`. |
| [cloudflare-api-token-secret.yaml](external-secrets/cloudflare-api-token-secret.yaml) | ExternalSecret | Sincroniza o token DNS-01 no namespace cert-manager. |
| [kustomization.yaml](external-secrets/kustomization.yaml) | Kustomization | Agrupa CA, identidades, stores e os quatro ExternalSecrets utilizados. |

As condições dos stores limitam namespaces; as políticas Vault limitam os caminhos acessíveis. `creationPolicy: Orphan` e `deletionPolicy: Retain` preservam os Secrets nas situações previstas por essas políticas. Atualizar um Secret não recarrega automaticamente variáveis de pods existentes.

Os placeholders `frontend-secret` e `mailpit-secret` foram retirados porque nenhum workload os consome. A limpeza dos arquivos não remove os antigos objetos ou dados do Vault no cluster.

## `vault/` — TLS interno e administração

| Manifesto | Recurso | Função e importância |
| --- | --- | --- |
| [namespace.yaml](vault/namespace.yaml) | Namespace | Separa os recursos Vault e desabilita a injeção de sidecar Istio. |
| [selfsigned-issuer.yaml](vault/selfsigned-issuer.yaml) | Issuer | Inicia a cadeia de confiança emitindo a CA interna autoassinada. |
| [ca-certificate.yaml](vault/ca-certificate.yaml) | Certificate | Solicita a autoridade certificadora interna, com `isCA: true`. |
| [ca-issuer.yaml](vault/ca-issuer.yaml) | Issuer | Utiliza a CA interna para assinar o certificado do servidor. |
| [server-certificate.yaml](vault/server-certificate.yaml) | Certificate | Emite TLS para os nomes DNS internos do Vault e endereços locais declarados. |
| [admin-serviceaccount.yaml](vault/admin-serviceaccount.yaml) | ServiceAccount | Define a identidade administrativa Kubernetes. As permissões no Vault dependem de role e política configuradas separadamente. |
| [kustomization.yaml](vault/kustomization.yaml) | Kustomization | Ordena namespace, emissores, certificados e identidade administrativa. |

Essa pasta prepara o Vault; o servidor é instalado pelo chart oficial com `helm/values-vault-eks.yaml`. O perfil atual tem uma réplica e unseal manual. Consulte [configuração pela CLI](../docs/vault-cli.md).

## Kustomize, validação e instalação

O [kustomization.yaml principal](kustomization.yaml) reúne as subpastas e os recursos da aplicação. `sortOptions.order: fifo` preserva a sequência de envio, mas **não espera readiness nem instala controllers**.

Ordem das dependências: EKS/IAM/EBS CSI → cert-manager e Istio → Knative Operator/Serving → Vault/ESO → credenciais e emissor → banco → backend → frontend.

Para conferir a renderização local, sem alterar o cluster:

```bash
kubectl kustomize k8s
helm lint helm/charts/banco-srjm-banco helm/charts/banco-srjm-backend helm/charts/banco-srjm-frontend --strict
```

Com plataforma e credenciais prontas, **somente se optar pela gestão Kustomize**:

```bash
kubectl apply --dry-run=server -k k8s
kubectl apply -k k8s
```

Para o fluxo Helm/Argo, use o [README principal](../README.md), [Helm](../helm/README.md) e [Argo CD](../argocd/README.md). O antigo alias `overlays/knative` foi removido; a base Kustomize é `k8s/`.
