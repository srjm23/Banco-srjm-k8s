#!/usr/bin/env python3
import subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]


def render(path):
    output = subprocess.check_output(['kubectl', 'kustomize', path], cwd=ROOT, text=True)
    return [resource for resource in yaml.safe_load_all(output) if resource]


def identity(resource):
    metadata = resource['metadata']
    return resource['apiVersion'], resource['kind'], metadata.get('namespace', ''), metadata['name']


def load(relative):
    return yaml.safe_load((ROOT / relative).read_text())


referenced = set()


def check_tree(directory):
    manifest = load(str(directory / 'kustomization.yaml'))
    assert manifest['sortOptions']['order'] == 'fifo', f'Ordem FIFO ausente: {directory}'
    referenced.add(directory / 'kustomization.yaml')
    for entry in manifest['resources']:
        path = directory / entry
        assert (ROOT / path).exists(), f'Referência ausente: {path}'
        if (ROOT / path).is_dir():
            check_tree(path)
        else:
            assert path not in referenced, f'Arquivo incluído duas vezes: {path}'
            referenced.add(path)


check_tree(Path('k8s'))
for path in (ROOT / 'k8s').rglob('*.yaml'):
    resources = [resource for resource in yaml.safe_load_all(path.read_text()) if resource]
    assert len(resources) == 1, f'Múltiplos recursos no arquivo: {path.name}'
    assert path.relative_to(ROOT) in referenced, f'Manifesto fora do Kustomize: {path.name}'

resources = render('k8s')
identities = [identity(resource) for resource in resources]
assert len(identities) == len(set(identities)), 'Recursos duplicados'
assert not any(resource['kind'] == 'Secret' for resource in resources), 'Secret estático no apply'
assert not any(resource['kind'] in ('Gateway', 'VirtualService') for resource in resources), 'Rota manual duplicando o Knative'

knative = {r['metadata']['name']: r for r in resources if r['apiVersion'] == 'serving.knative.dev/v1'}
assert set(knative) == {'backend', 'frontend'}
assert not any(r['apiVersion'] in ('apps/v1', 'v1') and r['kind'] in ('Deployment', 'Service') and r['metadata']['name'] in knative for r in resources)
assert knative['backend']['metadata']['labels']['networking.knative.dev/visibility'] == 'cluster-local'
assert 'networking.knative.dev/visibility' not in knative['frontend']['metadata'].get('labels', {})
for service in knative.values():
    template = service['spec']['template']
    assert template['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
    assert 'initContainers' not in template['spec']
    assert template['metadata']['annotations']['autoscaling.knative.dev/min-scale'] == '1'
    assert template['metadata']['annotations']['autoscaling.knative.dev/max-scale'] == '3'
backend = knative['backend']['spec']['template']['spec']
volume = next(v for v in backend['volumes'] if v['name'] == 'application-config')
assert volume['secret']['secretName'] == 'backend-application'
assert 'configMap' not in volume
configs = {(r['metadata']['namespace'], r['metadata']['name']): r for r in resources if r['kind'] == 'ConfigMap'}
assert ('banco-srjm', 'backend-application') not in configs
nginx = configs[('banco-srjm', 'frontend-nginx')]['data']['nginx.conf']
assert 'set $backend_upstream backend.banco-srjm.svc.cluster.local;' in nginx
assert 'proxy_set_header Host backend.banco-srjm.svc.cluster.local;' in nginx
assert 'proxy_pass http://$backend_upstream:80;' in nginx
assert 'resolver kube-dns.kube-system.svc.cluster.local valid=10s ipv6=off;' in nginx
print('OK: frontend/backend Knative, configuração e rota interna da API')

stores = {r['metadata']['name']: r for r in resources if r['kind'] == 'ClusterSecretStore'}
assert set(stores) == {'vault-banco', 'vault-cert-manager'}
for name, namespace in [('vault-banco', 'banco-srjm'), ('vault-cert-manager', 'cert-manager')]:
    store = stores[name]['spec']
    assert store['conditions'] == [{'namespaces': [namespace]}]
    assert store['provider']['vault']['server'] == 'https://vault.vault.svc:8200'
    assert store['provider']['vault']['version'] == 'v2'
    assert store['provider']['vault']['auth']['kubernetes']['serviceAccountRef']['audiences'] == ['vault']
external = [r for r in resources if r['kind'] == 'ExternalSecret']
expected = {('banco-srjm', name) for name in ('backend-secret', 'postgres-secret', 'backend-application')}
expected.add(('cert-manager', 'cloudflare-api-token-secret'))
assert {(r['metadata']['namespace'], r['spec']['target']['name']) for r in external} == expected
assert len(external) == len(expected)
for resource in external:
    namespace = resource['metadata']['namespace']
    spec = resource['spec']
    assert spec['secretStoreRef'] == {'name': 'vault-banco' if namespace == 'banco-srjm' else 'vault-cert-manager', 'kind': 'ClusterSecretStore'}
    assert spec['dataFrom'][0]['extract']['key'] == namespace + '/' + spec['target']['name']
    assert spec['target']['creationPolicy'] == 'Orphan'
    assert spec['target']['deletionPolicy'] == 'Retain'
    assert spec['refreshInterval'] == '1m'
print('OK: quatro Secrets externos, isolamento dos stores e caminhos Vault')

workloads = [r for r in resources if r['kind'] in ('StatefulSet', 'Deployment') or r['apiVersion'] == 'serving.knative.dev/v1']
for workload in workloads:
    namespace = workload['metadata']['namespace']
    pod = workload['spec']['template']['spec']
    for container in pod['containers']:
        for item in container.get('env', []):
            value = item.get('valueFrom', {})
            for kind, targets in [('secretKeyRef', expected), ('configMapKeyRef', configs)]:
                if kind in value:
                    assert (namespace, value[kind]['name']) in targets
        for item in container.get('envFrom', []):
            for kind, targets in [('secretRef', expected), ('configMapRef', configs)]:
                if kind in item:
                    assert (namespace, item[kind]['name']) in targets
    for volume in pod.get('volumes', []):
        if 'secret' in volume:
            assert (namespace, volume['secret']['secretName']) in expected
        if 'configMap' in volume:
            assert (namespace, volume['configMap']['name']) in configs

platform = load('k8s/platform/knative-serving.yaml')
for name, filename in [('knative-ingress-gateway', 'istio-ingress-classic.yaml'), ('knative-local-gateway', 'knative-local-gateway.yaml')]:
    service = load('k8s/platform/' + filename)
    assert service['metadata']['namespace'] == 'istio-ingress'
    assert service['spec']['selector'] == {'app': 'istio-ingress', 'istio': 'ingress'}
    assert platform['spec']['ingress']['istio'][name]['selector'] == service['spec']['selector']
classic = load('k8s/platform/istio-ingress-classic.yaml')
assert classic['spec']['type'] == 'LoadBalancer'
assert 'loadBalancerClass' not in classic['spec']
assert not any('nlb' in key or 'subnets' in key for key in classic['metadata'].get('annotations', {}))
for service in (r for r in resources if r['apiVersion'] == 'v1' and r['kind'] == 'Service' and r['metadata']['namespace'] == 'banco-srjm'):
    matches = [w for w in workloads if w['metadata']['namespace'] == service['metadata']['namespace'] and all(w['spec']['template']['metadata'].get('labels', {}).get(k) == v for k, v in service['spec']['selector'].items())]
    assert len(matches) == 1
    ports = {p['name'] for c in matches[0]['spec']['template']['spec']['containers'] for p in c.get('ports', [])}
    assert all(p['targetPort'] in ports for p in service['spec']['ports'])
postgres = load('k8s/postgres.yaml')
headless = load('k8s/svc-postgres-headless.yaml')
assert postgres['spec']['serviceName'] == headless['metadata']['name']
assert headless['spec']['clusterIP'] == 'None'
certificate = load('k8s/certificate.yaml')
mapping = load('k8s/domain-mapping.yaml')
assert mapping['spec']['tls']['secretName'] == certificate['spec']['secretName']
assert certificate['spec']['dnsNames'] == [mapping['metadata']['name']]
assert mapping['spec']['ref']['name'] == 'frontend'
print('OK: selectors, Classic ELB, Services do banco e domínio TLS')
print(f'OK: {len(resources)} recursos únicos, um por YAML, todos incluídos no Kustomize FIFO')
