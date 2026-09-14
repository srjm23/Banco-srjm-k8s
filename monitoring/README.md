# Prometheus, Kiali e Grafana — instalação e integração

Prometheus coleta e armazena métricas. Kiali consulta a API do Prometheus para exibir tráfego e saúde da malha Istio. Grafana permite visualizar métricas em dashboards quando configurado com uma fonte de dados Prometheus. O fluxo é **proxies Istio → coleta Prometheus → consulta pelo Kiali e Grafana**.

Os comandos utilizam o contexto Kubernetes atual, sem variáveis de ambiente. Instale na ordem **Prometheus → Kiali → integração**. Se os componentes já existem, confira suas releases e configurações antes de atualizar.

## 1. Pré-requisitos

- Helm e kubectl com acesso ao cluster.
- Istio instalado em `istio-system` e seus proxies operacionais.
- EBS CSI e StorageClass `banco-ebs-gp3`, utilizados pelo PVC do Prometheus.
- Capacidade disponível nos nodes para os novos componentes.

```bash
helm list -n monitoring
helm list -n kiali-operator
kubectl -n istio-system get pods
kubectl get storageclass banco-ebs-gp3
```

O Kiali utiliza o Operator `2.31.0`, conforme a configuração adotada neste projeto. O comando Prometheus utiliza a versão disponível no repositório; para reprodução exata, registre a versão instalada em `helm list` e utilize `--version` nas próximas instalações.

## 2. Adicionar os repositórios

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add kiali https://kiali.org/helm-charts
helm repo update prometheus-community kiali
```

## 3. Instalar o Prometheus

Configuração: namespace `monitoring`, PVC EBS de 10 GiB, retenção de sete dias, coleta a cada 15 segundos e Service interno. Alertmanager, Pushgateway, node-exporter e kube-state-metrics ficam desabilitados para reduzir os componentes instalados.

```bash
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --create-namespace \
  --set server.persistentVolume.storageClass=banco-ebs-gp3 \
  --set server.persistentVolume.size=10Gi \
  --set server.retention=7d \
  --set server.global.scrape_interval=15s \
  --set alertmanager.enabled=false \
  --set prometheus-pushgateway.enabled=false \
  --set prometheus-node-exporter.enabled=false \
  --set kube-state-metrics.enabled=false \
  --wait --timeout 10m

kubectl -n monitoring get pods,svc,pvc
```

Espere os pods ficarem Ready e o PVC Bound. A retenção de sete dias não garante que o volume comporte qualquer carga de métricas; acompanhe seu uso de disco.

## 4. Instalar o Kiali

O chart instala o Operator em `kiali-operator` e cria o recurso Kiali em `istio-system`. A autenticação utiliza token Kubernetes.

```bash
helm upgrade --install kiali-operator kiali/kiali-operator \
  --namespace kiali-operator \
  --create-namespace \
  --version 2.31.0 \
  --set cr.create=true \
  --set cr.namespace=istio-system \
  --set cr.spec.auth.strategy=token \
  --wait --timeout 10m

kubectl -n kiali-operator get pods
kubectl -n istio-system get kiali,pods,svc
```

O `--wait` do Helm aguarda os recursos gerenciados pelo chart; a criação do servidor Kiali pelo Operator pode continuar depois. Confirme que o pod e o Service `kiali` estão disponíveis antes de acessar.

## 5. Conectar o Kiali ao Prometheus

Este é o procedimento utilizado para atualizar a integração, preservando os values existentes da release:

```bash
helm upgrade kiali-operator kiali/kiali-operator \
  --namespace kiali-operator \
  --version 2.31.0 \
  --reuse-values \
  --set cr.create=true \
  --set cr.namespace=istio-system \
  --set cr.spec.external_services.prometheus.enabled=true \
  --set-string cr.spec.external_services.prometheus.url=http://prometheus-server.monitoring.svc.cluster.local:80 \
  --wait --timeout 10m
```

Use a URL pura no comando, sem a sintaxe Markdown `[endereço](endereço)`. Os underscores de `external_services` também são literais, sem barras de escape.

O endereço é interno ao cluster: Service `prometheus-server`, namespace `monitoring`, porta `80`. Não utiliza ELB, Cloudflare ou o endereço do port-forward.

Confira a configuração declarada:

```bash
kubectl -n istio-system get kiali \
  -o jsonpath='{range .items[*]}{.metadata.name}{": "}{.spec.external_services.prometheus.url}{"\n"}{end}'

helm list -n monitoring
helm list -n kiali-operator
```

Configurar a URL permite a consulta pelo Kiali, mas não garante que o Prometheus esteja coletando as métricas do Istio. Valide a coleta na próxima etapa.

## 6. Acessar e validar o Prometheus

Mantenha este terminal aberto:

```bash
kubectl -n monitoring port-forward svc/prometheus-server 9090:80
```

Abra **http://localhost:9090**. Confira os alvos em **Status → Target health**. Gere tráfego na aplicação e consulte:

```promql
istio_requests_total
```

Para testar a API de consulta em outro terminal:

```bash
curl -fsSG http://localhost:9090/api/v1/query \
  --data-urlencode 'query=istio_requests_total'
```

Uma resposta com `result: []` significa ausência de séries para essa consulta. Confira os alvos, suas anotações de scrape e a existência de tráfego nos proxies. Uma conexão bem-sucedida com a API não comprova a coleta de telemetria Istio.

## 7. Acessar o Kiali e obter o token

Em outro terminal, mantenha o encaminhamento aberto:

```bash
kubectl -n istio-system port-forward svc/kiali 20001:20001
```

Abra **http://localhost:20001**. Para a ServiceAccount padrão criada pelo Kiali:

```bash
kubectl -n istio-system get serviceaccount kiali
kubectl -n istio-system create token kiali --duration=1h
```

Copie o token somente para o campo **Token** da tela de login. Ele utiliza as permissões dessa ServiceAccount; não o publique nem o salve no Git. Quando expirar, gere outro.

Selecione os namespaces relevantes e uma janela de tempo com tráfego para visualizar o grafo.

## 8. Limites da observabilidade neste projeto

Frontend/backend são Services Knative com injeção de sidecar Istio desabilitada. A telemetria Istio vem principalmente dos gateways; o `queue-proxy` pertence ao Knative. Não espere um grafo completo de todas as chamadas internas ou do PostgreSQL sem instrumentação correspondente.

Prometheus e Kiali não habilitam tracing distribuído automaticamente. Instalar esses componentes também não altera o roteamento da aplicação.

## 9. Instalar o Grafana

O Grafana utiliza o namespace `monitoring`, Service `ClusterIP` e volume persistente de 5 GiB com a StorageClass `banco-ebs-gp3`. O comando reúne a instalação e a configuração de armazenamento utilizadas no projeto:

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update grafana

helm upgrade --install grafana grafana/grafana \
  -n monitoring \
  --create-namespace \
  --set persistence.enabled=true \
  --set persistence.storageClassName=banco-ebs-gp3 \
  --set persistence.size=5Gi \
  --set service.type=ClusterIP
```

Para uma release existente, o procedimento de atualização utilizado foi:

```bash
helm upgrade grafana grafana/grafana \
  -n monitoring \
  --reuse-values \
  --set persistence.enabled=true \
  --set persistence.storageClassName=banco-ebs-gp3 \
  --set persistence.size=5Gi
```

A StorageClass de um PVC existente não pode ser alterada por esse upgrade. Se o PVC já foi criado com outra classe, será necessário planejar a migração dos dados.

```bash
kubectl -n monitoring get pods,svc,pvc
kubectl -n monitoring port-forward svc/grafana 3000:80
```

Abra **http://localhost:3000**. Para consultar as credenciais geradas pelo chart padrão, execute em outro terminal:

```bash
kubectl -n monitoring get secret grafana -o jsonpath='{.data.admin-user}' | base64 --decode; echo
kubectl -n monitoring get secret grafana -o jsonpath='{.data.admin-password}' | base64 --decode; echo
```

No Grafana, adicione uma fonte de dados do tipo **Prometheus**, informe `http://prometheus-server.monitoring.svc.cluster.local:80` e clique em **Save & test**. A instalação acima não provisiona automaticamente essa fonte nem os dashboards do Istio.

## 10. Integrar o Grafana ao Kiali

```bash
helm upgrade kiali-operator kiali/kiali-operator \
  -n kiali-operator \
  --version 2.31.0 \
  --reuse-values \
  --set cr.spec.external_services.grafana.enabled=true \
  --set-string cr.spec.external_services.grafana.internal_url=http://grafana.monitoring.svc.cluster.local
```

`internal_url` é o endereço utilizado pelo Kiali dentro do cluster. Essa configuração preserva os values existentes, incluindo a integração com o Prometheus, mas não configura a fonte de dados do Grafana nem importa dashboards. Se houver autenticação na API do Grafana, configure também as credenciais de integração no Kiali.

Para links do Kiali abrirem o Grafana no navegador, configure `external_url` com um endereço acessível pelo usuário. No acesso local, mantenha o port-forward do Grafana ativo e execute:

```bash
helm upgrade kiali-operator kiali/kiali-operator \
  -n kiali-operator \
  --version 2.31.0 \
  --reuse-values \
  --set-string cr.spec.external_services.grafana.external_url=http://localhost:3000
```

## Referências

- [Chart Prometheus](https://github.com/prometheus-community/helm-charts/tree/main/charts/prometheus).
- [Instalação Helm do Kiali](https://kiali.io/docs/installation/installation-guide/install-with-helm/).
- [Integração Kiali e Prometheus](https://kiali.io/docs/configuration/p8s-jaeger-grafana/prometheus/).
- [Autenticação por token](https://kiali.io/docs/configuration/authentication/token/).
- [Instalação da aplicação](../README.md).
