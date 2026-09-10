# 🔐 Segurança de Secrets - Banco SRJM

## Visão Geral

O projeto segue a melhor prática de **segregação de credenciais** por aplicação. Cada serviço tem seu próprio manifesto de Secret consolidado.

## Estrutura de Secrets (Um por Aplicação)

### 1. **Backend Secret** (`backend-secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: backend-secret
  namespace: banco-srjm
type: Opaque
stringData:
  MAIL_USERNAME: ''          # SMTP username (opcional)
  MAIL_PASSWORD: ''          # SMTP password (opcional)
  DATA_ENCRYPTION_KEY: ...   # Chave de criptografia de dados
  ADMINISTRATOR_CREATION_TOKEN: ...  # Token para criar admin
```

**Usado por:** `backend.yaml` (Knative Service)

**Referência no deployment:**
```yaml
envFrom:
  - secretRef:
      name: backend-secret
```

---

### 2. **PostgreSQL Secret** (`postgres-secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: banco-srjm
type: Opaque
stringData:
  POSTGRES_PASSWORD: ...     # Senha do usuário banco_user
```

**Usado por:** 
- `postgres.yaml` (StatefulSet)
- `backend.yaml` (DB_PASSWORD)

**Referência nos deployments:**
```yaml
# Em postgres.yaml:
envFrom:
  - secretRef:
      name: postgres-secret

# Em backend.yaml:
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: postgres-secret
      key: POSTGRES_PASSWORD
```

---

### 3. **Frontend Secret** (`frontend-secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: frontend-secret
  namespace: banco-srjm
type: Opaque
stringData:
  placeholder: "true"  # Atualmente não requer secrets
```

**Usado por:** `frontend.yaml` (Knative Service)

**Status:** Sem credenciais necessárias (usa apenas ConfigMap)

---

### 4. **Mailpit Secret** (`mailpit-secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: mailpit-secret
  namespace: banco-srjm
type: Opaque
stringData:
  placeholder: "true"  # Servidor SMTP de teste, sem autenticação
```

**Usado por:** `mailpit.yaml` (Deployment)

**Status:** Sem credenciais necessárias

---

### 5. **Cloudflare Secret** (`cloudflare-secret.yaml`)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: cloudflare-api-token-secret
  namespace: cert-manager  # ⚠️ NOTA: NAMESPACE DIFERENTE
type: Opaque
stringData:
  api-token: ...         # API Token do Cloudflare para DNS-01
```

**Usado por:** `letsencrypt-production.yaml` (ClusterIssuer)

**Referência:**
```yaml
solvers:
  - dns01:
      cloudflare:
        apiTokenSecretRef:
          name: cloudflare-api-token-secret
          key: api-token
```

---

## 🚨 Proteção de Secrets

### `.gitignore`
Todos os secrets são **IGNORADOS** no git:
```
# Secrets extraídos da configuração da aplicação - NUNCA fazer commit
/k8s/postgres-secret.yaml
/k8s/backend-secret.yaml
/k8s/cloudflare-secret.yaml
/k8s/frontend-secret.yaml
/k8s/mailpit-secret.yaml
```

### Template Seguro
Um template de exemplo **é permitido** no git:
```
!/k8s/secrets-template.yaml  # SEGURO - apenas valores de exemplo
```

---

## 📋 Como Criar seus Secrets

### **Opção 1: Copiar e preencher o template**
```bash
cp k8s/secrets-template.yaml k8s/postgres-secret.yaml
# Editar e preencher valores REAIS
vim k8s/postgres-secret.yaml

cp k8s/secrets-template.yaml k8s/backend-secret.yaml
# Editar e preencher valores REAIS
vim k8s/backend-secret.yaml

# ... repetir para cloudflare e outros
```

### **Opção 2: Usar um script seguro**
```bash
#!/bin/bash
# criar-secrets.sh

# Backend Secret
cat <<EOF > k8s/backend-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: backend-secret
  namespace: banco-srjm
type: Opaque
stringData:
  MAIL_USERNAME: "$MAIL_USERNAME"
  MAIL_PASSWORD: "$MAIL_PASSWORD"
  DATA_ENCRYPTION_KEY: "$DATA_ENCRYPTION_KEY"
  ADMINISTRATOR_CREATION_TOKEN: "$ADMINISTRATOR_CREATION_TOKEN"
EOF

# ... continuar com outros secrets
echo "✓ Secrets criados com sucesso"
```

### **Opção 3: Usando `kubectl create secret` (Recomendado)**
```bash
# Backend
kubectl create secret generic backend-secret \
  --from-literal=MAIL_USERNAME='' \
  --from-literal=MAIL_PASSWORD='' \
  --from-literal=DATA_ENCRYPTION_KEY='<sua-chave>' \
  --from-literal=ADMINISTRATOR_CREATION_TOKEN='<seu-token>' \
  -n banco-srjm \
  --dry-run=client \
  -o yaml > k8s/backend-secret.yaml

# PostgreSQL
kubectl create secret generic postgres-secret \
  --from-literal=POSTGRES_PASSWORD='<sua-senha-forte>' \
  -n banco-srjm \
  --dry-run=client \
  -o yaml > k8s/postgres-secret.yaml

# Cloudflare (namespace cert-manager)
kubectl create secret generic cloudflare-api-token-secret \
  --from-literal=api-token='<seu-token-cloudflare>' \
  -n cert-manager \
  --dry-run=client \
  -o yaml > k8s/cloudflare-secret.yaml
```

---

## ✅ Checklist de Segurança

- [ ] **Nenhuma credencial em arquivos tracked pelo git**
  ```bash
  git status  # Verificar se nenhum *-secret.yaml aparece
  ```

- [ ] **Secrets não contêm valores de exemplo**
  ```bash
  grep -r "SUBSTITUA_POR" k8s/*.yaml  # Não deve haver resultados
  ```

- [ ] **Todos os secrets existem antes de deploy**
  ```bash
  kubectl get secrets -n banco-srjm
  # Deve listar: backend-secret, postgres-secret, frontend-secret, mailpit-secret
  
  kubectl get secrets -n cert-manager
  # Deve listar: cloudflare-api-token-secret
  ```

- [ ] **Nenhuma credencial em ConfigMaps** (apenas em Secrets)
  ```bash
  grep -r "password\|token\|key" k8s/backend-config.yaml
  # Não deve haver valores sensíveis
  ```

- [ ] **Backend acessa secrets corretamente**
  ```bash
  kubectl logs -n banco-srjm -l app=backend | grep -i "credential\|secret\|password"
  ```

---

## 🔄 Deploy com Secrets

### **1. Criar secrets manualmente**
```bash
# Preencher valores nos arquivos
vim k8s/backend-secret.yaml
vim k8s/postgres-secret.yaml
vim k8s/cloudflare-secret.yaml
```

### **2. Validar manifesto**
```bash
kubectl apply -k k8s --dry-run=client -o yaml > /tmp/validate.yaml
```

### **3. Aplicar**
```bash
kubectl apply -k k8s
```

### **4. Verificar**
```bash
# Ver se secrets foram criados
kubectl get secrets -n banco-srjm
kubectl get secrets -n cert-manager

# Ver se backend consegue acessar
kubectl describe pod -n banco-srjm -l app=backend
```

---

## 🛡️ Alternativas Avançadas (Futuro)

Para ambientes de produção, considere:

### **Sealed Secrets**
Criptografa secrets no git com uma chave específica do cluster.
```bash
# Instalar
kubectl apply -f https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.0/controller.yaml

# Usar
echo -n mypassword | kubectl create secret generic mysecret --dry-run=client --from-file=/dev/stdin -o yaml | kubeseal -o yaml > mysealedsecret.yaml
```

### **External Secrets Operator**
Sincroniza secrets de um vault externo (AWS Secrets Manager, HashiCorp Vault, etc.)

### **Kyverno Policies**
Valida que nenhum secret com credenciais é commitado:
```yaml
apiVersion: kyverno.io/v1
kind: ClusterPolicy
metadata:
  name: block-hardcoded-secrets
spec:
  validationFailureAction: audit
  rules:
  - name: no-hardcoded-passwords
    match:
      resources:
        kinds:
        - Secret
    pattern:
      stringData:
        password: "?*"  # Bloqueia se houver valor default
```

---

## 📞 Suporte

Se encontrar problemas:
1. Verificar se `*-secret.yaml` não está commitado
2. Confirmar que secrets existem: `kubectl get secrets -n <namespace>`
3. Checar logs do pod: `kubectl logs -n banco-srjm <pod-name>`
4. Validar referências em deployments

