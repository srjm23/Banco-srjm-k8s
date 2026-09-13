#!/usr/bin/env python3
import base64
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = 'eks-new'
PRIVATE = ROOT / '.secrets'
INIT = PRIVATE / 'vault-init.json'
SOURCES = [('banco-srjm', name) for name in ('postgres-secret', 'backend-secret', 'backend-application', 'frontend-secret', 'mailpit-secret')]
SOURCES.append(('cert-manager', 'cloudflare-api-token-secret'))


def kubectl(*args):
    return subprocess.check_output(['kubectl', '--context', CONTEXT, '--request-timeout=20s', *args], text=True)


def private_write(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(text)


def main():
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    PRIVATE.chmod(0o700)
    certificate = json.loads(kubectl('-n', 'vault', 'get', 'secret', 'vault-server-tls', '-o', 'json'))
    ca = base64.b64decode(certificate['data']['ca.crt']).decode()
    private_write(PRIVATE / 'vault-ca.crt', ca)
    ca_config = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'vault-ca', 'namespace': 'external-secrets'}, 'data': {'ca.crt': ca}}
    (ROOT / 'k8s/external-secrets/vault-ca.yaml').write_text(yaml.safe_dump(ca_config, sort_keys=False))
    tls = ssl.create_default_context(cadata=ca)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=tls))
    forward = subprocess.Popen(['kubectl', '--context', CONTEXT, '-n', 'vault', 'port-forward', 'pod/vault-0', '18200:8200'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    token = None

    def api(path, data=None, method=None, missing=False):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Vault-Token'] = token
        request = urllib.request.Request('https://127.0.0.1:18200/v1/' + path, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method or ('POST' if data is not None else 'GET'))
        try:
            with opener.open(request, timeout=20) as response:
                body = response.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            if missing and error.code == 404:
                return None
            raise RuntimeError(f'Vault HTTP {error.code} em {path}') from None

    try:
        for attempt in range(30):
            if forward.poll() is not None:
                raise RuntimeError('Port-forward encerrou; confira se a porta 18200 está livre.')
            try:
                status = api('sys/init')
                break
            except urllib.error.URLError:
                time.sleep(1)
        else:
            raise RuntimeError('Vault não respondeu ao port-forward.')
        if not status['initialized']:
            if INIT.exists():
                raise RuntimeError('Arquivo de bootstrap já existe para outro Vault. Não será sobrescrito.')
            initial = api('sys/init', {'secret_shares': 3, 'secret_threshold': 2}, method='PUT')
            private_write(INIT, json.dumps(initial))
            print('Vault inicializado; chaves guardadas em .secrets/vault-init.json.', flush=True)
        else:
            if not INIT.exists():
                raise RuntimeError('Vault já inicializado; arquivo de bootstrap não encontrado.')
            initial = json.loads(INIT.read_text())
        token = initial.get('root_token')
        if api('sys/seal-status')['sealed']:
            for key in initial['keys_base64'][:2]:
                api('sys/unseal', {'key': key})
        if api('sys/seal-status')['sealed']:
            raise RuntimeError('Vault continua selado.')
        print('Vault desbloqueado.', flush=True)
        if '--unseal' in sys.argv:
            return
        if '--verify-and-finalize' in sys.argv:
            for scope, allowed_namespace, forbidden in [('banco', 'banco-srjm', 'cert-manager/cloudflare-api-token-secret'), ('cert-manager', 'cert-manager', 'banco-srjm/backend-secret')]:
                account = 'vault-' + scope + '-reader'
                jwt = kubectl('-n', 'external-secrets', 'create', 'token', account, '--audience=vault', '--duration=10m').strip()
                token = api('auth/kubernetes/login', {'role': account, 'jwt': jwt})['auth']['client_token']
                for namespace, name in SOURCES:
                    if namespace != allowed_namespace:
                        continue
                    external = json.loads(kubectl('-n', namespace, 'get', 'externalsecret', name, '-o', 'json'))
                    if not any(c['type'] == 'Ready' and c['status'] == 'True' for c in external.get('status', {}).get('conditions', [])):
                        raise RuntimeError(f'ExternalSecret não está pronto: {namespace}/{name}')
                    secret = json.loads(kubectl('-n', namespace, 'get', 'secret', name, '-o', 'json'))
                    expected = {key: base64.b64decode(value).decode() for key, value in secret['data'].items()}
                    if api(f'secret/data/{namespace}/{name}')['data']['data'] != expected:
                        raise RuntimeError(f'Divergência na sincronização de {namespace}/{name}')
                    print(f'Sincronização verificada: {namespace}/{name}.', flush=True)
                try:
                    api('secret/data/' + forbidden)
                except RuntimeError as error:
                    if 'HTTP 403' not in str(error):
                        raise
                else:
                    raise RuntimeError('Política permitiu acesso cruzado indevido.')
                api('auth/token/revoke-self', {})
                token = None
                print(f'Isolamento de política verificado: {scope}.', flush=True)
            jwt = kubectl('-n', 'vault', 'create', 'token', 'vault-admin', '--audience=vault', '--duration=10m').strip()
            admin = api('auth/kubernetes/login', {'role': 'banco-vault-admin', 'jwt': jwt})['auth']['client_token']
            token = admin
            api('secret/data/banco-srjm/backend-secret')
            api('auth/token/revoke-self', {})
            if initial.get('root_token'):
                token = initial['root_token']
                api('auth/token/revoke-self', {})
                del initial['root_token']
                private_write(INIT, json.dumps(initial))
                print('Token root revogado e removido do arquivo de bootstrap.', flush=True)
            print('Acesso administrativo por autenticação Kubernetes validado.', flush=True)
            return
        if '--admin-token' in sys.argv:
            token = None
            jwt = kubectl('-n', 'vault', 'create', 'token', 'vault-admin', '--audience=vault', '--duration=10m').strip()
            admin = api('auth/kubernetes/login', {'role': 'banco-vault-admin', 'jwt': jwt})['auth']['client_token']
            private_write(PRIVATE / 'vault-admin-token', admin)
            print('Token administrativo temporário guardado em .secrets/vault-admin-token.', flush=True)
            return
        if not token:
            raise RuntimeError('Bootstrap concluído anteriormente; use --unseal, --admin-token ou --verify-and-finalize.')
        mounts = api('sys/mounts')['data']
        if 'secret/' not in mounts:
            api('sys/mounts/secret', {'type': 'kv', 'options': {'version': '2'}})
        elif mounts['secret/'].get('options', {}).get('version') != '2':
            raise RuntimeError('O mount secret existente não é KV v2.')
        auth = api('sys/auth')['data']
        if 'kubernetes/' not in auth:
            api('sys/auth/kubernetes', {'type': 'kubernetes'})
        api('auth/kubernetes/config', {'kubernetes_host': 'https://kubernetes.default.svc:443', 'disable_local_ca_jwt': False, 'disable_iss_validation': True})
        for scope, prefix in [('banco', 'banco-srjm/*'), ('cert-manager', 'cert-manager/cloudflare-api-token-secret')]:
            role = 'vault-' + scope + '-reader'
            policy = f'path "secret/data/{prefix}" {{ capabilities = ["read"] }}'
            api('sys/policies/acl/' + role, {'policy': policy}, method='PUT')
            api('auth/kubernetes/role/' + role, {'bound_service_account_names': [role], 'bound_service_account_namespaces': ['external-secrets'], 'audience': 'vault', 'token_policies': [role], 'token_ttl': '1h', 'token_max_ttl': '1h'})
        admin_policy = '\n'.join(f'path "secret/{section}/{scope}/*" {{ capabilities = ["create", "read", "update", "delete", "list"] }}' for section in ('data', 'metadata', 'delete', 'undelete', 'destroy') for scope in ('banco-srjm', 'cert-manager'))
        api('sys/policies/acl/banco-vault-admin', {'policy': admin_policy}, method='PUT')
        api('auth/kubernetes/role/banco-vault-admin', {'bound_service_account_names': ['vault-admin'], 'bound_service_account_namespaces': ['vault'], 'audience': 'vault', 'token_policies': ['banco-vault-admin'], 'token_ttl': '15m', 'token_max_ttl': '1h'})
        for namespace, name in SOURCES:
            secret = json.loads(kubectl('-n', namespace, 'get', 'secret', name, '-o', 'json'))
            values = {key: base64.b64decode(value, validate=True).decode() for key, value in secret['data'].items()}
            path = f'secret/data/{namespace}/{name}'
            existing = api(path, missing=True)
            if existing is None:
                api(path, {'options': {'cas': 0}, 'data': values})
            elif existing['data']['data'] != values:
                raise RuntimeError(f'Valores divergentes em {namespace}/{name}; nenhum sobrescrito.')
            if api(path)['data']['data'] != values:
                raise RuntimeError(f'Falha na verificação de {namespace}/{name}.')
            print(f'Migrado e conferido: {namespace}/{name}.', flush=True)
        print('Bootstrap concluído. Validar ExternalSecrets antes de revogar o token inicial.', flush=True)
    finally:
        forward.terminate()
        forward.wait(timeout=10)


if __name__ == '__main__':
    main()
