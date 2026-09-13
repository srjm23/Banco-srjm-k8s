# Vault e External Secrets

Instalar Vault Helm 0.34.1 (Vault 2.0.4) e recuperar External Secrets Helm 2.10.0.
Vault usa TLS interno, Raft persistente em PVC gp3 de 5 GiB e uma réplica.
Inicializar com três shares e threshold dois; guardar bootstrap em .secrets,
permissão 600, sem expor em logs. Não usar modo dev nem token root no ESO.

Migrar os valores atuais do Kubernetes para KV v2, verificar igualdade e
configurar autenticação Kubernetes com ServiceAccounts e políticas de leitura
separadas para banco-srjm e cert-manager. Criar dois ClusterSecretStores limitados aos namespaces banco-srjm e cert-manager e
ExternalSecrets com nomes atuais, retenção e reconciliação a cada minuto.
Remover Secrets estáticos do Kustomization somente após sincronização validada.

Verificar Vault/PVC, ESO, autenticação, sincronização de todos os Secrets,
igualdade de conteúdo e HTTPS da aplicação. Revogar token root do bootstrap
após criar acesso administrativo restrito e guardar as chaves de recuperação.
