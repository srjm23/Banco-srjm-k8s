# Instalar a aplicação pelo Argo CD com Helm

O Application pai [banco-srjm-apps](root-application.yaml) acompanha a pasta `argocd/applications` na branch `main` do GitHub e sincroniza automaticamente os Applications filhos. Frontend e backend possuem sincronização automática com `prune` e `selfHeal`; o banco mantém sincronização manual.

Os três Applications filhos utilizam os charts publicados em `https://srjm23.github.io/Banco-srjm-k8s/`, com destino no próprio cluster do Argo CD, namespace `banco-srjm`. O pai fica fora da pasta monitorada para não gerenciar a si mesmo. A remoção de Applications pelo pai não é automática (`prune` desabilitado).

| Application | Chart | Versão |
| --- | --- | --- |
| [banco](applications/banco.yaml) | `banco-srjm-banco` | `1.0.0` |
| [backend](applications/backend.yaml) | `banco-srjm-backend` | `1.0.0` |
| [frontend](applications/frontend.yaml) | `banco-srjm-frontend` | `1.0.0` |

## Pré-requisitos

Argo CD e as dependências da aplicação precisam estar instalados: Istio, Knative, armazenamento EBS, cert-manager, Vault e External Secrets. Os stores devem estar Ready, as credenciais disponíveis no Vault e os pacotes publicados. Consulte o [roteiro da plataforma](../README.md).

Execute os comandos na raiz do projeto, usando o contexto Kubernetes atual. O domínio padrão dos charts é `bancosrjm.geradorqrcode-srjm.uk`.

**Se a aplicação já foi instalada pelo Helm CLI:** o Argo passará a gerenciar os mesmos recursos. Preserve os valores usados na instalação anterior, revise os diffs e não execute `helm uninstall`. Após a adoção, atualize pelo Argo, sem aplicar os mesmos recursos por Helm CLI ou Kustomize. Não utilize Prune, Force ou Replace na primeira sincronização; preserve o PostgreSQL e seu PVC.

## 1. Ativar o App of Apps

Publique primeiro os arquivos no GitHub, pois o pai consulta o conteúdo remoto:

```bash
git add argocd/root-application.yaml argocd/applications/frontend.yaml argocd/applications/backend.yaml argocd/README.md
git commit -m "Configura App of Apps e sincronizacao automatica"
git push origin main

kubectl apply -f argocd/root-application.yaml
kubectl -n argocd get applications
```

O apply do pai é necessário apenas na ativação inicial ou quando sua própria configuração mudar. Depois, alterações nos YAML dos filhos publicadas na branch `main` são reconciliadas automaticamente. Os nomes existentes são preservados. O pai atualiza o Application do banco, mas a sincronização dos recursos do banco continua manual.

Frontend e backend podem começar a sincronizar assim que forem cadastrados; o pai não garante a prontidão do banco antes deles. Em um cluster novo, prepare o banco conforme a etapa 3 e acompanhe a recuperação dos serviços.

## 2. Acessar o Argo CD

Mantenha o terminal aberto:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443
```

Abra **https://localhost:8080**. Use o usuário `admin` e sua senha atual. Em uma instalação inicial, consulte a senha em outro terminal:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath='{.data.password}' | base64 --decode
printf '\n'
```

A senha inicial pode já ter sido alterada ou removida. O certificado padrão do Argo é autoassinado.

## 3. Sincronizar o banco

No painel, abra **banco → App Diff**, confira as alterações e selecione **Sync → Synchronize**, sem marcar Prune, Force ou Replace.

```bash
kubectl -n banco-srjm wait \
  --for=condition=Ready externalsecret/postgres-secret \
  --timeout=180s

kubectl -n banco-srjm rollout status statefulset/postgres \
  --timeout=300s
```

Avance somente quando o Secret e o PostgreSQL estiverem prontos. O StatefulSet mantém o nome `postgres` e reutiliza o PVC `data-postgres-0`, quando existente no mesmo namespace.

## 4. Sincronizar o backend

O backend sincroniza automaticamente. Abra **backend** para acompanhar o diff e o resultado da sincronização.

```bash
kubectl -n banco-srjm wait \
  --for=condition=Ready \
  externalsecret/backend-secret \
  externalsecret/backend-application \
  --timeout=180s

kubectl -n banco-srjm wait \
  --for=condition=Ready ksvc/backend \
  --timeout=600s
```

## 5. Sincronizar o frontend

O frontend sincroniza automaticamente. Abra **frontend** para acompanhar o diff e o resultado da sincronização.

```bash
kubectl -n banco-srjm wait \
  --for=condition=Ready \
  ksvc/frontend \
  certificate/banco-srjm \
  domainmapping/bancosrjm.geradorqrcode-srjm.uk \
  --timeout=600s
```

A ordem de validação é **banco → backend → frontend**. O App of Apps não estabelece uma dependência de prontidão entre esses serviços. Se alguma etapa falhar, resolva antes de continuar a validação.

## 6. Validar

```bash
kubectl -n argocd get applications

kubectl -n banco-srjm get \
  ksvc,pods,pvc,externalsecret,certificate,domainmapping

curl -fsS https://bancosrjm.geradorqrcode-srjm.uk/api/actuator/health
```

Confira sincronização das Applications, condições Ready dos recursos, PVC Bound e endpoint de saúde com `status: UP`.

## Atualizações e responsabilidade dos recursos

O Argo utiliza Helm para renderizar os charts e gerencia diretamente os recursos Kubernetes. Não cria novas releases em `helm list`. Releases antigas do Helm CLI podem continuar listadas, mas não devem ser usadas para atualizar, reverter ou remover os recursos após a adoção. [Helm no Argo CD](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/).

Para atualizar apenas a imagem, altere `spec.source.helm.valuesObject.image` no Application correspondente e publique no GitHub. Exemplo do frontend:

```yaml
helm:
  releaseName: frontend
  valuesObject:
    image:
      repository: srjm2024/banco-srjm-frontend
      tag: latest-1.1.0
      digest: ""
```

```bash
git add argocd/applications/frontend.yaml
git commit -m "Atualiza imagem do frontend"
git push origin main
```

O pai detecta a alteração no Git e atualiza o filho; o filho renderiza o Helm com os novos values e sincroniza o Service Knative, criando uma revisão quando o template muda. Não é necessário outro apply nem publicar um novo chart para alterar apenas a imagem pelos values. A detecção depende do intervalo de reconciliação do Argo CD; não é instantânea. Sobrescrever uma tag no registry não altera o Git nem dispara esse fluxo.

Para atualizar o chart, publique uma nova versão e altere `spec.source.targetRevision` no filho pelo Git. O banco ainda exige Sync manual. Para alterar o domínio, configure os values `domain.host` no frontend e `config.FRONTEND_URL` no backend, além de revisar o emissor DNS-01 e a Cloudflare. Consulte os [values dos charts](../helm/README.md).
