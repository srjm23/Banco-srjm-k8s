# Migração para DNS-01

O projeto usa DNS-01 na Cloudflare. O ClusterIssuer está em `k8s/letsencrypt-production.yaml`; o token vem do Vault por `k8s/external-secrets/cloudflare-api-token-secret.yaml`.

A configuração anterior de HTTP-01 e seus values de exemplo não fazem parte da aplicação atual. O frontend/backend são Knative e suas rotas são geradas automaticamente. Não é necessário criar Ingress manual para o desafio ACME.

Os comandos atuais estão em [TLS e Cloudflare](istio-letsencrypt.md). A instalação de todos os componentes está no [guia de arquitetura](arquitetura-e-instalacao.md).
