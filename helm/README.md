# Helm da aplicação e da plataforma

A aplicação possui três charts independentes para as Applications `banco`, `backend` e `frontend` do Argo CD. A pasta `k8s/` foi preservada integralmente como alternativa Kustomize e referência de paridade. Escolha apenas um gerenciador para cada recurso no cluster.

| Application / release | Chart | Recursos padrão |
| --- | --- | --- |
| banco | `charts/banco-srjm-banco` | PostgreSQL StatefulSet, dois Services, ConfigMap e ExternalSecret da senha |
| backend | `charts/banco-srjm-backend` | Service Knative, ConfigMap, dois ExternalSecrets e Mailpit opcional com Service |
| frontend | `charts/banco-srjm-frontend` | Service Knative, ConfigMap Nginx, Certificate, ClusterDomainClaim e DomainMapping |

São 16 recursos de aplicação sem sobreposição entre os charts. Os nomes `postgres`, `postgres-config`, `backend` e `frontend` foram mantidos para preservar referências. Cada chart suporta uma instalação por namespace; mudar o nome da release não renomeia os workloads. Os selectors do PostgreSQL permanecem `app: postgres`, compatíveis com o StatefulSet existente.

## Pré-requisitos compartilhados

Instale a plataforma uma única vez: AWS Controller, Istio, Classic ELB, Knative, cert-manager, EBS CSI, Vault e External Secrets. Os charts da aplicação reutilizam `vault-banco`, `letsencrypt-production` e `banco-ebs-gp3`. Não recriam ClusterSecretStores, ClusterIssuer, token Cloudflare ou gateways. O guia da plataforma está em [arquitetura e instalação](../docs/arquitetura-e-instalacao.md).

O Vault precisa estar inicializado e desbloqueado, com dados nos caminhos `secret/banco-srjm/postgres-secret`, `secret/banco-srjm/backend-secret` e `secret/banco-srjm/backend-application`. O Secret do arquivo Spring é sincronizado do Vault; o pacote não contém o arquivo com credenciais.

O store atual só permite namespace `banco-srjm`. Para outro namespace, adapte também suas condições e políticas Vault, além dos values dos charts. Os três charts foram renderizados e testados em namespace alternativo, mas isso não concede acesso ao Vault automaticamente. Ao mudar o domínio do frontend, ajuste também `config.FRONTEND_URL` nos values do backend.

## Validar, renderizar, empacotar e gerar índice

Na raiz do projeto:

```sh
python3 scripts/package-helm.py
```

O script executa lint estrito, valida paridade/referências, renderiza, empacota, compara pacote e fonte e verifica os digests do índice. Os comandos Helm equivalentes são:

```sh
helm lint helm/charts/banco-srjm-banco helm/charts/banco-srjm-backend helm/charts/banco-srjm-frontend --strict
helm template banco helm/charts/banco-srjm-banco -n banco-srjm --output-dir build/helm-rendered
helm template backend helm/charts/banco-srjm-backend -n banco-srjm --output-dir build/helm-rendered
helm template frontend helm/charts/banco-srjm-frontend -n banco-srjm --output-dir build/helm-rendered
helm package helm/charts/banco-srjm-banco --destination helm/repository
helm package helm/charts/banco-srjm-backend --destination helm/repository
helm package helm/charts/banco-srjm-frontend --destination helm/repository
helm repo index helm/repository --url https://srjm23.github.io/Banco-srjm-k8s/
```

Artefatos prontos:

- `helm/repository/banco-srjm-banco-1.0.0.tgz`
- `helm/repository/banco-srjm-backend-1.0.0.tgz`
- `helm/repository/banco-srjm-frontend-1.0.0.tgz`
- `helm/repository/index.yaml`
- `build/helm-rendered/`: um arquivo por recurso renderizado, ignorado pelo Git.

O repositório Helm configurado é **https://srjm23.github.io/Banco-srjm-k8s/**. O índice usa URLs absolutas para esse endereço e `scripts/package-helm.py` o utiliza por padrão. A geração local não publica os arquivos. Aumente `version` em Chart.yaml antes de publicar alterações em uma versão já distribuída.

Para publicar na raiz desse endereço:

1. Envie os charts, pacotes, índice e workflow ao GitHub.
2. Em **Settings → Pages → Build and deployment → Source**, selecione **GitHub Actions**.
3. Em **Actions → Publicar repositório Helm → Run workflow**, execute a publicação manual na branch que contém esses arquivos.

O workflow `.github/workflows/publish-helm-pages.yaml` publica o conteúdo de `helm/repository/` como raiz do site. Isso disponibiliza `/Banco-srjm-k8s/index.yaml`, sem acrescentar `/helm/repository/` à URL. Ele publica os pacotes já gerados; não reconstrói charts. Regenere-os antes de publicar alterações. Consulte [workflows do GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

Depois da publicação:

```sh
helm repo add banco-srjm https://srjm23.github.io/Banco-srjm-k8s/
helm repo update banco-srjm
helm search repo banco-srjm --versions
```

## Applications no Argo CD

Os exemplos estão em `argocd/applications/banco.yaml`, `backend.yaml` e `frontend.yaml`, um Application por arquivo. Eles usam `repoURL: https://srjm23.github.io/Banco-srjm-k8s/`, `chart` por componente e `targetRevision: 1.0.0`, com sincronização manual. Publique os pacotes no Pages antes de sincronizar; estes arquivos não foram aplicados ao cluster.

```sh
kubectl --context eks-new apply -f argocd/applications/banco.yaml
kubectl --context eks-new apply -f argocd/applications/backend.yaml
kubectl --context eks-new apply -f argocd/applications/frontend.yaml
```

O Argo CD usa Helm para renderizar os charts e controla a aplicação dos recursos; não cria uma release visível em `helm list`. Não é necessário plugin de Kustomize para usar estes charts. Veja [Helm no Argo CD](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/).

As três Applications já consomem o repositório Helm publicado. Elas não usam `source.path` ou `targetRevision: HEAD`. Para uma nova versão, publique o novo pacote/índice e atualize `targetRevision` na Application correspondente.

Sincronize nesta ordem: **banco → backend → frontend**. Espere o ExternalSecret e PostgreSQL ficarem prontos antes do backend. As annotations de sync-wave ordenam recursos dentro de uma Application; não ordenam três Applications independentes. O frontend usa o backend no mesmo namespace por padrão.

Os exemplos habilitam `FailOnSharedResource=true` e não habilitam auto-sync/prune. O StatefulSet PostgreSQL declara `Prune=false,Delete=false` para Argo CD e `helm.sh/resource-policy: keep` para Helm, preservando-o na remoção da aplicação/release. Seus dados também dependem do PVC existente: não exclua/recrie o banco para resolver ownership. Não use Force/Replace na adoção do StatefulSet.

## Uso direto do Helm

Em um namespace novo, com os pré-requisitos e credenciais preparados:

```sh
helm --kube-context eks-new upgrade --install banco helm/repository/banco-srjm-banco-1.0.0.tgz -n banco-srjm --create-namespace --wait --timeout 10m
helm --kube-context eks-new upgrade --install backend helm/repository/banco-srjm-backend-1.0.0.tgz -n banco-srjm --wait --timeout 10m
helm --kube-context eks-new upgrade --install frontend helm/repository/banco-srjm-frontend-1.0.0.tgz -n banco-srjm --wait --timeout 10m
kubectl --context eks-new -n banco-srjm wait --for=condition=Ready ksvc/backend ksvc/frontend --timeout=600s
```

No cluster atual, os recursos já existem e foram aplicados por Kustomize. A migração para Helm CLI exige adoção de ownership; não foi executada nesta preparação. Para a migração planejada ao Argo CD, revise os diffs e sincronize os recursos existentes, preservando os nomes e o PVC. Deixe de aplicar a mesma aplicação com Kustomize depois da adoção.

O primeiro sync de backend/frontend altera as anotações de checksum e pode criar novas revisões Knative. As imagens continuam com as tags atuais por padrão. A validação de renderização/dry-run não equivale a uma instalação real.

## Values principais

| Campo | Charts | Uso |
| --- | --- | --- |
| `image.repository`, `tag`, `digest`, `pullPolicy` | Todos | Imagem; digest tem precedência sobre tag |
| `resources`, `imagePullSecrets` | Todos | CPU/memória e registry |
| `externalSecrets.enabled`, `storeName`, `pathPrefix`, `refreshInterval` | Banco/backend | Sincronização do Vault; prefixo vazio usa o namespace |
| `secrets.*Name` | Banco/backend | Nomes dos Secrets consumidores; desabilite ExternalSecrets se já forem gerenciados externamente |
| `database` | Banco | Dados não sensíveis de postgres-config |
| `database.configMapName` | Backend | ConfigMap do banco, declarado pela Application banco |
| `persistence.storageClassName`, `size` | Banco | PVC; não altera automaticamente disco existente |
| `storageClass.create` | Banco | False por padrão; crie a classe apenas se não houver outro responsável |
| `config` | Backend | Configurações comuns; nunca use este campo para credenciais |
| `mailpit.enabled` | Backend | SMTP de teste; ao desabilitar, configure SMTP externo em config/Vault |
| `knative.minScale`, `maxScale`, `containerConcurrency`, `traffic` | Backend/frontend | Escala e roteamento de revisões |
| `configVersion` | Backend/frontend | Altere para criar revisão após mudança de credenciais externas |
| `backend.serviceName`, `namespace`, `clusterDomain`, `dnsResolver` | Frontend | Destino e resolução DNS internos |
| `domain.enabled`, `host`, `createClaim` | Frontend | Domínio público e sua reserva no Knative |
| `tls.createCertificate`, `secretName`, `issuerRef` | Frontend | Certificado ou reutilização de Secret TLS existente |

Mudanças nos ConfigMaps de cada chart alteram o checksum do respectivo Service Knative. Mudanças no Secret externo ou no ConfigMap do banco, gerenciado pela outra Application, não alteram automaticamente o template do backend: atualize `configVersion` quando precisar recarregar suas variáveis. Alterar a senha do Secret PostgreSQL não muda a senha de um banco já inicializado.

## Values da plataforma

Os arquivos `values-aws-load-balancer-controller-classic.yaml`, `values-istiod-eks.yaml`, `values-istio-gateway-eks.yaml`, `values-vault-eks.yaml` e `values-external-secrets.yaml` continuam em `helm/` para os charts oficiais. Eles não entram nos três pacotes da aplicação.

## Validação realizada

Os três charts passaram em `helm lint --strict`. Foram conferidos os 16 recursos padrão, a paridade funcional com `k8s/`, ausência de sobreposição, referências, namespace alternativo, imagens por digest e alterações de checksum. Os pacotes renderizam os mesmos recursos dos charts e seus digests SHA-256 correspondem ao index.

O servidor EKS aceitou o dry-run dos 16 recursos renderizados e das três Applications. Todos os arquivos de `k8s/` permaneceram idênticos byte a byte. Nenhum chart/Application foi instalado, nenhum recurso vivo foi alterado e os pacotes ainda não foram publicados.
