# Certificado HTTPS e Cloudflare

O cert-manager usa o ClusterIssuer de `k8s/letsencrypt-production.yaml` para emitir certificados Let's Encrypt por DNS-01. Ele lê a chave `api-token` do Secret `cert-manager/cloudflare-api-token-secret`, sincronizado do Vault pelo ExternalSecret de mesmo nome.

O token permite ao cert-manager criar e remover o TXT temporário de validação `_acme-challenge.bancosrjm.geradorqrcode-srjm.uk`. Ele não é usado pelo frontend, pelo Istio ou pelo Classic ELB para atender requisições. O registro CNAME da aplicação é configurado separadamente na Cloudflare. Para o solver, limite o token à zona necessária, com permissões Zone DNS Edit e Zone Read, conforme a [documentação do cert-manager](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/).

`k8s/certificate.yaml` solicita o certificado do domínio e o cert-manager gera o Secret `banco-srjm-tls` em `banco-srjm`. `k8s/domain-mapping.yaml` associa esse Secret TLS ao domínio e ao frontend. A integração Knative/Istio configura o gateway para servir o certificado.

Com proxy Cloudflare, existem duas conexões TLS: navegador → Cloudflare e Cloudflare → Istio, passando pelo Classic ELB TCP. Configure Full (strict), que valida o certificado da origem. O teste público confirmou `server: cloudflare` e HTTPS 200; isso não revela sozinho o modo SSL escolhido no painel. Veja [Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/).

```sh
kubectl --context eks-new get clusterissuer letsencrypt-production
kubectl --context eks-new -n cert-manager get externalsecret cloudflare-api-token-secret
kubectl --context eks-new -n banco-srjm get certificate,domainmapping
kubectl --context eks-new -n banco-srjm get orders,challenges
curl -I https://bancosrjm.geradorqrcode-srjm.uk/
curl https://bancosrjm.geradorqrcode-srjm.uk/api/actuator/health
```

A emissão usa DNS-01; os exemplos antigos de HTTP-01 e os manifests de Secret com token literal foram retirados do fluxo. Veja o [guia completo](arquitetura-e-instalacao.md) e [Vault](vault-external-secrets.md).
