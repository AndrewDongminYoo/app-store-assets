"""Stage reviewed bytes before remote lookup; preserve precise attempt state."""
import os
import fcntl
import shutil
import uuid
from pathlib import Path

from .planning import verify_plan
from .records import canonical, file_digest, read_json, record_digest, safe_path, verify_inventory

ATTEMPT_STATE = 'build/store-assets'


def write_record(path, value):
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    temporary.write_bytes(canonical(value))
    temporary.replace(path)


def stage_inventory(source, destination, expected):
    destination.mkdir(parents=True)
    for name, digest in expected.items():
        original = safe_path(source, name)
        target = safe_path(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target, follow_symlinks=False)
        if file_digest(target) != digest:
            raise ValueError(f'input changed while staging: {name}')
        target.chmod(0o444)
    verify_inventory(destination, expected, exact=True)


def preflight(payload, observed):
    expected = payload['remote']
    if expected is None:
        raise ValueError('remote target is unverified; download a snapshot and re-plan')
    if observed.get('target') != payload['target']:
        raise ValueError('remote snapshot target/version differs from plan')
    if record_digest(observed) != record_digest(expected):
        raise ValueError('remote snapshot revision/state changed; re-plan')
    if payload['target']['store'] == 'apple' and payload['operation'] in ('metadata', 'images'):
        if not expected.get('version_id') or not observed.get('editable'):
            raise ValueError('Apple listing requires the exact existing editable version ID')
        if observed.get('review_active'):
            raise ValueError('active Apple review blocks listing replacement')
    if payload['operation'] == 'images':
        local = (payload['listing'] or {}).get('images', {})
        policy = payload.get('replacement')
        if not policy or not local:
            raise ValueError('image replacement requires explicit nonempty inventory and policy')
        local_groups = {(locale, slot) for locale, slots in local.items() for slot in slots}
        remote_groups = {(locale, slot) for locale, slots in observed.get('images', {}).items()
                         for slot, images in slots.items() if images}
        if remote_groups - local_groups:
            raise ValueError('remote screenshot class/locale would be omitted by replacement')
        if remote_groups and policy.get('allow_delete') is not True:
            raise ValueError('deleting existing screenshots requires explicit reviewed allow_delete policy')
        if {locale for locale, _ in local_groups} != set(policy.get('locales', [])):
            raise ValueError('replacement locale policy differs from inventory')
        if {slot for _, slot in local_groups} != set(policy.get('slots', [])):
            raise ValueError('replacement class policy differs from inventory')


def readback_matches(payload, report, result):
    if report.get('target') != payload['target']:
        return False
    observed = report.get('observed', {})
    if payload['operation'] == 'binary':
        binary = observed.get('binary') or {}
        if binary.get('app_id') != payload['target']['app_id'] or binary.get('version') != payload['target']['version']:
            return False
        if binary.get('platform') != payload['target']['platform']:
            return False
        if binary.get('processing_state') != 'processed':
            return False
        if binary.get('source_sha256') is not None and binary['source_sha256'] != payload['build']['sha256']:
            return False
        if payload['target']['store'] == 'google' and observed.get('release_status') != payload['release_status']:
            return False
        return observed.get('release_notes', {}) == payload['release_notes']
    if payload['operation'] == 'metadata':
        actual = observed.get('fields', {})
        expected = (payload['listing'] or {}).get('fields', {})
        return all(actual.get(locale, {}).get(key) == value for locale, fields in expected.items()
                   for key, value in fields.items())
    expected = (payload['listing'] or {}).get('images', {})
    actual = observed.get('images', {})
    expected_groups = {(locale, slot) for locale, groups in expected.items()
                       for slot, images in groups.items() if images}
    actual_groups = {(locale, slot) for locale, groups in actual.items()
                     for slot, images in groups.items() if images}
    if actual_groups != expected_groups:
        return False
    uploaded = result.get('image_ids', {})
    for locale, groups in expected.items():
        for slot, images in groups.items():
            seen = actual.get(locale, {}).get(slot, [])
            if len(seen) != len(images):
                return False
            checksums = [item.get('source_sha256') for item in seen]
            if all(checksums):
                if checksums != [item['sha256'] for item in images]:
                    return False
            elif uploaded.get(locale, {}).get(slot) != [item.get('id') for item in seen]:
                return False
            if any(item.get('processing_state') != 'processed' for item in seen):
                return False
    return True


def execute(root, plan, expected_digest, provider, state, dry_run=False):
    if expected_digest != plan.get('digest'):
        raise ValueError('expected digest differs from reviewed plan')
    verify_plan(root, plan)
    payload = plan['payload']
    if dry_run:
        return {'status': 'dry-run', 'digest': plan['digest'], 'effects': payload['effects']}
    raw_root, raw_state = Path(os.path.abspath(root)), Path(os.path.abspath(state))
    root = raw_root.resolve()
    if not raw_state.is_relative_to(raw_root):
        raise ValueError('attempt state must stay inside the project workspace')
    state = safe_path(root, raw_state.relative_to(raw_root).as_posix())
    if state != safe_path(root, ATTEMPT_STATE):
        raise ValueError(f'execution requires canonical attempt state: {ATTEMPT_STATE}')
    for name in payload['input_paths']:
        source = safe_path(root, name)
        if state == source or (source.is_dir() and state.is_relative_to(source)):
            raise ValueError('attempt state overlaps bound source inputs')
    state.mkdir(parents=True, exist_ok=True)
    locks = state / 'locks'
    attempts = state / 'attempts'
    locks.mkdir(exist_ok=True)
    attempts.mkdir(exist_ok=True)
    def target_key(target):
        return record_digest({'account': target.get('account_id') or target['account'],
                              **{k: target[k] for k in ('app_id', 'store', 'platform')}})
    key = target_key(payload['target'])
    lock = safe_path(root, (locks / (key + '.lock')).relative_to(root).as_posix())
    handle = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('concurrent target execution lock exists') from None
        os.ftruncate(handle, 0)
        os.write(handle, canonical({'pid': os.getpid(), 'digest': plan['digest']}))
        for file in attempts.glob('*/receipt.json'):
            prior = read_json(file)
            if prior.get('effects_started') and target_key(prior['target']) == key and prior.get('status') != 'verified':
                raise ValueError('target has a pending/partial transfer; verify it before a recovery plan')
            if prior.get('digest') == plan['digest'] and prior.get('effects_started'):
                raise ValueError('plan already has an attempted/pending transfer; verify or make a recovery plan')
        attempt = attempts / uuid.uuid4().hex
        attempt.mkdir()
        receipt = {'schema_version': 1, 'type': 'receipt', 'digest': plan['digest'], 'target': payload['target'],
                   'effects': payload['effects'], 'effects_started': False, 'status': 'staging',
                   'attempt': attempt.name}
        write_record(attempt / 'plan.json', plan)
        write_record(attempt / 'receipt.json', receipt)
        try:
            inputs = attempt / 'inputs'
            runtime = attempt / 'runtime'
            stage_inventory(root, inputs, payload['inputs'])
            stage_inventory(safe_path(root, payload['runtime_path']), runtime, payload['runtime']['files'])
            # A command provider gets only the staged package and project paths.
            if hasattr(provider, 'bind_stage'):
                provider.bind_stage(inputs, runtime)
            preflight(payload, provider.snapshot(payload['target']))
            verify_inventory(inputs, payload['inputs'], exact=True)
            verify_inventory(runtime, payload['runtime']['files'], exact=True)
            preflight(payload, provider.snapshot(payload['target']))
            receipt['status'] = 'transferring'
            receipt['effects_started'] = True
            write_record(attempt / 'receipt.json', receipt)
            result = provider.upload(plan, inputs)
            if result.get('accepted') is not True:
                raise ValueError('provider did not confirm acceptance')
            verify_inventory(inputs, payload['inputs'], exact=True)
            verify_inventory(runtime, payload['runtime']['files'], exact=True)
            receipt['status'] = 'accepted_pending_verification'
            receipt['provider_result'] = {k: result[k] for k in ('accepted', 'remote_ids', 'image_ids') if k in result}
            write_record(attempt / 'receipt.json', receipt)
            try:
                report = provider.readback(plan, result)
                if readback_matches(payload, report, result):
                    receipt['status'] = 'verified'
            except (ValueError, OSError, RuntimeError, KeyError, TypeError):
                # Acceptance and processing evidence are separate. Preserve pending.
                receipt['verification_error'] = 'provider-readback-failed'
            write_record(attempt / 'receipt.json', receipt)
            return receipt
        except BaseException as error:
            receipt['status'] = 'failed_partial' if receipt['effects_started'] else 'failed_preflight'
            receipt['error_type'] = type(error).__name__
            write_record(attempt / 'receipt.json', receipt)
            raise
    finally:
        # Keep the inode stable: unlinking lets another process lock a different
        # inode under the same pathname. The OS releases ownership on close/exit.
        os.close(handle)
