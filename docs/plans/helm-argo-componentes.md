# Helm por componente para Argo CD

Objetivo: entregar charts instaláveis de banco, backend e frontend, renderizações, pacotes e index.yaml sem modificar k8s/.

- [x] Criar três charts independentes preservando selectors, nomes e integração Knative/Vault.
- [x] Banco gerencia PostgreSQL, seus Services/ConfigMap e ExternalSecret; backend gerencia API, configuração, dois ExternalSecrets e Mailpit opcional; frontend gerencia Nginx, certificado e domínio.
- [x] Manter controllers, Classic ELB, ClusterSecretStores, ClusterIssuer e token Cloudflare como pré-requisitos compartilhados da plataforma.
- [x] Validar lint, renderizações, paridade funcional com k8s/, referências entre charts e isolamento de recursos.
- [x] Gerar pacotes 1.0.0, index.yaml com URLs relativas e conferir os próprios pacotes.
- [x] Documentar três Applications, pré-requisitos, publicação e adoção pelo Argo CD sem executar instalação ou publicação.
