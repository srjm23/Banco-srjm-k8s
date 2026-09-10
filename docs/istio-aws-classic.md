# Classic ELB para o Istio

A configuração de entrada está em `k8s/platform/istio-ingress-classic.yaml`: um Service
`LoadBalancer` sem `loadBalancerClass`, sem anotações NLB e sem IDs de subnets.
O controller legado AWS solicita o Classic ELB público e encaminha TCP 80/443
para os pods existentes do Istio. O TLS permanece no Istio/Knative.

Este fluxo usa o **Istio Gateway existente**. `istio-ingress-classic` é somente
o nome do Service de exposição; não é outro gateway nem outro Deployment.

Fluxo: Cloudflare → Classic ELB → NodePorts dos nós EKS → Istio → aplicação.

## Descoberta automática de subnets

Nas subnets públicas elegíveis da VPC do cluster, configure a tag recomendada:

```text
kubernetes.io/role/elb = 1
```

Elas precisam ter rota para o Internet Gateway e endereços disponíveis.
O controller legado também pode identificar subnets públicas pela tabela de
rotas; a AWS recomenda identificá-las explicitamente com a tag de função.
Os nós estarem em subnets públicas não substitui essas verificações nem as
permissões IAM do controller. Nenhum ID de subnet fica fixado no manifesto.

## Preparar o controller

O AWS Load Balancer Controller injeta `service.k8s.aws/nlb` nos novos Services
LoadBalancer. Para permitir Classic ELB, a opção documentada pela AWS é
`enableServiceMutatorWebhook=false` nos values da release desse controller.
Isso altera o padrão para novos Services sem classe em todo o cluster;
Services NLB devem declarar explicitamente sua classe. O controller continua
instalado para gerenciar NLB/ALB existentes.

Confira a versão instalada antes do upgrade:

```sh
helm --kube-context eks-new list -n kube-system --filter '^aws-load-balancer-controller$'
helm repo add eks https://aws.github.io/eks-charts
helm repo update eks
```

Na consulta anterior, o chart instalado era `aws-load-balancer-controller-3.5.0`.
Se a versão mudou, substitua `3.5.0` abaixo pela versão instalada. Preserve essa
opção também nos values usados por futuros upgrades/GitOps do controller.

```sh
helm --kube-context eks-new upgrade aws-load-balancer-controller eks/aws-load-balancer-controller \
  --namespace kube-system --version 3.5.0 --reuse-values \
  -f helm/values-aws-load-balancer-controller-classic.yaml --wait --timeout 5m
```

## Integrar o Istio Gateway ao Knative

Aplique a configuração da plataforma, mantida pelo operador Knative:

```sh
kubectl --context eks-new apply -k k8s/platform
```

O manifesto `k8s/platform/knative-serving.yaml` ajusta os selectors dos Gateways para `app: istio-ingress` e
`istio: ingress`, referencia o Service Classic externo e referencia o Service
`knative-local-gateway`, definido em `k8s/platform/knative-local-gateway.yaml`,
no mesmo namespace dos pods do gateway. Esse Service
interno encaminha 80 → 8081 e 443 → 8444, sem exposição pública.

O Knative cria e reconcilia os VirtualServices das revisões e do DomainMapping.
Não crie um VirtualService manual apontando para um Deployment fixo: frontend
e backend continuam sendo Services Knative, com seus respectivos queue-proxies.
PostgreSQL continua em StatefulSet, com seu PVC e Service internos.

A injeção de sidecar nos workloads da aplicação permanece desabilitada. O
injector do Istiod permanece habilitado para o template `gateway`, usado pelo
Deployment Helm do Istio Gateway. Expor o ELB ou cadastrar DNS na Cloudflare
não exige sidecars nas aplicações.

## Validar e aplicar

O gateway Istio deve existir no namespace `istio-ingress`, com os labels
`app: istio-ingress` e `istio: ingress`. Não é instalado por este manifesto.
Após configurar o controller, valide o Service no servidor:

```sh
kubectl --context eks-new apply --dry-run=server -f k8s/platform/istio-ingress-classic.yaml -o yaml
```

O resultado precisa ter `type: LoadBalancer` e **não** conter
`spec.loadBalancerClass`. Se aparecer uma classe, corrija a seleção de controller
antes de aplicar. Não existe `loadBalancerClass: classic`.

```sh
kubectl --context eks-new apply -f k8s/platform/istio-ingress-classic.yaml
kubectl --context eks-new -n istio-ingress get svc istio-ingress-classic -w
kubectl --context eks-new -n istio-ingress describe svc istio-ingress-classic
kubectl --context eks-new -n istio-ingress get svc istio-ingress-classic \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}{"\n"}'
```

O Service faz parte de `k8s/platform/kustomization.yaml`, incluído pelo
Kustomization principal de `k8s/`. A release Helm do gateway mantém seu Service
ClusterIP. Não é necessário bootstrap NodePort nem patch posterior; reaplicar
o manifesto preserva o tipo LoadBalancer.

## AWS e Cloudflare

Quando provisionado, encontre o recurso em **EC2 → Load Balancers**, tipo
**classic**, na região **Ohio (us-east-2)**. O hostname gerado pela AWS pode ser
usado como destino do CNAME de `bancosrjm.geradorqrcode-srjm.uk` na Cloudflare.
Listeners e propriedades controladas pelo Kubernetes devem ser configurados
pelo Service, pois alterações manuais podem ser reconciliadas.

## Estado validado em 10/09/2026

Aplicado no contexto `eks-new`:

- Classic ELB criado com descoberta automática de subnets.
- Frontend e backend na revisão `00002`, ambos Ready e pods 2/2 Running.
- PostgreSQL 1/1 Running; backend conectado e migrações Flyway concluídas.
- DomainMapping e Certificate Ready; VirtualServices gerados pelo Knative.
- HTTPS pelo ELB: frontend 200 e `/api/actuator/health` 200 com `status: UP`.
- Certificado validado pelo cliente TLS, sem opção de ignorar certificado.
- Nginx validado com `nginx -t`.
- API AWS `elb describe-load-balancers` confirmou Classic ELB internet-facing,
  TCP 80/443, e duas subnets descobertas automaticamente.
- Os dois nós registrados no Classic ELB estão `InService`.
- Service antigo `istio-ingress` agora é ClusterIP; release Helm do gateway
  está deployed na revisão 3 e não solicita mais NLB.

Hostname gerado:

```text
ad9260bd1a3f64eeea48e9dcd11746af-1296708679.us-east-2.elb.amazonaws.com
```

Na Cloudflare, configure CNAME `bancosrjm` para esse hostname. Se usar proxy
Cloudflare, use SSL/TLS **Full (strict)**. O DNS não foi alterado nesta execução.

Para repetir a validação sem depender do DNS Cloudflare:

```sh
curl --noproxy '*' --connect-to bancosrjm.geradorqrcode-srjm.uk:443:ad9260bd1a3f64eeea48e9dcd11746af-1296708679.us-east-2.elb.amazonaws.com:443 \
  https://bancosrjm.geradorqrcode-srjm.uk/api/actuator/health
```

O backend anterior não foi agendado por insuficiência de recursos. O Istiod
reservava 2 GiB e usava cerca de 37 MiB; seus requests foram ajustados para
100m/512Mi por `helm/values-istiod-eks.yaml`. Monitore e amplie os recursos à
medida que a carga crescer. O frontend agora resolve o DNS do backend durante
as requisições, com cache de 10 segundos, evitando falha de inicialização
quando o Service Knative backend ainda não foi criado.

Para preservar os ajustes das releases instaladas:

```sh
helm --kube-context eks-new upgrade istiod istio/istiod -n istio-system \
  --version 1.31.0 --reuse-values -f helm/values-istiod-eks.yaml --wait
helm --kube-context eks-new upgrade istio-ingress istio/gateway -n istio-ingress \
  --version 1.31.0 --reuse-values -f helm/values-istio-gateway-eks.yaml --wait
```

O Service original do gateway passa a ClusterIP; o Service Classic é a única
entrada pública desejada. Os Gateways/VirtualServices convencionais estão em
`k8s/legacy/` e não são aplicados junto ao Knative. O template Helm de Istio
atende ao modo Deployment opcional, sem duplicar as rotas geradas pelo Knative.

## Referências

- [AWS: controller legado e enableServiceMutatorWebhook](https://docs.aws.amazon.com/eks/latest/userguide/aws-load-balancer-controller.html)
- [AWS: identificação e descoberta de subnets](https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html)
- [Knative: configuração dos gateways pelo operador](https://knative.dev/docs/install/operator/configuring-serving-cr/)
- [Cloudflare: Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)
