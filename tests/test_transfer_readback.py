"""U3 invariants 1, 3, 6, 8 and 9 through the real Ruby/Python boundary."""

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from offline_support import ROOT, fixture, module, write_json
from test_assets import png
from test_offline_boundaries import snapshot_fixture
import test_snapshot_export as snapshot_test
from test_snapshot_export import FAKE, LIB, READS, scenario, shot, version_of

HARNESS = ROOT / "tests/transfer_readback_harness.rb"


class TransferReadbackTests(unittest.TestCase):
    def setUp(self):
        self.exporter = snapshot_test.SnapshotExportTests()
        self.exporter.setUp()
        self.addCleanup(self.exporter.doCleanups)
        self.tmp = self.exporter.tmp
        self.stage_parent = self.tmp / "staging"
        self.stage_parent.mkdir(mode=0o700)
        self.root, self.profile = fixture(self)
        self.target = self.profile["targets"]["production"]
        self.target["app_id"] = "com.example.transfer." + hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        self.identity = module("profiles").target_identity(self.target)
        self.lock = Path("/tmp").resolve() / ("app-store-assets-transfer-" + hashlib.sha256(self.identity["app_id"].encode()).hexdigest() + ".lock")
        self.data = scenario()
        self.data["app"]["bundle_id"] = self.identity["app_id"]
        version = version_of(self.data)
        version["version_string"] = self.identity["version"]["name"]
        version["build"]["version"] = self.identity["version"]["build"]
        version["localizations"][0]["sets"][0]["screenshot_display_type"] = "APP_IPHONE_65"
        version["localizations"][1]["sets"][0]["screenshot_display_type"] = "APP_IPHONE_65"
        version["localizations"][1]["sets"].append({
            "id": "ko-ipad", "screenshot_display_type": "APP_IPAD_PRO_3GEN_129",
            "screenshots": [shot("ko-ipad-shot", width=2048, height=2732)],
        })
        self.remote, _, _ = self.exporter.export(self.data, identity=self.identity)
        images = {"en-US/01.png": png(), "ko/01.png": png(2048, 2732)}
        entries = [
            {"file": name, "sha256": hashlib.sha256(data).hexdigest(), "locale": locale, "slot": slot}
            for (name, data), locale, slot in zip(images.items(), ("en-US", "ko"), ("APP_IPHONE_65", "APP_IPAD_PRO_3GEN_129"))
        ]
        record = {"schema_version": 1, "type": "asset-manifest", "target": self.identity,
                  "assets": entries, "provenance": {"status": "unverified-import"}}
        directory = snapshot_fixture(self.root / "state/assets", record, images)
        listing = {"schema_version": 1, "type": "metadata", "target": self.identity, "images": {}}
        self.sources = []
        for entry in entries:
            source = directory / entry["file"]
            self.sources.append(source)
            listing["images"].setdefault(entry["locale"], {})[entry["slot"]] = [{
                "file": str(source.relative_to(self.root)), "sha256": entry["sha256"],
            }]
        self.target["assets"] = {"manifest": str(directory.relative_to(self.root) / "manifest.json")}
        self.target["replacement"] = {"locales": ["en-US", "ko"], "slots": ["APP_IPHONE_65", "APP_IPAD_PRO_3GEN_129"], "allow_delete": False}
        write_json(self.root / "metadata/listing.json", listing)
        write_json(self.root / "store-upload.json", self.profile)
        self.prepare_plan()

    def prepare_plan(self):
        write_json(self.root / "remote.json", self.remote)
        self.plan = module("planning").make_plan(self.root, "store-upload.json", "production", "images")
        self.approval = {"schema_version": 1, "type": "transfer-approval", "target": self.identity,
                         "plan_digest": self.plan["digest"], "operation": "images"}
        write_json(self.root / "plan.json", self.plan)
        write_json(self.root / "approval.json", self.approval)

    def run_readback(self, data=None, identity=None, options=None, extra_env=None):
        write_json(self.tmp / "scenario.json", self.data if data is None else data)
        log = self.tmp / "readback-calls.json"
        log.unlink(missing_ok=True)
        env = {"PATH": os.environ["PATH"], "HOME": str(self.tmp / "home"), "LANG": "C.UTF-8",
               "TMPDIR": str(self.stage_parent), "PYTHON": sys.executable,
               "FAKE_ASC_SCENARIO": str(self.tmp / "scenario.json"), "FAKE_ASC_LOG": str(log), **(extra_env or {})}
        result = subprocess.run([
            "ruby", "--disable-gems", "-I", str(FAKE), str(HARNESS), str(LIB), str(self.root),
            json.dumps(self.identity if identity is None else identity), json.dumps(options or {}),
        ], capture_output=True, text=True, env=env, timeout=30)
        calls = json.loads(log.read_text()) if log.exists() else []
        self.assertEqual([c for c in calls if c["call"] not in READS], [], calls)
        return result, calls

    def assert_clean(self):
        self.assertEqual(list(self.stage_parent.iterdir()), [])
        self.assertFalse(self.lock.exists())

    def assert_refused(self, result, text):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.stdout, "")
        self.assertIn(text, result.stderr)
        self.assert_clean()

    def test_invariants_3_and_8_readback_has_only_declared_pairs_and_preserved_sets(self):
        before = set(self.root.rglob("*"))
        result, calls = self.run_readback()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertEqual(report["plan_digest"], self.plan["digest"])
        self.assertEqual(report["target"], self.identity)
        self.assertEqual(report["mode"], "read-only")
        self.assertTrue(report["remote_verified"])
        self.assertEqual([(g["locale"], g["slot"]) for g in report["groups"]],
                         [("en-US", "APP_IPHONE_65"), ("ko", "APP_IPAD_PRO_3GEN_129")])
        self.assertEqual(report["groups"][0]["remote_screenshot_ids"], ["shot-b", "shot-a"])
        self.assertTrue(all(g["action"] == "verify" and g["readback"]["snapshot_matches"] for g in report["groups"]))
        self.assertEqual(set(report["preserved_sets"]["en-US"]), {"APP_IPAD_PRO_3GEN_129"})
        self.assertEqual(set(report["preserved_sets"]["ko"]), {"APP_IPHONE_65"})
        self.assertEqual(report["provenance"], {"status": "unverified-import"})
        self.assertIn("AppStoreVersion#get_build", [c["call"] for c in calls])
        self.assertEqual(set(self.root.rglob("*")), before)
        self.assert_clean()

    def test_invariant_3_refuses_changed_version_build_or_review_state(self):
        changes = [
            lambda d: version_of(d).update(id="different-version"),
            lambda d: version_of(d).update(app_version_state="READY_FOR_DISTRIBUTION"),
            lambda d: d["app"].update(review_submission=True),
            lambda d: version_of(d)["build"].update(version="99"),
            lambda d: version_of(d).update(build=None),
        ]
        for index, change in enumerate(changes):
            with self.subTest(case=index):
                data = copy.deepcopy(self.data)
                change(data)
                result, _ = self.run_readback(data)
                self.assert_refused(result, "en-US/APP_IPHONE_65")

    def test_invariant_3_refuses_changed_id_order_dimensions_and_processing(self):
        for field, value in (("id", "changed-id"), ("image_asset", {"width": 1, "height": 1}),
                             ("asset_delivery_state", {"state": "FAILED"})):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                version_of(data)["localizations"][0]["sets"][0]["screenshots"][0][field] = value
                result, _ = self.run_readback(data)
                self.assert_refused(result, "en-US/APP_IPHONE_65")
        data = copy.deepcopy(self.data)
        version_of(data)["localizations"][0]["sets"][0]["screenshots"].reverse()
        result, _ = self.run_readback(data)
        self.assert_refused(result, "en-US/APP_IPHONE_65")

    def test_invariant_3_requires_a_live_build_even_when_snapshot_omits_binary(self):
        self.remote.pop("binary")
        self.prepare_plan()
        data = copy.deepcopy(self.data)
        version_of(data)["build"] = None
        result, _ = self.run_readback(data)
        self.assert_refused(result, "approved attached build")

    def test_invariant_3_distinguishes_an_absent_set_from_an_empty_set(self):
        data = copy.deepcopy(self.data)
        version_of(data)["localizations"][0]["sets"].pop(0)
        result, _ = self.run_readback(data)
        self.assert_refused(result, "en-US/APP_IPHONE_65")
        self.remote["images"]["en-US"].pop("APP_IPHONE_65")
        self.prepare_plan()
        result, _ = self.run_readback(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["groups"][0]["remote_screenshot_ids"], [])
        self.assert_clean()
        version_of(data)["localizations"][0]["sets"].append({"id": "empty", "screenshot_display_type": "APP_IPHONE_65", "screenshots": []})
        result, _ = self.run_readback(data)
        self.assert_refused(result, "en-US/APP_IPHONE_65")

    def test_invariant_3_refuses_snapshot_fields_without_a_live_mapping(self):
        for key in ("revision", "binary.source_sha256"):
            with self.subTest(key=key):
                remote = copy.deepcopy(self.remote)
                if key == "revision":
                    self.remote[key] = "unmapped revision"
                else:
                    self.remote["binary"]["source_sha256"] = "0" * 64
                self.prepare_plan()
                result, _ = self.run_readback()
                self.assert_refused(result, "live mapping")
                self.remote = remote

    def test_invariant_3_compares_supplied_metadata_fields_without_echoing_values(self):
        data = copy.deepcopy(self.data)
        version_of(data)["localizations"][0]["support_url"] = "https://example.com/changed"
        result, _ = self.run_readback(data)
        self.assert_refused(result, "fields.en-US.support_url")
        self.assertNotIn("https://example.com/changed", result.stderr)

    def test_invariant_3_maps_optional_build_presence_and_selected_notes(self):
        self.remote["build_exists"] = True
        self.remote["release_notes"] = {"en-US": "Fixes"}
        self.prepare_plan()
        result, _ = self.run_readback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_clean()

    def test_invariant_3_requires_snapshot_screenshot_ids(self):
        self.remote["images"]["en-US"]["APP_IPHONE_65"][0].pop("id")
        self.prepare_plan()
        result, _ = self.run_readback()
        self.assert_refused(result, "screenshot IDs are required")

    def test_invariant_1_existing_lock_refuses_before_local_verification_and_provider_reads(self):
        self.lock.write_text("operator-owned existing lock")
        self.addCleanup(self.lock.unlink)
        write_json(self.root / "approval.json", {})
        result, calls = self.run_readback()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lock exists", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(calls, [])
        self.assertEqual(self.lock.read_text(), "operator-owned existing lock")
        self.assertEqual(list(self.stage_parent.iterdir()), [])

    def test_invariant_1_target_and_approval_mismatches_never_reach_spaceship(self):
        result, calls = self.run_readback(identity=dict(self.identity, account_id="other-team"))
        self.assert_refused(result, "target")
        self.assertEqual(calls, [])
        write_json(self.root / "approval.json", dict(self.approval, plan_digest="0" * 64))
        result, calls = self.run_readback()
        self.assert_refused(result, "verification")
        self.assertEqual(calls, [])

    def test_invariant_1_concurrent_run_refuses_while_first_run_holds_lock(self):
        data = copy.deepcopy(self.data)
        data["hang"] = {"call": "App.find", "seconds": 3}
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.run_readback, data, options={"deadline": 1})
            until = time.monotonic() + 3
            while not self.lock.exists() and time.monotonic() < until:
                time.sleep(0.01)
            self.assertTrue(self.lock.exists())
            owner = self.lock.read_text()
            result, calls = self.run_readback(data)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lock exists", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(calls, [])
            self.assertEqual(self.lock.read_text(), owner)
            result, _ = first.result(timeout=10)
            self.assert_refused(result, "deadline")

    def test_invariant_1_replaced_lock_is_refused_without_removing_the_replacement(self):
        foreign = self.tmp / "foreign-lock"
        foreign.write_text("keep another writer's file")
        data = copy.deepcopy(self.data)
        data["swap_directory"] = {"during": "App.find", "path": str(self.lock),
                                  "moved_to": str(self.tmp / "moved-lock"), "replacement": str(foreign)}
        self.addCleanup(lambda: self.lock.unlink(missing_ok=True))
        result, _ = self.run_readback(data)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("lock changed", result.stderr)
        self.assertTrue(self.lock.is_symlink())
        self.assertEqual(foreign.read_text(), "keep another writer's file")
        self.assertEqual(list(self.stage_parent.iterdir()), [])

    def test_invariant_6_bounds_a_provider_retry_and_cleans_up(self):
        data = copy.deepcopy(self.data)
        data["hang"] = {"call": "App.find", "seconds": 3}
        start = time.monotonic()
        result, calls = self.run_readback(data, options={"deadline": 0.15})
        self.assert_refused(result, "deadline")
        self.assertLess(time.monotonic() - start, 2.5)
        self.assertEqual(calls[0]["call"], "App.find")

    def test_invariant_1_cleanup_preserves_a_substituted_staging_directory(self):
        log = self.tmp / "stage-swap.json"
        result, _ = self.run_readback(extra_env={"FAKE_TRANSFER_SWAP_STAGE": str(log)})
        directory = Path(json.loads(log.read_text())["directory"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertTrue((directory / "marker").exists(), "cleanup deleted foreign staging content")
        self.assertEqual((directory / "marker").read_text(), "foreign staging content")
        self.assertFalse(self.lock.exists())

    def test_invariant_1_cleanup_preserves_a_lock_swapped_after_its_inode_check(self):
        log = self.tmp / "lock-swap.json"
        result, _ = self.run_readback(extra_env={"FAKE_TRANSFER_SWAP_LOCK": str(log)})
        record = json.loads(log.read_text())
        retained = Path(record["retained"])
        self.addCleanup(lambda: self.lock.unlink(missing_ok=True))
        if retained != self.lock:
            self.addCleanup(shutil.rmtree, retained.parent)
        self.assertTrue(retained.exists(), "cleanup deleted a lock substituted after lstat")
        self.assertEqual(retained.read_text(), "foreign lock content")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("retained", result.stderr)

    def test_invariant_6_bounds_the_local_verifier_process(self):
        program = self.tmp / "slow-python"
        program.write_text("#!/bin/sh\nsleep 5\n")
        program.chmod(0o700)
        start = time.monotonic()
        result, calls = self.run_readback(options={"verification_deadline": 0.15}, extra_env={"PYTHON": str(program)})
        self.assert_refused(result, "deadline")
        self.assertLess(time.monotonic() - start, 2)
        self.assertEqual(calls, [])

    def test_invariant_6_bounds_local_verifier_output(self):
        program = self.tmp / "verbose-python"
        program.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.write('x' * (9 * 1024 * 1024))\n")
        program.chmod(0o700)
        result, calls = self.run_readback(extra_env={"PYTHON": str(program)})
        self.assert_refused(result, "byte bound")
        self.assertEqual(calls, [])

    def test_invariant_6_kills_verifier_descendants_after_the_parent_exits(self):
        marker = self.tmp / "surviving-child"
        parent_exit = self.tmp / "parent-exited"
        child = f"import time; from pathlib import Path; time.sleep(2); Path({str(marker)!r}).write_text('survived')"
        program = self.tmp / "forking-python"
        program.write_text(f"#!{sys.executable}\nimport os, subprocess, sys\nfrom pathlib import Path\nsubprocess.Popen([sys.executable, '-c', {child!r}])\nPath({str(parent_exit)!r}).write_text('exiting')\nos._exit(0)\n")
        program.chmod(0o700)
        result, calls = self.run_readback(options={"verification_deadline": 0.5}, extra_env={"PYTHON": str(program)})
        self.assert_refused(result, "deadline")
        self.assertEqual(calls, [])
        self.assertTrue(parent_exit.exists(), "fixture did not reach the parent exit")
        time.sleep(2.1)
        self.assertFalse(marker.exists(), "verifier child survived after its parent exited")

    def test_invariant_6_refuses_invalid_deadlines_before_provider_calls(self):
        for options in ({"deadline": 0}, {"deadline": 601}, {"verification_deadline": -1}):
            with self.subTest(options=options):
                result, calls = self.run_readback(options=options)
                self.assert_refused(result, "deadline")
                self.assertEqual(calls, [])

    def test_invariant_8_provider_stdout_and_existing_logger_use_stderr(self):
        data = copy.deepcopy(self.data)
        data["print"] = True
        result, _ = self.run_readback(data, extra_env={"FAKE_ASC_PRELOAD": "1", "VERBOSE": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("\n"), 1)
        json.loads(result.stdout)
        self.assertIn("fake provider output", result.stderr)
        self.assertIn(">> GET", result.stderr)
        self.assert_clean()

    def test_invariant_9_provider_exception_text_does_not_escape(self):
        data = copy.deepcopy(self.data)
        version_of(data)["build_error"] = "private-key-path-must-not-escape"
        result, _ = self.run_readback(data)
        self.assert_refused(result, "provider")
        self.assertNotIn("private-key-path-must-not-escape", result.stderr)

    def test_invariant_4_transfer_mode_remains_unavailable(self):
        result, calls = self.run_readback(options={"mode": "transfer"})
        self.assert_refused(result, "read-only")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
