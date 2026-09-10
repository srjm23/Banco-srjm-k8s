# Migração: HTTP-01 → DNS-01 com Cloudflare

## Resumo das mudanças

✅ **Concluído**: Transição de HTTP-01 Ingress para DNS-01 com Cloudflare no cert-manager

### Arquivos modificados:
- `k8s/letsencrypt-production.yaml` — ClusterIssuer agora usa DNS-01
- `k8s/cloudflare-secret.yaml` — **NOVO** — Secret com API Token Cloudflare
- `k8s/kustomization.yaml` — Adicionado cloudflare-secret.yaml, removido istio-ingressclass.yaml
- `helm/values-knative.example.yaml` — Atualizado para usar ClusterIssuer DNS-01
- `docs/istio-letsencrypt.md` — Documentação atualizada
- `docs/knative-letsencrypt.md` — Documentação atualizada

## Por que DNS-01?

| Aspecto | HTTP-01 | DNS-01 |
|--------|---------|--------|
| **Validação** | Via `.well-known/acme-challenge/` HTTP | Via DNS TXT record |
| **Wildcard** | ❌ Não suporta | ✅ Suporta |
| **Gateway** | Requer Ingress + IngressClass | Funciona com qualquer Gateway |
| **Downtime** | Pode bloquear HTTP 80 | Sem impacto na aplicação |
| **Segurança** | Expõe desafio via HTTP | Apenas DNS admins |

## Pré-requisitos

```sh
# 1. cert-manager instalado
kubectl get deployment -n cert-manager cert-manager

# 2. Cloudflare configurado para geradorqrcode-srjm.uk
# 3. API Token com permissão de editar DNS
```

## Aplicar as mudanças

### Opção 1: Com Kustomize

```sh
# Validar manifests
python3 scripts/validate-manifests.py

# Dry-run
kubectl kustomize k8s > /tmp/banco-dns01.yaml
kubectl apply --dry-run=server -f /tmp/banco-dns01.yaml

# Aplicar
kubectl apply -k k8s
```

### Opção 2: Com Helm

```sh
# Preparar valores locais
cp helm/values-knative.example.yaml helm/values-knative.local.yaml

# Editar domínio se necessário (já está correto no exemplo)
# vim helm/values-knative.local.yaml

# Validar
helm lint helm/banco-srjm -f helm/values-knative.local.yaml

# Dry-run
helm template banco-srjm helm/banco-srjm \
  -n banco-srjm -f helm/values-knative.local.yaml > /tmp/banco-dns01.yaml
kubectl apply --dry-run=server -f /tmp/banco-dns01.yaml

# Aplicar
helm upgrade --install banco-srjm helm/banco-srjm \
  -n banco-srjm --create-namespace \
  -f helm/values-knative.local.yaml --wait
```

## Monitorar a emissão do certificado

```sh
# 1. Aguardar ClusterIssuer estar pronto
kubectl wait --for=condition=Ready clusterissuer/letsencrypt-production --timeout=120s

# 2. Monitorar Certificate
watch kubectl -n banco-srjm get certificate
kubectl -n banco-srjm describe certificate banco-srjm

# 3. Se demorar, verifique Order e Challenge
kubectl -n banco-srjm get order,challenge -o wide
kubectl -n banco-srjm describe order
kubectl -n banco-srjm describe challenge

# 4. Verificar logs do cert-manager
kubectl -n cert-manager logs -l app.kubernetes.io/name=cert-manager --tail=50 -f

# 5. Esperar Certificate pronto (Ready)
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s
```

## Validar o certificado

```sh
# Secret TLS foi criado
kubectl -n banco-srjm get secret banco-srjm-tls -o yaml

# Verificar dados do certificado
kubectl -n banco-srjm get secret banco-srjm-tls -o jsonpath='{.data."tls.crt"}' | base64 -d | openssl x509 -text -noout

# Deve mostrar:
# - Issuer: Let's Encrypt Production
# - Subject: bancosrjm.geradorqrcode-srjm.uk
# - Validity: válido por 90 dias
```

## Validar HTTPS

```sh
# Aguardar DomainMapping estar pronto
kubectl -n banco-srjm wait --for=condition=Ready domainmapping/bancosrjm.geradorqrcode-srjm.uk --timeout=300s

# Testar HTTPS
curl -I https://bancosrjm.geradorqrcode-srjm.uk/
# Esperado: HTTP/2 200 ou 301/302 (redirect HTTP→HTTPS)

# Verificar certificado TLS no navegador/openssl
openssl s_client -connect bancosrjm.geradorqrcode-srjm.uk:443 -showcerts < /dev/null

# Certificado deve ser de Let's Encrypt Production, válido para seu domínio
```

## Troubleshooting

### Certificate fica "Pending" por muito tempo

```sh
# 1. Verificar Challenge status
kubectl -n banco-srjm describe challenge

# 2. Verificar credenciais Cloudflare
kubectl -n cert-manager get secret cloudflare-api-token-secret -o jsonpath='{.data.api-token}' | base64 -d
echo ""  # Newline

# 3. Testar API Cloudflare
CLOUDFLARE_TOKEN="$(kubectl -n cert-manager get secret cloudflare-api-token-secret -o jsonpath='{.data.api-token}' | base64 -d)"
curl -X GET "https://api.cloudflare.com/client/v4/user" \
  -H "X-Auth-Email: srjm99silva@gmail.com" \
  -H "Authorization: Bearer ${CLOUDFLARE_TOKEN}" \
  -H "Content-Type: application/json"
# Esperado: status: success

# 4. Verificar zona DNS
curl -X GET "https://api.cloudflare.com/client/v4/zones?name=geradorqrcode-srjm.uk" \
  -H "X-Auth-Email: srjm99silva@gmail.com" \
  -H "Authorization: Bearer ${CLOUDFLARE_TOKEN}" \
  -H "Content-Type: application/json"
```

### API Token inválido ou sem permissões

```sh
# Gerar novo token em Cloudflare:
# 1. Ir para account.cloudflare.com
# 2. Account Settings > API Tokens
# 3. Create Token > Custom token
# 4. Permissões: Zone.DNS.Edit em sua zona
# 5. Copiar token
# 6. Atualizar Secret:

kubectl -n cert-manager delete secret cloudflare-api-token-secret
kubectl -n cert-manager create secret generic cloudflare-api-token-secret \
  --from-literal=api-token=YOUR_NEW_TOKEN

# Deletar Challenge para retentar
kubectl -n banco-srjm delete challenge -l certmanager.k8s.io/certificate-name=banco-srjm

# Certificate vai retentar automaticamente
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s
```

### DNS TXT não aparece em Cloudflare

```sh
# Verificar manualmente se cert-manager criou o TXT
dig _acme-challenge.bancosrjm.geradorqrcode-srjm.uk TXT

# Se não encontrar, verificar logs de cert-manager
kubectl -n cert-manager logs -l app.kubernetes.io/name=cert-manager -f | grep -i cloudflare

# Comuns: token expirado, falta permissão, zona ID incorreta
```

## Limpar antes de retentar (se necessário)

```sh
# ⚠️ Cuidado: só se algo der muito errado

# Deletar Order (força nova tentativa)
kubectl -n banco-srjm delete order -l certmanager.k8s.io/certificate-name=banco-srjm

# Deletar Challenge (força revalidação)
kubectl -n banco-srjm delete challenge -l certmanager.k8s.io/certificate-name=banco-srjm

# Certificado vai recriar tudo automaticamente
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s
```

## Segurança: Protegendo credenciais Cloudflare

### ⚠️ IMPORTANTE

O arquivo `k8s/cloudflare-secret.yaml` **contém credenciais sensíveis**.

**Adicione ao `.gitignore` IMEDIATAMENTE**:
```bash
echo "k8s/cloudflare-secret.yaml" >> .gitignore
git rm --cached k8s/cloudflare-secret.yaml
git commit -m "Remove Cloudflare secret from git history"
```

### Em Produção (Recomendado)

Use **External Secrets Operator** com Azure Key Vault:

```yaml
# k8s/external-secret-cloudflare.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: azure-keyvault
  namespace: cert-manager
spec:
  provider:
    azurekv:
      vaultUrl: https://your-keyvault.vault.azure.net/
      auth:
        workloadIdentity:
          serviceAccountRef:
            name: external-secrets-sa

---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: cloudflare-api-token-secret
  namespace: cert-manager
spec:
  secretStoreRef:
    name: azure-keyvault
    kind: SecretStore
  target:
    name: cloudflare-api-token-secret
    template:
      type: Opaque
  data:
  - secretKey: api-token
    remoteRef:
      key: cloudflare-api-token
```

Ou use **Sealed Secrets**:
```bash
kubeseal -f k8s/cloudflare-secret.yaml -w k8s/cloudflare-secret-sealed.yaml
# Commitar apenas cloudflare-secret-sealed.yaml
```

## Rollback (se necessário)

Se precisar voltar para HTTP-01:

```sh
# Restaurar letsencrypt-production.yaml anterior
git checkout HEAD~1 k8s/letsencrypt-production.yaml
git checkout HEAD~1 k8s/kustomization.yaml
git checkout HEAD~1 k8s/istio-ingressclass.yaml

# Aplicar
kubectl apply -k k8s

# Certificado será revalidado via HTTP-01 Ingress
```

## Próximas etapas

1. ✅ ClusterIssuer com DNS-01 Cloudflare
2. ✅ Secret Cloudflare em cert-manager
3. ✅ Certificate emitido automaticamente
4. ✅ DomainMapping/Istio Gateway + HTTPS
5. 🔄 Monitorar renovação automática (a cada 60 dias)

```sh
# Verificar data de expiração
kubectl -n banco-srjm get secret banco-srjm-tls -o jsonpath='{.data."tls.crt"}' | base64 -d | openssl x509 -noout -enddate
```

## Referências

- [cert-manager DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/)
- [cert-manager + Cloudflare](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/)
- [Cloudflare API Token](https://developers.cloudflare.com/api/)
- [External Secrets Operator](https://external-secrets.io/)
- [Knative Custom Domains + TLS](https://knative.dev/docs/serving/services/custom-domains/)
