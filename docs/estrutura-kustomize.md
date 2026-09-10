# Estrutura dos manifests e ordem de aplicação

Cada arquivo em `k8s/` contém um recurso Kubernetes. Os templates YAML do
chart Helm também geram, no máximo, um recurso por arquivo. Os comentários
foram removidos do código e dos arquivos de configuração; as explicações
ficam na documentação. O shebang Python foi mantido por ser a instrução de
execução do script. Os documentos de perfil Spring em `application.yaml`
continuam juntos: são configuração da aplicação, não manifests Kubernetes.

## Arquivos separados

| Conteúdo anterior | Arquivos atuais |
| --- | --- |
| ConfigMaps de variáveis | `postgres-config.yaml`, `backend-config.yaml` |
| ConfigMaps de arquivos | `frontend-nginx.yaml`, `backend-application.yaml` |
| Certificado e domínio | `certificate.yaml`, `cluster-domain-claim.yaml`, `domain-mapping.yaml` |
| Mailpit | `mailpit.yaml`, `svc-mailpit.yaml` |
| Integração Istio/Knative | `platform/knative-serving.yaml`, `platform/knative-local-gateway.yaml` |
| Entrada pública | `platform/istio-ingress-classic.yaml` |

No Helm, Services foram separados dos Deployments/StatefulSet. Também foram
separados os Secrets, ConfigMaps, Certificate/ClusterIssuer,
ClusterDomainClaim/DomainMapping e Gateway/VirtualService. As condições de
habilitação do chart foram preservadas. `_helpers.tpl` calcula os checksums
usando os novos templates, mantendo a atualização das revisões quando a
configuração muda.

## Ordem no Kustomize

`k8s/kustomization.yaml`, `k8s/platform/kustomization.yaml` e o alias
`overlays/knative/kustomization.yaml` usam `sortOptions.order: fifo` para
preservar a ordem de `resources` na saída renderizada:

1. Namespace da aplicação.
2. Plataforma: Service Classic ELB, Service interno e KnativeServing.
3. StorageClass e ConfigMaps.
4. Secrets e ClusterIssuer.
5. Services internos do PostgreSQL e Mailpit.
6. StatefulSet PostgreSQL e Deployment Mailpit.
7. Certificate.
8. Service Knative backend e Service Knative frontend.
9. ClusterDomainClaim e DomainMapping.

A ordem organiza o envio ao servidor, mas não aguarda readiness entre os
recursos. Antes do apply, Istio, Knative Operator, cert-manager, EBS CSI e
suas CRDs precisam estar instalados, assim como os namespaces `istio-ingress`,
`knative-serving` e `cert-manager`. Os ajustes Helm da plataforma estão
descritos em [Istio e Classic ELB](istio-aws-classic.md).

```sh
kubectl --context eks-new apply --dry-run=server -k k8s
kubectl --context eks-new apply -k k8s
kubectl --context eks-new -n knative-serving wait --for=condition=Ready knativeserving/knative-serving --timeout=300s
kubectl --context eks-new -n banco-srjm rollout status statefulset/postgres --timeout=300s
kubectl --context eks-new -n banco-srjm wait --for=condition=Ready ksvc/backend ksvc/frontend --timeout=600s
kubectl --context eks-new -n banco-srjm wait --for=condition=Ready certificate/banco-srjm domainmapping/bancosrjm.geradorqrcode-srjm.uk --timeout=600s
```

O comando completo inclui a plataforma; `kubectl apply -k k8s/platform`
atualiza somente os três recursos de integração. Os Secrets locais continuam
ignorados pelo Git e precisam existir para renderizar o Kustomization completo.

## Selectors corrigidos na recuperação do cluster

Os pods do gateway instalado no namespace `istio-ingress` têm os labels
`app: istio-ingress` e `istio: ingress`. As correções anteriores foram
preservadas nesta reorganização:

| Recurso | Antes | Configuração atual |
| --- | --- | --- |
| Gateway `knative-serving/knative-ingress-gateway` | `istio: ingressgateway` | `app: istio-ingress` e `istio: ingress` |
| Gateway `knative-serving/knative-local-gateway` | `istio: ingressgateway` | `app: istio-ingress` e `istio: ingress` |
| Service usado como gateway local | Service em `istio-system`, com `istio: ingressgateway` | Service em `istio-ingress`, com `app: istio-ingress` e `istio: ingress` |

O Service local precisa estar no namespace dos pods, pois selectors de Service
não selecionam pods de outro namespace. O Service antigo em `istio-system`
não é a referência usada pelo Knative neste fluxo. O Service externo Classic
ELB também usa os dois labels corretos, sem mudança de selector nesta etapa.

Em `platform/knative-serving.yaml`, o operador mantém os selectors dos
Gateways e as referências efetivas do `config-istio`:

- Externo: `istio-ingress-classic.istio-ingress.svc.cluster.local`.
- Local: `knative-local-gateway.istio-ingress.svc.cluster.local`.

O fluxo permanece Classic ELB → Istio Gateway → VirtualService gerado pelo
Knative → frontend → backend → PostgreSQL. Frontend e backend usam o
queue-proxy do Knative sem sidecar Istio; PostgreSQL continua em StatefulSet.

## Validação e efeito da reorganização

Foram verificados o lint Helm, a paridade dos recursos, seis combinações de
values, um recurso por manifesto/template, a correspondência entre selectors
e a ordem real renderizada pelo Kustomize. Os valores dos Secrets foram
preservados. Os Kustomizations completos renderizam 25 recursos; a plataforma
isolada renderiza três.

A reorganização não foi aplicada ao cluster. Os checksums dos manifests de
frontend/backend foram atualizados para refletir os templates separados;
o próximo apply pode gerar novas revisões Knative, sem mudar imagens, portas
ou recursos de CPU/memória da aplicação.
