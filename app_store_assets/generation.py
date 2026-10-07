"""Normalize app-composed inputs reproducibly within a locked toolchain."""
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from assets import image_info
from .catalog import CATALOG_FILE, encoded_format, slot_rule, validate_images
from .commands import executable_identity, expand_argv, run_command
from .execution import stage_inventory
from .environment import local_environment
from .identity import runtime_inventory
from .profiles import exact_keys, target_identity
from .records import file_digest, inventory, record_digest, safe_path, verify_inventory
from .snapshots import publish_snapshot, validate_snapshot


def toolchain(optimize=False):
    result = {'os': platform.system(), 'architecture': platform.machine()}
    with tempfile.TemporaryDirectory() as home:
        for tool, args in [('magick', ['-version'])] + ([('oxipng', ['--version'])] if optimize else []):
            executable = shutil.which(tool)
            if not executable:
                raise ValueError(f'missing local image tool: {tool}')
            output = subprocess.run([executable, *args], env=local_environment(home), capture_output=True,
                                    text=True, timeout=30, check=True)
            if tool == 'magick' and not output.stdout.startswith('Version: ImageMagick 7.'):
                raise ValueError('ImageMagick 7 is required')
            result[tool] = {'version': output.stdout.strip(), 'binary_sha256': file_digest(Path(executable).resolve())}
    return result


def generate(root, recipe, state):
    recipe = dict(recipe, target=target_identity(recipe['target']))
    exact_keys(recipe, {'schema_version', 'target', 'inputs', 'outputs', 'toolchain', 'provenance',
                        'normalize_alpha', 'optimize', 'composer'}, ('schema_version', 'target', 'inputs', 'outputs', 'toolchain', 'provenance'))
    if recipe['schema_version'] != 1 or not recipe['outputs']:
        raise ValueError('unsupported/empty generation recipe')
    provenance = recipe['provenance']
    if provenance.get('status') not in ('unverified-import', 'widget-rendered'):
        raise ValueError('native capture needs a separate verified capture-time build evidence adapter')
    locked = toolchain(recipe.get('optimize', False))
    if locked != recipe['toolchain']:
        raise ValueError('generation toolchain differs from lock; review a new recipe')
    root = Path(root).resolve()
    expected = inventory(root, recipe['inputs'])
    store = recipe['target']['store']
    with tempfile.TemporaryDirectory(prefix='asset-generation-') as temporary:
        scratch = Path(temporary)
        staged, output, home = scratch / 'inputs', scratch / 'outputs', scratch / 'home'
        home.mkdir()
        output.mkdir()
        stage_inventory(root, staged, expected)
        source_root, sources, composer_tool = staged, expected, None
        composed_inputs = {}
        if recipe.get('composer'):
            exact_keys(recipe['composer'], {'argv'}, ('argv',))
            composer_tool = executable_identity(recipe['composer']['argv'])
            source_root = scratch / 'composed'
            source_root.mkdir()
            response = run_command(expand_argv(recipe['composer']['argv'], staged, output=source_root),
                                   {'schema_version': 1, 'action': 'compose', 'root': str(staged),
                                    'output': str(source_root), 'target': target_identity(recipe['target'])},
                                   staged, home, expected=composer_tool)
            names = sorted({entry['source'] for entry in recipe['outputs']})
            if sorted(response.get('files', [])) != names:
                raise ValueError('composer output inventory differs from recipe')
            composed_inputs = inventory(source_root, names)
            verify_inventory(source_root, composed_inputs, exact=True)
            verify_inventory(staged, expected, exact=True)
            sources = composed_inputs
        assets = []
        for entry in recipe['outputs']:
            exact_keys(entry, {'source', 'file', 'locale', 'slot', 'background', 'size'}, ('source', 'file', 'locale', 'slot'))
            if entry['source'] not in sources:
                raise ValueError('generation source is outside declared inputs')
            source = safe_path(source_root, entry['source'])
            destination = safe_path(output, entry['file'])
            if destination.exists():
                raise ValueError('duplicate generation output')
            destination.parent.mkdir(parents=True, exist_ok=True)
            encoded_format(source)
            _, _, alpha = image_info(source, env=local_environment(home))
            rule = slot_rule(store, entry['slot'])
            command = [shutil.which('magick'), str(source)]
            if alpha and rule['alpha'] == 'forbidden':
                if not recipe.get('normalize_alpha'):
                    raise ValueError('alpha normalization requires explicit recipe policy')
                if entry.get('background'):
                    command += ['-background', entry['background'], '-alpha', 'remove']
                else:
                    opaque = subprocess.run([command[0], str(source), '-format', '%[opaque]', 'info:'],
                                            env=local_environment(home), capture_output=True, text=True, timeout=60, check=True)
                    if opaque.stdout.strip().lower() != 'true':
                        raise ValueError('transparent pixels require an explicit background')
            if entry.get('size'):
                width, height = entry['size']
                command += ['-resize', f'{int(width)}x{int(height)}!']
            if destination.suffix.lower() not in ('.png', '.jpg', '.jpeg'):
                raise ValueError('generation output must declare PNG/JPEG extension')
            coder = 'JPEG' if destination.suffix.lower() in ('.jpg', '.jpeg') else ('PNG32' if rule['alpha'] == 'required-rgba32' else 'PNG24')
            if coder == 'JPEG':
                command += ['-alpha', 'off', '-quality', '90', '-sampling-factor', '4:4:4']
            if coder == 'PNG24':
                command += ['-alpha', 'off']
            command += ['-strip', '-depth', '8', '-define', 'png:exclude-chunk=date,time', coder + ':' + str(destination)]
            rendered = subprocess.run(command, env=local_environment(home), capture_output=True, text=True, timeout=120)
            if rendered.returncode:
                raise ValueError('local image generation failed')
            if recipe.get('optimize') and coder != 'JPEG':
                optimized = subprocess.run([shutil.which('oxipng'), '--strip', 'safe', str(destination)],
                                           env=local_environment(home), capture_output=True, timeout=120)
                if optimized.returncode:
                    raise ValueError('local image optimization failed')
            assets.append({k: entry[k] for k in ('file', 'locale', 'slot')})
        validated = validate_images(output, assets, store)
        for item, entry in zip(validated, recipe['outputs'], strict=True):
            item['source_sha256'] = sources[entry['source']]
        record = {'schema_version': 1, 'type': 'asset-manifest', 'target': target_identity(recipe['target']),
                  'recipe_sha256': record_digest(recipe), 'recipe': recipe, 'inputs': expected, 'toolchain': locked,
                  'runtime': runtime_inventory(Path(__file__).resolve().parents[1]),
                  'catalog_sha256': file_digest(CATALOG_FILE), 'provenance': provenance, 'assets': validated,
                  'composer_tool': composer_tool, 'composed_inputs': composed_inputs}
        return publish_snapshot(state, record, {item['file']: output / item['file'] for item in validated})


def regenerate(root, recipe, expected_snapshot, state):
    original = validate_snapshot(expected_snapshot)
    expected = original['record']
    recipe = dict(recipe, target=target_identity(recipe['target']))
    if expected.get('type') != 'asset-manifest' or expected.get('target') != recipe['target']:
        raise ValueError('regeneration manifest target/type differs')
    current = {'recipe_sha256': record_digest(recipe), 'inputs': inventory(root, recipe['inputs']),
               'toolchain': toolchain(recipe.get('optimize', False)),
               'runtime': runtime_inventory(Path(__file__).resolve().parents[1]), 'catalog_sha256': file_digest(CATALOG_FILE)}
    if any(expected.get(k) != v for k, v in current.items()):
        raise ValueError('regeneration input/recipe/toolchain/runtime identity differs')
    actual_path = generate(root, recipe, state)
    if validate_snapshot(actual_path) != original:
        raise ValueError('regenerated manifest/final bytes/order/provenance differ')
    return {'status': 'verified', 'snapshot': actual_path, 'manifest_digest': record_digest(original)}
