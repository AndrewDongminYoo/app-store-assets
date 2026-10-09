"""Build-only app adapters; actual artifact inspection remains explicit."""
import tempfile
from contextlib import ExitStack
from pathlib import Path

from .commands import capture_provider_argv, executable_identity, expand_argv, run_command
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


def build(root, target, adapter, state, mode='live', allow_build=False, signing_file=None):
    exact_keys(adapter, {'argv', 'inputs', 'artifact', 'inspect_argv'}, ('argv', 'inputs', 'artifact'))
    if mode != 'fixture' and not adapter.get('inspect_argv'):
        raise ValueError('live artifact requires an explicit native inspection adapter')
    if mode != 'fixture' and allow_build is not True:
        raise ValueError('native build requires explicit local authority: allow_build')
    root = Path(root).resolve()
    source_inputs = inventory(root, adapter['inputs'])
    tool = executable_identity(adapter['argv'])
    inspector = executable_identity(adapter['inspect_argv']) if adapter.get('inspect_argv') else None
    source_commit = None
    if mode != 'fixture':
        source_commit = git(root, 'rev-parse', 'HEAD')
    with tempfile.TemporaryDirectory(prefix='store-build-') as temporary, ExitStack() as captures:
        folder = Path(temporary).resolve()
        inputs, output = folder / 'inputs', folder / 'output'
        output.mkdir()
        stage_inventory(root, inputs, source_inputs)
        approved = {str(safe_path(inputs, name)): digest for name, digest in source_inputs.items()}
        build_argv = capture_provider_argv(expand_argv(adapter['argv'], inputs, output=output), approved, roots=[inputs])
        captures.callback(build_argv.capture.close)
        inspect_argv = (capture_provider_argv(expand_argv(adapter['inspect_argv'], inputs, output=output), approved, roots=[inputs])
                        if adapter.get('inspect_argv') else None)
        if inspect_argv:
            captures.callback(inspect_argv.capture.close)
        request = {'schema_version': 1, 'action': 'build', 'target': target_identity(target),
                   'source_commit': source_commit, 'source_inputs': source_inputs,
                   'output': str(output), 'mode': mode, 'allow_build': allow_build,
                   'signing_file': signing_file}
        result = run_command(build_argv, request, inputs,
                             folder / 'home', expected=tool)
        verify_inventory(inputs, source_inputs, exact=True)
        if result.get('artifact') != adapter['artifact']:
            raise ValueError('build adapter artifact path differs')
        artifact = safe_path(output, result['artifact'])
        inspected_sha256 = file_digest(artifact)
        inspection = result.get('inspection', {})
        if adapter.get('inspect_argv'):
            inspection = run_command(inspect_argv,
                                     dict(request, action='inspect', artifact=str(artifact)), inputs, folder / 'home', expected=inspector)
        if file_digest(artifact) != inspected_sha256:
            raise ValueError('artifact changed during native inspection')
        verify_inventory(inputs, source_inputs, exact=True)
        for key in ('app_id', 'platform', 'flavor', 'version'):
            if inspection.get(key) != target[key]:
                raise ValueError(f'build native identity differs: {key}')
        if inspection.get('evidence') != ('fixture' if mode == 'fixture' else 'inspected'):
            raise ValueError('build inspection evidence differs from execution mode')
        guards = inspection.get('native_guards', {})
        if mode != 'fixture' and (not isinstance(guards, dict) or not guards or any(v is not True for v in guards.values())):
            raise ValueError('native release guard evidence is required')
        record = {'schema_version': 1, 'type': 'build', 'app_id': target['app_id'], 'platform': target['platform'],
                  'flavor': target['flavor'], 'version': target['version'], 'sha256': inspected_sha256,
                  'evidence': inspection['evidence'], 'native_guards': inspection.get('native_guards', {}),
                  'source_commit': source_commit, 'source_inputs': source_inputs, 'tool': tool, 'inspector': inspector,
                  'adapter': adapter, 'build_commands': result.get('commands', []),
                  'derived_policy': result.get('derived_policy'),
                  'native_tools': {'build': result.get('tools', {}), 'inspection': inspection.get('tools', {})}}
        return publish_snapshot(state, record, {adapter['artifact']: artifact},
                                expected_hashes={adapter['artifact']: inspected_sha256})
