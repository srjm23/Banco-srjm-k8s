# Vault e External Secrets no EKS

> Atualização: foram preparados três charts independentes para banco, backend e frontend, preservando `k8s/`. Os pacotes, índice e instruções de adoção estão em [Helm e Argo CD](../helm/README.md). A consolidação abaixo descreve a etapa anterior.

Instalados no contexto `eks-new`: chart HashiCorp Vault 0.34.1 e External Secrets 2.10.0. O Vault usa TLS interno emitido pelo cert-manager, Service ClusterIP e Raft em PVC EBS gp3 de 5 GiB. Há uma réplica: esta instalação não oferece alta disponibilidade nem auto-unseal.

O fluxo é Vault KV v2 → External Secrets Operator → Secret Kubernetes → aplicação. ConfigMaps permanecem separados. Não foi necessário instalar o Vault Injector ou mudar os selectors do Istio.

| ClusterSecretStore | Namespace autorizado | Caminho KV v2 |
| --- | --- | --- |
| vault-banco | banco-srjm | secret/banco-srjm/* |
| vault-cert-manager | cert-manager | secret/cert-manager/cloudflare-api-token-secret |

Cada store possui ServiceAccount e política de leitura próprias. O teste de acesso cruzado retornou 403 para ambos. Seis ExternalSecrets usam atualização de um minuto, `creationPolicy: Orphan` e `deletionPolicy: Retain`, preservando os Secrets quando o recurso de sincronização é removido. O certificado público da CA fica em `k8s/external-secrets/vault-ca.yaml`; nenhuma chave privada é versionada.

## Instalação e migração

Pré-requisitos: contexto eks-new, Helm, kubectl, Python com PyYAML, cert-manager e StorageClass banco-ebs-gp3. O bootstrap migra os seis Secrets já existentes no cluster; em um ambiente novo, provisione as credenciais iniciais antes desta etapa. Não execute novamente a inicialização para substituir um Vault existente.

```sh
helm repo add hashicorp https://helm.releases.hashicorp.com
helm repo add external-secrets https://charts.external-secrets.io
helm repo update
kubectl --context eks-new apply -k k8s/vault
kubectl --context eks-new -n vault wait --for=condition=Ready certificate/vault-ca certificate/vault-server --timeout=180s
helm --kube-context eks-new upgrade --install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace --version 2.10.0 -f helm/values-external-secrets.yaml --wait --timeout 5m
helm --kube-context eks-new upgrade --install vault hashicorp/vault -n vault --version 0.34.1 -f helm/values-vault-eks.yaml --timeout 5m
kubectl --context eks-new -n vault wait --for=jsonpath='{.status.phase}'=Running pod/vault-0 --timeout=300s
python3 scripts/bootstrap-vault.py
kubectl --context eks-new apply -k k8s/external-secrets
kubectl --context eks-new wait --for=condition=Ready clustersecretstore/vault-banco clustersecretstore/vault-cert-manager --timeout=180s
kubectl --context eks-new -n banco-srjm wait --for=condition=Ready externalsecret --all --timeout=180s
kubectl --context eks-new -n cert-manager wait --for=condition=Ready externalsecret/cloudflare-api-token-secret --timeout=180s
python3 scripts/bootstrap-vault.py --verify-and-finalize
```

O script inicializa apenas um Vault não inicializado, desbloqueia, configura KV v2 e autenticação Kubernetes, migra sem imprimir valores e verifica igualdade dos dados. Recusa sobrescrever caminhos com valores divergentes. A finalização verifica sincronização, isolamento e login administrativo e então revoga o token root, removendo-o do arquivo local. Os recursos YAML contêm um objeto por arquivo e os Kustomizations usam FIFO.

## Operação e recuperação

As três chaves Shamir estão em `.secrets/vault-init.json`, com permissão 600, diretório 700 e exclusão do Git. São necessárias duas para desbloquear o Vault. Faça backup protegido fora desta máquina e distribua as chaves a custodiantes; o arquivo local concentra todas as partes. Faça também backups dos snapshots Raft: as chaves não substituem os dados do PVC.

Após reinício do Vault, desbloqueie usando:

```sh
python3 scripts/bootstrap-vault.py --unseal
kubectl --context eks-new -n vault get pods,pvc
kubectl --context eks-new get clustersecretstores
kubectl --context eks-new get externalsecrets -A
```

Para administrar os caminhos de credenciais via identidade Kubernetes autorizada:

```sh
python3 scripts/bootstrap-vault.py --admin-token
kubectl --context eks-new -n vault port-forward service/vault 8200:8200
```

A UI está em https://localhost:8200 e usa a CA privada da instalação. O token temporário é salvo em `.secrets/vault-admin-token`; não publique esse arquivo. Esse acesso exige permissão Kubernetes para criar tokens da ServiceAccount `vault-admin` no namespace `vault`. O papel administra os caminhos das credenciais, sem substituir um administrador root do Vault.

Mudanças no Vault atualizam os Secrets em até aproximadamente um minuto. Variáveis de ambiente de pods existentes não são recarregadas: altere o template do serviço Knative para criar uma revisão que consuma os novos valores. Uma alteração apenas no Secret não cria revisão automaticamente. Rotacionar a senha do PostgreSQL exige alterar também a senha no banco já inicializado.

A aplicação é gerenciada exclusivamente por `kubectl apply -k k8s`. O chart Helm alternativo foi removido para evitar duplicação; Helm continua instalando Vault e External Secrets. Os seis manifests de Secrets locais usados na migração foram movidos para `.secrets/manifestos-anteriores/` e não fazem parte do Kustomize. O arquivo Spring em `application.yaml` na raiz permanece como referência de configuração; o conteúdo usado pelo backend é o sincronizado do Vault.


Referências: [provider Vault do ESO](https://external-secrets.io/latest/provider/hashicorp-vault/) e [configuração Helm do Vault](https://developer.hashicorp.com/vault/docs/deploy/kubernetes/helm/configuration).
