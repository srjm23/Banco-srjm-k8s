#!/usr/bin/env python3
import subprocess
from collections import Counter
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = 'helm/banco-srjm'

def render(namespace='banco-srjm', *args):
    output = subprocess.check_output(['helm', 'template', 'banco-srjm', CHART,
                                      '-n', namespace, *args], cwd=ROOT, text=True)
    sources = Counter(line for line in output.splitlines() if line.startswith('# Source:'))
    assert all(count == 1 for count in sources.values()), 'Template Helm com múltiplos recursos'
    return [d for d in yaml.safe_load_all(output) if d]

def identity(d):
    return d['apiVersion'], d['kind'], d['metadata']['name']

def normalized(value):
    if isinstance(value, list):
        return [normalized(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key.startswith(('checksum/', 'app.kubernetes.io/')) or key == 'helm.sh/resource-policy':
            continue

        if key == 'imagePullSecrets' and item == []:
            continue
        if key == 'sidecar.istio.io/inject' and item == 'false':
            continue
        clean = normalized(item)
        if key in ('labels', 'annotations') and not clean:
            continue
        result[key] = clean
    return result

def check(docs, namespace):
    ids = [identity(d) for d in docs]
    assert len(ids) == len(set(ids)), 'Recursos duplicados'
    for d in docs:
        if 'namespace' in d['metadata']:
            assert d['metadata']['namespace'] == namespace
    ksvc = {d['metadata']['name']: d for d in docs if d['apiVersion'] == 'serving.knative.dev/v1'}
    assert set(ksvc) == {'backend', 'frontend'}
    assert not any(d['kind'] in ('Gateway', 'VirtualService') for d in docs)
    assert not any(d['apiVersion'] in ('v1', 'apps/v1') and d['kind'] in ('Service', 'Deployment') and d['metadata']['name'] in ksvc for d in docs)
    assert ksvc['backend']['metadata']['labels']['networking.knative.dev/visibility'] == 'cluster-local'
    assert 'networking.knative.dev/visibility' not in (ksvc['frontend']['metadata'].get('labels') or {})
    for svc in ksvc.values():
        template = svc['spec']['template']
        assert template['metadata']['annotations']['sidecar.istio.io/inject'] == 'false'
        assert len(template['metadata']['annotations']['checksum/runtime']) == 64
        assert 'initContainers' not in template['spec']
    env = ksvc['backend']['spec']['template']['spec']['containers'][0]['env']
    assert next(e for e in env if e['name'] == 'DB_URL')['valueFrom']['secretKeyRef']['key'] == 'DB_URL'
    configs = {d['metadata']['name']: d['data'] for d in docs if d['kind'] == 'ConfigMap'}
    assert 'backend-application' not in configs
    application_secret = next(d for d in docs if d['kind'] == 'Secret' and d['metadata']['name'] == 'backend-application')
    assert application_secret['type'] == 'Opaque'
    assert application_secret['stringData']['application.yaml'] == (ROOT / CHART / 'files/application.yaml').read_text()
    application_volume = next(v for v in ksvc['backend']['spec']['template']['spec']['volumes'] if v['name'] == 'application-config')
    assert application_volume['secret']['secretName'] == 'backend-application'
    assert 'configMap' not in application_volume
    host = f'backend.{namespace}.svc.cluster.local'
    assert f'set $backend_upstream {host};' in configs['frontend-nginx']['nginx.conf']
    assert 'proxy_pass http://$backend_upstream:80;' in configs['frontend-nginx']['nginx.conf']
    assert 'resolver kube-dns.kube-system.svc.cluster.local valid=10s ipv6=off;' in configs['frontend-nginx']['nginx.conf']
    assert f'proxy_set_header Host {host};' in configs['frontend-nginx']['nginx.conf']
    mapping = next(d for d in docs if d['kind'] == 'DomainMapping')
    cert = next(d for d in docs if d['kind'] == 'Certificate')
    assert mapping['spec']['tls']['secretName'] == cert['spec']['secretName']
    assert cert['spec']['dnsNames'] == [mapping['metadata']['name']]
    services = [d for d in docs if d['apiVersion'] == 'v1' and d['kind'] == 'Service']
    workloads = [d for d in docs if d['kind'] in ('StatefulSet', 'Deployment')]
    for svc in services:
        matches = [w for w in workloads if all(w['spec']['template']['metadata']['labels'].get(k) == v for k, v in svc['spec']['selector'].items())]
        assert len(matches) == 1
        ports = {p['name'] for c in matches[0]['spec']['template']['spec']['containers'] for p in c['ports']}
        assert all(p['targetPort'] in ports for p in svc['spec']['ports'])
    print(f'OK: Knative, rotas, TLS e Services em {namespace}')

for path in (ROOT / 'k8s').rglob('*.yaml'):
    documents = [d for d in yaml.safe_load_all(path.read_text()) if d]
    assert len(documents) == 1, f'Manifesto com múltiplos recursos: {path.name}'

platform = yaml.safe_load((ROOT / 'k8s/platform/knative-serving.yaml').read_text())
external_service = yaml.safe_load((ROOT / 'k8s/platform/istio-ingress-classic.yaml').read_text())
local_service = yaml.safe_load((ROOT / 'k8s/platform/knative-local-gateway.yaml').read_text())
for name, service in (('knative-ingress-gateway', external_service), ('knative-local-gateway', local_service)):
    assert platform['spec']['ingress']['istio'][name]['selector'] == service['spec']['selector']

base = render()
check(base, 'banco-srjm')
check(render('review', '-f', 'helm/values-eks.example.yaml', '--set', 'mailpit.enabled=false', '--set', 'storageClass.create=false'), 'review')
check(render('banco-srjm', '-f', 'helm/values-knative.example.yaml'), 'banco-srjm')


actual = {identity(d): d for d in base}
for filename in ('backend.yaml', 'frontend.yaml', 'postgres-config.yaml', 'backend-config.yaml', 'frontend-nginx.yaml',
                 'postgres.yaml', 'svc-postgres.yaml', 'svc-postgress-head.yaml',
                 'mailpit.yaml', 'svc-mailpit.yaml', 'storageclass.yaml', 'certificate.yaml', 'cluster-domain-claim.yaml', 'domain-mapping.yaml'):
    for expected in yaml.safe_load_all((ROOT / 'k8s' / filename).read_text()):
        if expected:
            assert normalized(actual[identity(expected)]) == normalized(expected), f'Divergência: {filename} / {identity(expected)}'
print('OK: paridade com os manifestos atuais de k8s/ (exceto metadados Helm/checksums)')

custom = render('banco-srjm', '--set', 'knative.backend.traffic[0].revisionName=backend-00003', '--set', 'knative.backend.traffic[0].percent=100', '--set', 'secrets.create=true', '--set', 'secrets.postgresPassword=test-only', '--set', 'secrets.dataEncryptionKey=test-only', '--set', 'secrets.administratorCreationToken=test-only', '--set', 'secrets.backendName=custom-backend')
backend = next(d for d in custom if identity(d) == ('serving.knative.dev/v1', 'Service', 'backend'))
assert backend['spec']['traffic'] == [{'revisionName': 'backend-00003', 'percent': 100}]
secret = next(d for d in custom if d['kind'] == 'Secret' and d['metadata']['name'] == 'custom-backend')
assert secret['stringData']['DB_URL'] == 'jdbc:postgresql://postgres:5432/banco_programacao'
assert next(e for e in backend['spec']['template']['spec']['containers'][0]['env'] if e['name'] == 'DB_URL')['valueFrom']['secretKeyRef']['name'] == 'custom-backend'
legacy = render('banco-srjm', '--set', 'knative.enabled=false', '--set', 'certManager.enabled=false')
assert not any(d['apiVersion'].startswith('serving.knative.dev/') for d in legacy)
assert {d['metadata']['name'] for d in legacy if d['kind'] == 'Deployment'} >= {'frontend', 'backend'}
print('OK: revisão fixa, Secrets customizados e modo Deployment opcional')

issuer_docs = render('banco-srjm', '-f', 'helm/values-dns01.example.yaml')
issuer = next(d for d in issuer_docs if d['kind'] == 'ClusterIssuer')
assert issuer == yaml.safe_load((ROOT / 'k8s/letsencrypt-production.yaml').read_text())
print('OK: ClusterIssuer DNS-01 corresponde ao manifesto k8s')
