# Knative Serving + Istio + Let's Encrypt (DNS-01)

A configuração agora usa **DNS-01 com Cloudflare** para validar certificados Let's Encrypt. Isso funciona com Knative, Istio Gateway e não requer HTTP-01 Ingress.

Consulte [istio-letsencrypt.md](istio-letsencrypt.md) para detalhes de validação DNS-01.

## Arquitetura

```text
HTTPS → LoadBalancer do Knet-Istio → DomainMapping → Knative frontend
                                                       ↓ /api/
                                  backend.<namespace>.svc.cluster.local:80
                                                       ↓
                                              Knative backend
                                                       ↓
                                           PostgreSQL + PVC EBS
```

O Knative cria e gerencia os Services, revisões e rotas de frontend/backend. O chart não cria os antigos Deployments, Services ou Gateway/VirtualService da aplicação neste modo. O PostgreSQL continua StatefulSet; Mailpit continua Deployment, pois SMTP não é um serviço HTTP Knative.

Ambos os Knative Services têm visibilidade `cluster-local`. O `DomainMapping` torna somente o frontend acessível pelo domínio público. Nginx usa a porta **80** e envia o **Host interno do backend**, necessário para o roteamento Knative; mantém `/api/` e encaminha o host público em `X-Forwarded-Host`.

## Pré-requisitos do cluster

- **Knative Serving**, DomainMapping controller/webhook e Knet-Istio compatíveis instalados; ingress público e local configurados pelo Knet-Istio.
- **cert-manager** com CRDs e ClusterIssuer `letsencrypt-production` pronto (configurado em `k8s/letsencrypt-production.yaml`)
- **Cloudflare** com API Token para DNS-01 (Secret em `k8s/cloudflare-secret.yaml`)
- DNS público do domínio apontando para o LoadBalancer do ingress Knet-Istio, portas 80/443 disponíveis
- Pré-requisitos de EBS e Secrets conforme documentado em `k8s/` e `helm/README.md`
- Backend inclui Actuator com endpoints de probe acessíveis; a imagem frontend contém Nginx e os assets da aplicação.

## Certificado explícito (Knative + cert-manager)

Este modo usa um `Certificate` explícito do cert-manager (`k8s/certificate.yaml`) e `DomainMapping.spec.tls.secretName`.

O certificado é emitido e renovado pelo cert-manager no **namespace da aplicação** (`banco-srjm`):

```yaml
# k8s/certificate.yaml - Certificate
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: banco-srjm
  namespace: banco-srjm
spec:
  secretName: banco-srjm-tls
  dnsNames:
  - bancosrjm.geradorqrcode-srjm.uk
  issuerRef:
    group: cert-manager.io
    kind: ClusterIssuer
    name: letsencrypt-production
```

Não é o Secret manual no namespace `istio-system`. Não requer o componente `net-certmanager` ou habilitar Auto TLS global no Knative; isso seria necessário para delegar ao Knative a criação automática de Certificates (não é a abordagem deste chart).

## Configuração: Helm

```sh
cp helm/values-knative.example.yaml helm/values-knative.local.yaml
```

Edite `istio.host` com o domínio real. `FRONTEND_URL` será calculada como `https://<dominio>/`. Se houver `backend.frontendUrl` de outro override, atualize-o também.

Por padrão, `certManager.createIssuer=false` referencia `letsencrypt-production` existente. Se tiver outro nome, ajuste `certManager.issuerRef`. Os Secrets da aplicação também devem existir, conforme `helm/README.md`.

**DNS-01 agora está configurado no ClusterIssuer** (`k8s/letsencrypt-production.yaml`). Não é necessário alterar o solver no Helm:

```yaml
# ❌ NÃO MUDE ISTO (Helm values-knative.example.yaml)
# O solver está no ClusterIssuer, não no Helm values

certManager:
  createIssuer: false
  issuerRef:
    name: letsencrypt-production
    kind: ClusterIssuer
```

Se quiser criar um novo ClusterIssuer via Helm:

```yaml
certManager:
  createIssuer: true
  email: srjm99silva@gmail.com
  server: https://acme-v02.api.letsencrypt.org/directory
  # Deixe o Helm com o solver, OU mantenha createIssuer=false e use o do k8s/
```

Após preencher os valores e preparar a plataforma:

```sh
helm lint helm/banco-srjm --strict -f helm/values-knative.local.yaml
helm template banco-srjm helm/banco-srjm -n banco-srjm \
  -f helm/values-knative.local.yaml > /tmp/banco-knative.yaml
# O namespace e os Secrets da aplicação devem estar preparados.
kubectl apply --dry-run=server -f /tmp/banco-knative.yaml
helm upgrade --install banco-srjm helm/banco-srjm \
  -n banco-srjm --create-namespace \
  -f helm/values-knative.local.yaml --wait --timeout 10m
kubectl -n banco-srjm wait --for=condition=Ready ksvc/backend ksvc/frontend --timeout=600s
kubectl -n banco-srjm wait --for=condition=Ready certificate/banco-srjm --timeout=600s
kubectl -n banco-srjm get ksvc,domainmapping,certificate,pvc
```

O `--wait` Helm não substitui a verificação de Ready dos CRDs. Também verifique `DomainMapping` Ready e teste `curl -I https://<dominio>/`, redirecionamento HTTP, login e operações da API.

## Configuração: Kustomize

Knative está diretamente em `k8s/`. Edite o domínio em:
- `k8s/certificate.yaml`, `k8s/cluster-domain-claim.yaml` e `k8s/domain-mapping.yaml`
- `FRONTEND_URL` em `k8s/backend-config.yaml`

O exemplo usa `banco-srjm`; ao mudar namespace, ajuste também:
- hostname Nginx em `k8s/frontend-nginx.yaml`
- namespace do ClusterDomainClaim

Os arquivos locais `k8s/postgres-secret.yaml` e `k8s/backend-secret.yaml` entram no Kustomization e devem estar preenchidos.

O ClusterIssuer e Secret Cloudflare estão em `k8s/`:

```sh
kubectl kustomize k8s > /tmp/banco-knative.yaml
kubectl apply --dry-run=server -f /tmp/banco-knative.yaml
kubectl apply -k k8s
```

`overlays/knative` é um alias de compatibilidade para a mesma configuração. Os recursos convencionais em `k8s/legacy/` não são aplicados. `kubectl apply` não remove recursos de instalações anteriores: migração exige tratar conflitos sem excluir o PVC.

## Escala e inicialização

- `knative.frontend/backend.minScale=1` e `maxScale=3` são valores iniciais; réplicas são controladas por Knative. Configure `minScale=0` se aceitar cold starts.
- Backend não usa initContainer; `SPRING_FLYWAY_CONNECT_RETRIES=60` tolera a inicialização do banco. Probes de readiness permanecem e liveness começa após 300s.
- Frontend inicia Nginx com configuração montada em diretório, sem mounts subPath. Probes não dependem da API.
- Persistência e escala do banco não mudam. Ajuste máximo de réplicas e pool de conexões do backend à capacidade do PostgreSQL.
- Instalações sem sidecars precisam permitir tráfego HTTP/TCP da aplicação conforme políticas de rede existentes.

## Segurança das credenciais Cloudflare

**IMPORTANTE**: O arquivo `k8s/cloudflare-secret.yaml` contém credenciais sensíveis.

Em **desenvolvimento**:
```sh
# .gitignore
k8s/cloudflare-secret.yaml
```

Em **produção**, use uma das alternativas:

### Opção 1: External Secrets + Azure Key Vault
```yaml
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

### Opção 2: Sealed Secrets
```sh
# Criptografar o Secret antes de commitar
kubeseal -f k8s/cloudflare-secret.yaml -w k8s/cloudflare-secret-sealed.yaml
# Commitar apenas cloudflare-secret-sealed.yaml
```

### Opção 3: Variáveis de ambiente com Helm
```yaml
# helm/values-knative.local.yaml
certManager:
  cloudflare:
    email: srjm99silva@gmail.com
    apiTokenSecretName: cloudflare-api-token-secret  # Cria externamente

# Criar Secret separadamente:
kubectl create secret generic cloudflare-api-token-secret \
  -n cert-manager \
  --from-literal=api-token=$CLOUDFLARE_API_TOKEN
```

## Troubleshooting

Consulte [istio-letsencrypt.md#troubleshooting](istio-letsencrypt.md#troubleshooting) para diagnosticar problemas do Certificate e Challenge.

Testes específicos Knative:

```sh
# DomainMapping status
kubectl -n banco-srjm describe domainmapping bancosrjm.geradorqrcode-srjm.uk

# Verificar se o Secret TLS está linkado
kubectl -n banco-srjm get secret banco-srjm-tls -o yaml

# Teste de HTTPS
curl -I https://bancosrjm.geradorqrcode-srjm.uk/
openssl s_client -connect bancosrjm.geradorqrcode-srjm.uk:443 -showcerts
```

## Próximas etapas

1. ✅ ClusterIssuer com DNS-01 Cloudflare
2. ✅ Secret Cloudflare em cert-manager
3. ✅ Certificate emitido automaticamente
4. ✅ DomainMapping referencia Secret TLS
5. ✅ Knative Services rodando
6. ✅ HTTPS funcional

Teste completo:
```sh
curl -I https://bancosrjm.geradorqrcode-srjm.uk/
# Esperado: HTTP/2 200 (ou 301/302 para redirect HTTP→HTTPS)

# Login e operações API
curl -X POST https://bancosrjm.geradorqrcode-srjm.uk/api/login
```

## Referências

- [istio-letsencrypt.md](istio-letsencrypt.md) — DNS-01 com Cloudflare
- [Knative Custom Domains + TLS](https://knative.dev/docs/serving/services/custom-domains/)
- [cert-manager DNS-01](https://cert-manager.io/docs/configuration/acme/dns01/)
- [External Secrets Operator](https://external-secrets.io/)
- [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets)
