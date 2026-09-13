# Knative e Let's Encrypt

A aplicação usa os manifests únicos de `k8s/`. O chart alternativo da aplicação foi removido para evitar manutenção duplicada.

`certificate.yaml` solicita o certificado, `cluster-domain-claim.yaml` reserva o domínio para o namespace e `domain-mapping.yaml` associa domínio, frontend e Secret TLS. O Knative gera o roteamento Istio correspondente.

Consulte [certificado e Cloudflare](istio-letsencrypt.md), [Knative no projeto](../k8s/README.md) e [instalação da plataforma](arquitetura-e-instalacao.md).
