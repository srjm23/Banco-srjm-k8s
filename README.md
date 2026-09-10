# Banco SRJM — EKS, Knative, Istio e Let's Encrypt

A pasta **`k8s/` é a configuração principal com Knative**. Para instalar a aplicação, após configurar os requisitos abaixo:

```sh
kubectl apply -k k8s
```

Cada manifesto Kubernetes contém um único recurso. O Kustomization inclui:

- `platform/`: Service Classic ELB, Service interno do gateway e configuração KnativeServing.
- `backend.yaml` e `frontend.yaml`: Services Knative, com escala de 1 a 3 réplicas.
- `certificate.yaml`, `cluster-domain-claim.yaml` e `domain-mapping.yaml`: certificado e domínio público.
- `postgres.yaml`: StatefulSet com PVC de 20 GiB; `svc-postgres.yaml` e `svc-postgress-head.yaml`: Services do banco.
- `storageclass.yaml`: EBS gp3 criptografado, com política Retain.
- `mailpit.yaml` e `svc-mailpit.yaml`: Deployment e Service SMTP interno de testes.
- `postgres-config.yaml`, `backend-config.yaml`, `frontend-nginx.yaml` e `backend-application.yaml`: ConfigMaps separados.
- `namespace.yaml`: namespace `banco-srjm`, com injeção de sidecar desabilitada.
- Secrets locais e `letsencrypt-production.yaml`: credenciais e emissor DNS-01 Cloudflare.

A ordem usa `sortOptions.order: fifo`: namespace → plataforma → StorageClass →
ConfigMaps → Secrets → emissor → Services internos → PostgreSQL/Mailpit →
certificado → backend → frontend → claim → DomainMapping.

Essa é a ordem de envio dos recursos; Kustomize não espera readiness entre eles.
Os controllers e suas CRDs devem existir antes do apply. Confira o
[guia da estrutura e dos selectors](docs/estrutura-kustomize.md).

`k8s/legacy/` guarda os antigos Deployments/Services e Gateway manual, **fora do Kustomization**. Não aplique essa pasta junto com Knative. `overlays/knative` é apenas um alias para `k8s/`.

## Preparar antes do apply

1. Instale/configure Knative Serving, DomainMapping, Knet-Istio, cert-manager e EBS CSI com IAM adequado. O Kustomization configura o KnativeServing existente e solicita o Classic ELB; não instala os charts dos controllers. Configure `enableServiceMutatorWebhook=false` conforme [o guia AWS](docs/istio-aws-classic.md). O PostgreSQL EBS requer nós EC2 compatíveis; não é destinado a Fargate.
2. O ClusterIssuer `letsencrypt-production` entra no Kustomization com DNS-01 Cloudflare. O Secret `cloudflare-api-token-secret`, no namespace `cert-manager`, fornece o token da zona. Veja [Istio e Let’s Encrypt](docs/istio-letsencrypt.md).
3. O domínio `bancosrjm.geradorqrcode-srjm.uk` já está configurado no claim, DomainMapping, certificado e `FRONTEND_URL`. Crie o registro DNS desse subdomínio apontando para o LoadBalancer Knet-Istio. O cert-manager cria e renova o Secret TLS **no namespace `banco-srjm`**.
4. Os Secrets locais `k8s/postgres-secret.yaml` e `k8s/backend-secret.yaml` já estão incluídos no Kustomization. Eles foram extraídos dos valores do `application.yaml` e estão ignorados pelo Git. Revise-os antes de produção: valores padrão de desenvolvimento foram preservados, não substituídos por credenciais novas. Em um clone novo, prepare os arquivos a partir dos exemplos e preencha as credenciais:

   ```sh
   cp k8s/postgres-secret.example.yaml k8s/postgres-secret.yaml
   cp k8s/backend-secret.example.yaml k8s/backend-secret.yaml
   chmod 600 k8s/postgres-secret.yaml k8s/backend-secret.yaml
   ```

   Não sobrescreva arquivos locais já preenchidos. O backend usa a mesma senha do PostgreSQL via `secretKeyRef`; suas demais credenciais vêm de `backend-secret`. O `application.yaml` não contém mais fallbacks para essas credenciais. Preserve a chave de criptografia ao migrar dados.
5. Para EKS Auto Mode, altere `provisioner` da StorageClass para `ebs.csi.eks.amazonaws.com`. Para usar uma classe existente, ajuste `storageClassName` no StatefulSet e remova `storageclass.yaml` da lista de recursos.
6. Confira as imagens, arquitetura dos nós e acesso ao registry. Fixe tags/digests para releases reproduzíveis. As imagens devem conter assets JS/CSS, Actuator e migrações Flyway; não há Dockerfiles ou código completo neste repositório.

## Validar e aplicar

A partir da raiz do repositório:

```sh
kubectl config current-context
kubectl apply -f k8s/namespace.yaml
kubectl kustomize k8s > /tmp/banco-srjm-rendered.yaml
kubectl apply --dry-run=server -f /tmp/banco-srjm-rendered.yaml
kubectl apply -k k8s
kubectl -n banco-srjm rollout status statefulset/postgres --timeout=300s
kubectl -n banco-srjm wait --for=condition=Ready ksvc/backend ksvc/frontend --timeout=600s
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s
kubectl -n banco-srjm get ksvc,domainmapping,certificate,pods,svc,pvc
```

Confirme também `DomainMapping` Ready e teste HTTPS, redirecionamento HTTP, assets, login e operações da API. Para ver o Mailpit: `kubectl -n banco-srjm port-forward svc/mailpit 8025:8025` e acesse `http://localhost:8025`.

Os dois Secrets são aplicados pelo próprio `kubectl apply -k k8s`. A renderização contém credenciais: evite publicar ou versionar o YAML renderizado. Os arquivos `.example.yaml` não entram no apply.

## Operação e limites

- O Nginx encaminha `/api/` para `backend.banco-srjm.svc.cluster.local:80`, usando o Host interno exigido pelo Knative. A porta do container permanece 8080; Knative gerencia a porta do Service e as réplicas.
- Escala: edite `autoscaling.knative.dev/min-scale` e `max-scale` em backend/frontend. Use mínimo zero se aceitar cold starts. PostgreSQL e Mailpit não têm autoscaling. Escala de nós depende de Karpenter/Cluster Autoscaler/Auto Mode.
- A aplicação não usa sidecar neste perfil e pressupõe HTTP interno. Readiness/liveness do backend usam `/api/actuator/health/...` e precisam estar liberadas sem autenticação na imagem. Nginx usa `/healthz`.
- Flyway faz retries de conexão na inicialização; Hibernate valida o schema. Banco novo não importa dados do volume Docker: planeje backup/restauração e confirme a versão real do PostgreSQL da imagem.
- A StorageClass usa Retain. PVC/disco preservados continuam gerando custos; não há alta disponibilidade ou backup automático. Mudar a senha no Secret não altera a senha de um banco já inicializado.
- Mailpit captura e-mails de teste sem entrega real e sem persistência. Configure SMTP real nas variáveis/Secrets quando necessário. Tracing Spring e exportadores OTEL ficam desabilitados sem collector.
- Alterações em ConfigMaps/Secrets não criam por si só uma nova revisão Knative. Após alterá-los, mude uma anotação em `spec.template.metadata.annotations` de backend/frontend (por exemplo, `config-version`) para publicar nova revisão. Não reinicie manualmente os Deployments gerenciados pelo Knative.
- `apply` não remove Deployments/Services de uma instalação convencional anterior. Havendo instalação existente, planeje a migração/ownership sem excluir o PVC. O fluxo acima pressupõe instalação nova.

## Helm e validação local

O chart continua em [helm/banco-srjm](helm/banco-srjm). Para Knative use `helm/values-knative.example.yaml`, seguindo o [guia](docs/knative-letsencrypt.md); não misture Helm e Kustomize no mesmo namespace.

```sh
python3 scripts/validate-manifests.py
```

Requer Python/PyYAML, kubectl e Helm. Valida renderização e referências localmente; não faz deploy nem substitui dry-run do servidor e testes reais.

## Istio e balanceador AWS

Para o **Classic ELB**, use o manifesto único [istio-ingress-classic.yaml](k8s/platform/istio-ingress-classic.yaml),
com descoberta automática de subnets. Os pré-requisitos do controller e os
comandos estão em [Istio com Classic ELB](docs/istio-aws-classic.md).
Aplicado e validado no contexto `eks-new`: frontend/backend Knative prontos,
VirtualServices gerados pelo Knative, PostgreSQL em StatefulSet e HTTPS pelo
Classic ELB retornando 200. O hostname e a configuração Cloudflare estão no guia.
