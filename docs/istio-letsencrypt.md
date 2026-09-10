# Let's Encrypt DNS-01 com Cloudflare no Istio

O emissor `k8s/letsencrypt-production.yaml` agora usa **DNS-01 com Cloudflare** para validação de domínio, funcionando com Istio Gateway e Knative. A validação ocorre via DNS records, não via HTTP, eliminando dependência de HTTP-01 Ingress.

## Vantagens de DNS-01

- ✅ Funciona com qualquer tipo de Gateway (Istio, Knative, etc)
- ✅ Não requer acesso HTTP público temporário
- ✅ Pode validar wildcards (`*.dominio.com`)
- ✅ Mais robusto e seguro
- ✅ Não depende de IngressClass ou configuração de Ingress

## Pré-requisitos

- **cert-manager** instalado no cluster (1.12+)
- **Cloudflare** como provedor DNS da zona `geradorqrcode-srjm.uk`
- **API Token Cloudflare** com permissão para editar DNS records
- DNS público apontando para o LoadBalancer do Istio/Knative

## Configuração

### 1. Secret do Cloudflare (já criado)

```yaml
# k8s/cloudflare-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-api-token-secret
  namespace: cert-manager
type: Opaque
stringData:
  api-token: YOUR_CLOUDFLARE_API_TOKEN
```

**Nota importante**: Este arquivo contém credenciais sensíveis. Adicione ao `.gitignore` ou use sealed-secrets em produção.

### 2. ClusterIssuer com DNS-01

O `k8s/letsencrypt-production.yaml` agora configura:

```yaml
solvers:
  - selector:
      dnsNames:
        - bancosrjm.geradorqrcode-srjm.uk
        - '*.geradorqrcode-srjm.uk'
    dns01:
      cloudflare:
        email: srjm99silva@gmail.com
        apiTokenSecretRef:
          name: cloudflare-api-token-secret
          key: api-token
```

Sem necessidade de Ingress ou IngressClass.

## Aplicar e verificar

```sh
# Aplicar manifests
kubectl apply -k k8s

# Aguardar ClusterIssuer estar pronto
kubectl wait --for=condition=Ready clusterissuer/letsencrypt-production --timeout=120s

# Monitorar Certificate
kubectl -n banco-srjm get certificate
kubectl -n banco-srjm describe certificate banco-srjm

# Se demorar, verifique Order e Challenge
kubectl -n banco-srjm get order,challenge
kubectl -n banco-srjm describe order
kubectl -n banco-srjm describe challenge

# Aguardar Certificate pronto
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s

# Validar Secret TLS gerado
kubectl -n banco-srjm get secret banco-srjm-tls -o json | jq '.data."tls.crt"' | base64 -d | openssl x509 -text -noout
```

## Fluxo de validação DNS-01

1. cert-manager cria um recurso `Order` com os domínios
2. Let's Encrypt retorna um `Challenge` com dados DNS
3. cert-manager usa a API Cloudflare para criar um registro TXT temporário
4. Let's Encrypt valida o DNS TXT
5. Após sucesso, cert-manager remove o TXT e emite o certificado
6. Certificado é salvo em `Secret banco-srjm-tls` no namespace `banco-srjm`

## Troubleshooting

### Certificate fica "Pending"

```sh
# Verifique o Challenge
kubectl -n banco-srjm describe challenge

# Comum: API Token inválido ou sem permissões
# Solução: Gere novo token em Account Settings > API Tokens com permissão de editar DNS

# Verificar logs do cert-manager
kubectl -n cert-manager logs -l app.kubernetes.io/name=cert-manager --tail=100
```

### DNS TXT não criado automaticamente

```sh
# Verifique as credenciais Cloudflare
kubectl -n cert-manager get secret cloudflare-api-token-secret -o jsonpath='{.data.api-token}' | base64 -d

# Teste acesso à API Cloudflare:
curl -X GET "https://api.cloudflare.com/client/v4/user" \
  -H "X-Auth-Email: srjm99silva@gmail.com" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"
```

### Certificate com domínios não encontrados

```sh
# Verify SANs no Certificate
kubectl -n banco-srjm get certificate banco-srjm -o jsonpath='{.spec.dnsNames}'

# Se faltar wildcard ou subdomain, edite certificate.yaml e reaplique
```

## Segurança

- **NÃO commite credenciais** no Git. Use:
  - Sealed Secrets ou External Secrets
  - Git crypt
  - `.gitignore` com backup seguro

Em produção:
```sh
# Exemplo com External Secrets
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-backend
spec:
  provider:
    vault:
      server: "https://vault.example.com"
      path: "secret"
```

## Próximas etapas

1. ✅ Certificado emitido pelo Let's Encrypt (prod)
2. ✅ Salvo em `banco-srjm-tls` Secret
3. ✅ DomainMapping do Knative referencia esse Secret
4. ✅ Istio Gateway expõe HTTPS automaticamente

Teste acesso:
```sh
# HTTP → HTTPS (redirect)
curl -I https://bancosrjm.geradorqrcode-srjm.uk

# Verificar certificado
openssl s_client -connect bancosrjm.geradorqrcode-srjm.uk:443 -showcerts
```

## Referências

- [cert-manager DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/)
- [Cloudflare DNS API](https://developers.cloudflare.com/api/)
- [Knative Custom Domains + TLS](https://knative.dev/docs/serving/services/custom-domains/)
