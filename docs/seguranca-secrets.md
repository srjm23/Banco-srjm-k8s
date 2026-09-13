# Credenciais da aplicação

O Vault é a origem das credenciais. O External Secrets Operator autentica usando ServiceAccounts Kubernetes e sincroniza seis Secrets nos namespaces consumidores. Consulte [instalação, comandos e recuperação](vault-external-secrets.md).

| Secret | Consumidor |
| --- | --- |
| banco-srjm/postgres-secret | PostgreSQL e senha de banco do backend |
| banco-srjm/backend-secret | Variáveis sensíveis do backend |
| banco-srjm/backend-application | Arquivo Spring montado em /etc/banco/application.yaml |
| banco-srjm/frontend-secret | Placeholder preservado do frontend |
| banco-srjm/mailpit-secret | Placeholder preservado do Mailpit |
| cert-manager/cloudflare-api-token-secret | ClusterIssuer, desafio DNS-01 na Cloudflare |

Configurações comuns permanecem nos ConfigMaps. Kubernetes representa o campo `data` dos Secrets em base64; base64 não é criptografia. Nenhuma credencial foi rotacionada na migração.

Os manifests ExternalSecret podem ser versionados: contêm referências, sem valores sensíveis. Os antigos Secrets locais e a pasta `.secrets/` são ignorados pelo Git. As anotações antigas `last-applied-configuration` dos seis Secrets foram removidas para eliminar cópias redundantes dos valores.

O Vault possui TLS e armazenamento persistente. O acesso dos leitores é restrito por políticas, e os ClusterSecretStores limitam os namespaces consumidores. O token root de bootstrap foi revogado. A aplicação continua lendo Secrets Kubernetes; não precisa de Vault Agent Injector.
