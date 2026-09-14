# Instalar a aplicação pelo Argo CD com Helm

As três Applications utilizam os charts publicados em `https://srjm23.github.io/Banco-srjm-k8s/`, com sincronização manual e destino no próprio cluster do Argo CD, namespace `banco-srjm`.

| Application | Chart | Versão |
| --- | --- | --- |
| [banco](applications/banco.yaml) | `banco-srjm-banco` | `1.0.0` |
| [backend](applications/backend.yaml) | `banco-srjm-backend` | `1.0.0` |
| [frontend](applications/frontend.yaml) | `banco-srjm-frontend` | `1.0.0` |

## Pré-requisitos

Argo CD e as dependências da aplicação precisam estar instalados: Istio, Knative, armazenamento EBS, cert-manager, Vault e External Secrets. Os stores devem estar Ready, as credenciais disponíveis no Vault e os pacotes publicados. Consulte o [roteiro da plataforma](../README.md).

Execute os comandos na raiz do projeto, usando o contexto Kubernetes atual. O domínio padrão dos charts é `bancosrjm.geradorqrcode-srjm.uk`.

**Se a aplicação já foi instalada pelo Helm CLI:** o Argo passará a gerenciar os mesmos recursos. Preserve os valores usados na instalação anterior, revise os diffs e não execute `helm uninstall`. Após a adoção, atualize pelo Argo, sem aplicar os mesmos recursos por Helm CLI ou Kustomize. Não utilize Prune, Force ou Replace na primeira sincronização; preserve o PostgreSQL e seu PVC.

## 1. Criar as Applications

```bash
kubectl apply -f argocd/applications/banco.yaml
kubectl apply -f argocd/applications/backend.yaml
kubectl apply -f argocd/applications/frontend.yaml
```

Esses comandos cadastram as Applications. Os recursos da aplicação serão aplicados durante a sincronização.

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

Abra **backend**, confira o diff e execute **Sync → Synchronize**.

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

Abra **frontend**, confira o diff e execute **Sync → Synchronize**.

```bash
kubectl -n banco-srjm wait \
  --for=condition=Ready \
  ksvc/frontend \
  certificate/banco-srjm \
  domainmapping/bancosrjm.geradorqrcode-srjm.uk \
  --timeout=600s
```

A ordem é **banco → backend → frontend**. As sync-waves ordenam recursos dentro de uma Application; não ordenam essas três Applications independentes. Se alguma etapa falhar, resolva antes de continuar.

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

Para atualizar a aplicação, publique uma nova versão do chart, altere `spec.source.targetRevision` na Application, aplique o arquivo atualizado e sincronize. Para alterar o domínio, configure `spec.source.helm.parameters` com `domain.host` no frontend e `config.FRONTEND_URL` no backend, além de revisar o emissor DNS-01 e a Cloudflare. Consulte os [values dos charts](../helm/README.md).
