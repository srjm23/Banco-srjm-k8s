# Revisão pré-deploy — 2026-09-09

Registro da revisão do modo convencional. A configuração atual de `k8s/` usa Knative; veja o README principal e `knative-letsencrypt.md`.

Revisados `nginx-front/nginx.conf`, `nginx-main.conf`, `index.html`, `application.yaml`, manifests Kustomize e chart Helm. Revisão local; não houve deploy ou validação no EKS.

## Problemas corrigidos

| Problema | Correção |
| --- | --- |
| Services separados e VirtualService ausentes no Kustomization | Incluídos os quatro arquivos de Services e `Istio-vs.yaml`; sem eles faltariam DNS do banco/backend e rota externa |
| Nginx substituía o protocolo HTTPS do Istio por HTTP | `map` preserva `X-Forwarded-Proto` válido, com fallback local; Spring recebe `SERVER_FORWARD_HEADERS_STRATEGY=framework` |
| `/api` sem barra caía no fallback da SPA | Redirecionamento 308 para `/api/`; `proxy_pass` preserva o prefixo exigido pelo Spring |
| Probes TCP não conferiam o estado da aplicação | Startup/liveness/readiness do backend usam Actuator sob `/api`; frontend usa `/healthz` |
| Configurações revisadas não eram montadas nos Pods | ConfigMaps de runtime montam Nginx e Spring; `SPRING_CONFIG_ADDITIONAL_LOCATION` carrega o arquivo externo |
| Variáveis OTEL não garantiam desabilitar tracing Spring/Micrometer | `MANAGEMENT_TRACING_ENABLED=false`; habilitação futura requer collector configurado |

Fluxo confirmado: Istio HTTPS → frontend:8080 → Nginx `/api/` → backend:8080 com contexto `/api` → postgres:5432. Não deve haver rewrite que remova `/api` no Istio ou no Nginx. A porta 8081 de stub_status não é publicada pelo Service. Os forwarded headers pressupõem entrada pelo gateway confiável, com cabeçalhos normalizados por ele.

## Validação realizada

- `helm lint helm/banco-srjm --strict`.
- Renderização Kustomize e Helm, incluindo namespace alternativo, SMTP externo e Gateway/StorageClass existentes.
- Script `scripts/validate-manifests.py`: unicidade, Services/seletores/portas, vínculo headless, probes, volumes/ConfigMaps, rotas e igualdade dos arquivos de runtime com as fontes.

Não foram executados `nginx -t`, inicialização das imagens, requisições HTTP reais ou dry-run no servidor Kubernetes. O binário Nginx não está disponível localmente e o acesso padrão ao daemon Docker foi negado.

## Confirmações necessárias antes do deploy

- A imagem backend precisa incluir Actuator e liberar, sem autenticação, `/api/actuator/health/liveness` e `/api/actuator/health/readiness`. O YAML habilita probes, mas não há código de SecurityFilterChain nem dependências para comprovar isso. Readiness usa o estado da aplicação; não garante consulta ao banco.
- `index.html` referencia `/assets/js/app.js` e `/assets/css/styles.css`, ausentes nesta pasta. A imagem frontend deve contê-los. O HTML não foi montado isoladamente para evitar substituir uma versão associada aos assets da imagem.
- Flyway está habilitado e Hibernate usa `ddl-auto: validate`: a imagem deve conter as migrações em `classpath:db/migration`, compatíveis com o schema do PostgreSQL.
- Confirmar formato da chave de criptografia com a implementação e manter a chave anterior ao migrar dados existentes.
- Ajustar domínio, TLS Secret no namespace do ingress gateway, labels do gateway, Secrets reais, driver/IAM EBS e arquitetura das imagens. Confirmar versão real do PostgreSQL antes de migrar dados; o PVC é novo e não importa o volume Docker.

Depois de preparar os valores e Secrets, faça o dry-run no contexto EKS correto conforme o README. Após o deploy autorizado, valide o HTTPS, os endpoints de saúde internamente, carregamento dos assets, login, operações da API e envio/captura de e-mails. As validações locais não comprovam esses comportamentos em runtime.
