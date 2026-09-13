#!/usr/bin/env python3
from collections import Counter
from pathlib import Path
import json
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHARTS = {component: ROOT / 'helm/charts' / ('banco-srjm-' + component) for component in ('banco', 'backend', 'frontend')}
SOURCES = {
    'banco': ['postgres-config.yaml', 'postgres.yaml', 'svc-postgres.yaml', 'svc-postgres-headless.yaml', 'external-secrets/postgres-secret.yaml'],
    'backend': ['backend.yaml', 'backend-config.yaml', 'mailpit.yaml', 'svc-mailpit.yaml', 'external-secrets/backend-secret.yaml', 'external-secrets/backend-application.yaml'],
    'frontend': ['frontend.yaml', 'frontend-nginx.yaml', 'certificate.yaml', 'domain-mapping.yaml', 'cluster-domain-claim.yaml'],
}


def render(component, namespace='banco-srjm', *arguments, chart=None):
    output = subprocess.check_output(['helm', 'template', component, str(chart or CHARTS[component]), '-n', namespace, *arguments], text=True)
    sources = Counter(line for line in output.splitlines() if line.startswith('# Source:'))
    assert all(count == 1 for count in sources.values()), 'Template com mais de um recurso'
    return [resource for resource in yaml.safe_load_all(output) if resource]


def identity(resource):
    return resource['apiVersion'], resource['kind'], resource['metadata'].get('namespace', ''), resource['metadata']['name']


def normalize(value):
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {}
    for key, item in value.items():
        if key.startswith(('checksum/', 'argocd.argoproj.io/')) or key in ('config-version', 'helm.sh/resource-policy'):
            continue
        if key == 'imagePullSecrets' and not item:
            continue
        clean = normalize(item)
        if key == 'annotations' and not clean:
            continue
        normalized[key] = clean
    return normalized


def check_union(groups, namespace):
    resources = sum(groups.values(), [])
    identifiers = [identity(resource) for resource in resources]
    assert len(identifiers) == len(set(identifiers)), 'Applications gerenciam recursos duplicados'
    assert not any(r['kind'] in ('Secret', 'ClusterSecretStore', 'Gateway', 'VirtualService', 'Namespace', 'ClusterIssuer') for r in resources)
    for resource in resources:
        if 'namespace' in resource['metadata']:
            assert resource['metadata']['namespace'] == namespace
    configmaps = {r['metadata']['name'] for r in resources if r['kind'] == 'ConfigMap'}
    secrets = {r['spec']['target']['name'] for r in resources if r['kind'] == 'ExternalSecret'}
    workloads = [r for r in resources if r['kind'] in ('StatefulSet', 'Deployment') or r['apiVersion'] == 'serving.knative.dev/v1']
    for workload in workloads:
        pod = workload['spec']['template']['spec']
        for container in pod['containers']:
            for env in container.get('env', []):
                for kind, targets in [('configMapKeyRef', configmaps), ('secretKeyRef', secrets)]:
                    reference = env.get('valueFrom', {}).get(kind)
                    if reference:
                        assert reference['name'] in targets, f'Referência não declarada: {reference}'
            for env in container.get('envFrom', []):
                for kind, targets in [('configMapRef', configmaps), ('secretRef', secrets)]:
                    if kind in env:
                        assert env[kind]['name'] in targets
        for volume in pod.get('volumes', []):
            if 'secret' in volume:
                assert volume['secret']['secretName'] in secrets
            if 'configMap' in volume:
                assert volume['configMap']['name'] in configmaps
    services = [r for r in resources if r['apiVersion'] == 'serving.knative.dev/v1']
    assert {r['metadata']['name'] for r in services} == {'backend', 'frontend'}
    for service in services:
        assert service['spec']['template']['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
        assert len(service['spec']['template']['metadata']['annotations']['checksum/config']) == 64
    for resource in resources:
        if resource['apiVersion'] == 'v1' and resource['kind'] == 'Service':
            selector = resource['spec']['selector']
            matches = [w for w in workloads if all(w['spec']['template']['metadata'].get('labels', {}).get(k) == v for k, v in selector.items())]
            assert len(matches) == 1
    return resources


groups = {component: render(component) for component in CHARTS}
resources = check_union(groups, 'banco-srjm')
for component, filenames in SOURCES.items():
    actual = {identity(resource): normalize(resource) for resource in groups[component]}
    expected = [yaml.safe_load((ROOT / 'k8s' / name).read_text()) for name in filenames]
    assert len(actual) == len(expected)
    for resource in expected:
        assert actual[identity(resource)] == normalize(resource), f'Divergência funcional em {component}: {identity(resource)}'
print('OK: 16 recursos, três charts sem sobreposição e equivalentes aos manifests k8s/')

alternate = {component: render(component, 'review') for component in CHARTS}
check_union(alternate, 'review')
nginx = next(r for r in alternate['frontend'] if r['kind'] == 'ConfigMap')['data']['nginx.conf']
assert 'backend.review.svc.cluster.local' in nginx
for resources in alternate.values():
    for resource in resources:
        if resource['kind'] == 'ExternalSecret':
            assert resource['spec']['dataFrom'][0]['extract']['key'].startswith('review/')
print('OK: namespace alternativo, DNS interno e caminhos Vault parametrizados')

backend = render('backend', 'banco-srjm', '--set', 'mailpit.enabled=false', '--set', 'secrets.backendName=backend-private', '--set', 'secrets.applicationName=application-private', '--set', 'externalSecrets.pathPrefix=other-path', '--set', 'knative.traffic[0].latestRevision=true', '--set', 'knative.traffic[0].percent=100')
assert not any(r['metadata']['name'] == 'mailpit' for r in backend)
service = next(r for r in backend if r['apiVersion'] == 'serving.knative.dev/v1')
assert service['spec']['traffic'] == [{'latestRevision': True, 'percent': 100}]
assert service['spec']['template']['spec']['volumes'][0]['secret']['secretName'] == 'application-private'
assert {r['spec']['target']['name'] for r in backend if r['kind'] == 'ExternalSecret'} == {'backend-private', 'application-private'}
external_off = render('banco', 'banco-srjm', '--set', 'externalSecrets.enabled=false', '--set', 'storageClass.create=true')
assert not any(r['kind'] == 'ExternalSecret' for r in external_off)
assert sum(r['kind'] == 'StorageClass' for r in external_off) == 1
assert not any(r['kind'] in ('DomainMapping', 'Certificate', 'ClusterDomainClaim') for r in render('frontend', 'review', '--set', 'domain.enabled=false'))
custom = render('frontend', 'review', '--set', 'backend.namespace=api', '--set', 'backend.serviceName=api', '--set', 'clusterDomain=internal', '--set', 'domain.host=review.example.com', '--set', 'tls.createCertificate=false', '--set', 'domain.createClaim=false')
assert not any(r['kind'] in ('Certificate', 'ClusterDomainClaim') for r in custom)
assert 'api.api.svc.internal' in next(r for r in custom if r['kind'] == 'ConfigMap')['data']['nginx.conf']
assert next(r for r in custom if r['kind'] == 'DomainMapping')['metadata']['name'] == 'review.example.com'
print('OK: recursos opcionais, referências customizadas e configuração de tráfego')

for component in ('backend', 'frontend'):
    key = 'config.MAIL_FROM=changed@example.com' if component == 'backend' else 'backend.serviceName=changed'
    old = next(r for r in groups[component] if r['apiVersion'] == 'serving.knative.dev/v1')
    new = next(r for r in render(component, 'banco-srjm', '--set', key) if r['apiVersion'] == 'serving.knative.dev/v1')
    assert old['spec']['template']['metadata']['annotations']['checksum/config'] != new['spec']['template']['metadata']['annotations']['checksum/config']
    digest = 'sha256:' + 'a' * 64
    changed = next(r for r in render(component, 'banco-srjm', '--set', 'image.digest=' + digest) if r['apiVersion'] == 'serving.knative.dev/v1')
    assert changed['spec']['template']['spec']['containers'][0]['image'].endswith('@' + digest)
print('OK: atualização de configuração altera revisão e imagens aceitam digest')

for chart in CHARTS.values():
    for template in (chart / 'templates').glob('*.yaml'):
        assert not any(line.lstrip().startswith('#') for line in template.read_text().splitlines())
    schema = json.loads((chart / 'values.schema.json').read_text())
    assert schema['type'] == 'object'
print('OK: um recurso por template e schemas de values presentes')
