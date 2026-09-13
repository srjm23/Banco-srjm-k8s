# Manifests, ordem e selectors

> Atualização: foram preparados três charts independentes para banco, backend e frontend, preservando `k8s/`. Os pacotes, índice e instruções de adoção estão em [Helm e Argo CD](../helm/README.md). A consolidação abaixo descreve a etapa anterior.

`k8s/` é a única definição da aplicação. Foram retirados o chart Helm alternativo, seus values de exemplo e seis manifests de `k8s/legacy/` que repetiam frontend/backend e rotas. Helm permanece para os charts oficiais da plataforma. Os seis Secrets locais de migração foram movidos para `.secrets/manifestos-anteriores/`, fora do apply e ignorados pelo Git.

A limpeza retirou 45 arquivos redundantes. O arquivo `svc-postgress-head.yaml` foi renomeado para `svc-postgres-headless.yaml`; o recurso continua chamado `postgres-headless`. O alias `overlays/knative` permanece porque apenas aponta para a base e não duplica definições.

## Ordem FIFO

Todos os Kustomizations usam `sortOptions.order: fifo`. O principal inclui, nesta ordem:

1. Namespace da aplicação.
2. Namespace Vault, emissores, certificados internos e ServiceAccount administrativa.
3. Service Classic ELB, Service do gateway local e KnativeServing.
4. StorageClass e ConfigMaps da aplicação.
5. CA pública, ServiceAccounts leitoras, ClusterSecretStores e ExternalSecrets.
6. ClusterIssuer Let's Encrypt.
7. Services PostgreSQL, headless e Mailpit.
8. StatefulSet PostgreSQL e Deployment Mailpit.
9. Certificate público.
10. Backend e frontend Knative.
11. ClusterDomainClaim e DomainMapping.

São 36 recursos renderizados. A ordem não espera readiness. Em um ambiente novo, instale os controllers/CRDs, inicialize o Vault e espere os Secrets serem sincronizados antes de subir os consumidores. Os comandos estão no [guia de instalação](arquitetura-e-instalacao.md).

## Selectors

| Recurso | Selector / referência atual | Por quê |
| --- | --- | --- |
| Service `istio-ingress-classic` | `app: istio-ingress`, `istio: ingress` | Seleciona os pods do gateway instalado por Helm |
| Service `knative-local-gateway` | Mesmos labels, namespace `istio-ingress` | Services só selecionam pods no próprio namespace |
| Gateways externo e local gerenciados pelo KnativeServing | Mesmos labels | Substituem o selector antigo `istio: ingressgateway` que não correspondia aos pods |
| Services `postgres` e `postgres-headless` | `app: postgres` | Selecionam o StatefulSet; cumprem funções diferentes |
| Service `mailpit` | `app: mailpit` | Seleciona o Deployment de SMTP |
| Frontend/backend | Selectors gerados pelo Knative para cada revisão | Não manter Services/Deployments manuais concorrentes |

As correções do Istio ocorreram na recuperação anterior. Nesta limpeza, nenhum selector ou template da aplicação foi alterado. O Service ClusterIP `istio-ingress` pertence ao chart oficial e foi mantido. O Classic ELB e o gateway local expõem os mesmos pods com finalidades/portas distintas; não são três gateways separados.

## Verificação

```sh
python3 scripts/validate-manifests.py
kubectl --context eks-new apply --dry-run=server -k k8s
```

O script valida um recurso por arquivo, todas as referências do Kustomize, ausência de identidades repetidas, equivalência do alias, rotas, selectors, referências de configuração/credenciais, stores isolados e TLS. Também foi comparada a renderização antes/depois da limpeza: os 36 recursos e sua ordem são idênticos. A limpeza não exigiu reaplicar esses recursos. Durante a conferência do cluster, o Vault foi desbloqueado após a recriação de seu pod; esse procedimento operacional está registrado no guia de arquitetura.
