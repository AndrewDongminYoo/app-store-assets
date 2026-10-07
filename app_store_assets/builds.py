"""Build-only app adapters; actual artifact inspection remains explicit."""
import tempfile
from pathlib import Path

from .commands import executable_identity, expand_argv, run_command
from .execution import stage_inventory
from .identity import git
from .profiles import exact_keys, target_identity
from .records import file_digest, inventory, safe_path, verify_inventory
from .snapshots import publish_snapshot


def flutter_argv(platform, flavor, version):
    if platform not in ('android', 'ios'):
        raise ValueError('unsupported Flutter store platform')
    return ['flutter', 'build', 'appbundle' if platform == 'android' else 'ipa', '--flavor', flavor,
            '--release', '--build-name', str(version['name']), '--build-number', str(version['build']), '--no-pub']


def godot_argv(executable, preset, output, root):
    return [executable, '--headless', '--path', str(root), '--export-release', preset, str(output)]


def build(root, target, adapter, state, mode='live'):
    exact_keys(adapter, {'argv', 'inputs', 'artifact', 'inspect_argv'}, ('argv', 'inputs', 'artifact'))
    if mode != 'fixture' and not adapter.get('inspect_argv'):
        raise ValueError('live artifact requires an explicit native inspection adapter')
    root = Path(root).resolve()
    source_inputs = inventory(root, adapter['inputs'])
    tool = executable_identity(adapter['argv'])
    inspector = executable_identity(adapter['inspect_argv']) if adapter.get('inspect_argv') else None
    source_commit = None
    if mode != 'fixture':
        source_commit = git(root, 'rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory(prefix='store-build-') as temporary:
        folder = Path(temporary)
        inputs, output = folder / 'inputs', folder / 'output'
        output.mkdir()
        stage_inventory(root, inputs, source_inputs)
        request = {'schema_version': 1, 'action': 'build', 'target': target_identity(target),
                   'source_commit': source_commit, 'output': str(output), 'mode': mode}
        result = run_command(expand_argv(adapter['argv'], inputs, output=output), request, inputs,
                             folder / 'home', expected=tool)
        verify_inventory(inputs, source_inputs, exact=True)
        if result.get('artifact') != adapter['artifact']:
            raise ValueError('build adapter artifact path differs')
        artifact = safe_path(output, result['artifact'])
        inspection = result.get('inspection', {})
        if adapter.get('inspect_argv'):
            inspection = run_command(expand_argv(adapter['inspect_argv'], inputs, output=output),
                                     dict(request, action='inspect', artifact=str(artifact)), inputs, folder / 'home', expected=inspector)
        for key in ('app_id', 'platform', 'flavor', 'version'):
            if inspection.get(key) != target[key]:
                raise ValueError(f'build native identity differs: {key}')
        if inspection.get('evidence') != ('fixture' if mode == 'fixture' else 'inspected'):
            raise ValueError('build inspection evidence differs from execution mode')
        guards = inspection.get('native_guards', {})
        if mode != 'fixture' and (not isinstance(guards, dict) or not guards or any(v is not True for v in guards.values())):
            raise ValueError('native release guard evidence is required')
        record = {'schema_version': 1, 'type': 'build', 'app_id': target['app_id'], 'platform': target['platform'],
                  'flavor': target['flavor'], 'version': target['version'], 'sha256': file_digest(artifact),
                  'evidence': inspection['evidence'], 'native_guards': inspection.get('native_guards', {}),
                  'source_commit': source_commit, 'source_inputs': source_inputs, 'tool': tool, 'inspector': inspector,
                  'adapter': adapter}
        return publish_snapshot(state, record, {adapter['artifact']: artifact})
