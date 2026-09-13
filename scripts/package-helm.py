#!/usr/bin/env python3
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ('banco', 'backend', 'frontend')


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def render(chart, component):
    return list(yaml.safe_load_all(subprocess.check_output(['helm', 'template', component, str(chart), '-n', 'banco-srjm'], cwd=ROOT, text=True)))


def main():
    parser = argparse.ArgumentParser(description='Valida, renderiza e empacota os três charts da aplicação.')
    parser.add_argument('--url', default='https://srjm23.github.io/Banco-srjm-k8s/', help='URL HTTP(S) pública da pasta que receberá index.yaml e os pacotes.')
    args = parser.parse_args()
    if args.url and not args.url.startswith(('https://', 'http://')):
        parser.error('--url precisa usar HTTP ou HTTPS')
    charts = [ROOT / 'helm/charts' / ('banco-srjm-' + component) for component in COMPONENTS]
    repository = ROOT / 'helm/repository'
    rendered = ROOT / 'build/helm-rendered'
    repository.mkdir(parents=True, exist_ok=True)
    rendered.mkdir(parents=True, exist_ok=True)
    run('helm', 'lint', *map(str, charts), '--strict')
    run(sys.executable, 'scripts/validate-helm.py')
    packages = []
    for component, chart in zip(COMPONENTS, charts):
        metadata = yaml.safe_load((chart / 'Chart.yaml').read_text())
        run('helm', 'template', component, str(chart), '-n', 'banco-srjm', '--output-dir', str(rendered))
        run('helm', 'package', str(chart), '--destination', str(repository))
        package = repository / (metadata['name'] + '-' + metadata['version'] + '.tgz')
        if render(chart, component) != render(package, component):
            raise RuntimeError('Pacote diverge do chart: ' + package.name)
        packages.append(package)
    arguments = ['helm', 'repo', 'index', str(repository)]
    if args.url:
        arguments.extend(['--url', args.url.rstrip('/')])
    run(*arguments)
    index = yaml.safe_load((repository / 'index.yaml').read_text())
    for chart, package in zip(charts, packages):
        metadata = yaml.safe_load((chart / 'Chart.yaml').read_text())
        entry = next(item for item in index['entries'][metadata['name']] if item['version'] == metadata['version'])
        if entry['digest'] != hashlib.sha256(package.read_bytes()).hexdigest():
            raise RuntimeError('Digest incorreto no index: ' + package.name)
        expected_url = args.url.rstrip('/') + '/' + package.name if args.url else package.name
        if entry['urls'] != [expected_url]:
            raise RuntimeError('URL incorreta no index: ' + package.name)
    print('OK: três pacotes conferidos, index.yaml com URLs válidas e digests SHA-256 corretos.')


if __name__ == '__main__':
    main()
