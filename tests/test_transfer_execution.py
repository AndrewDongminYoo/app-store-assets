"""U4: invariants 2, 4-9 using actual U2 staging and an opt-in write fake."""

import copy
import hashlib
import json
import time
import unittest

from offline_support import write_json
from test_snapshot_export import version_of
from test_transfer_readback import TransferFixture


class TransferExecutionTests(TransferFixture, unittest.TestCase):
    multiple_images = True

    def setUp(self):
        super().setUp()
        self.data["transfer"] = True
        self.locals = version_of(self.data)["localizations"]
        other = copy.deepcopy(self.locals[0])
        other.update(id="fr-localization", locale="fr-FR")
        for index, group in enumerate(other["sets"]):
            group["id"] = f"fr-set-{index}"
            for image in group["screenshots"]:
                image["id"] = "fr-" + image["id"]
        self.locals.append(other)
        self.declared = [self.locals[0]["sets"][0], self.locals[1]["sets"][1]]
        for group in self.declared:
            group["screenshots"] = []
        self.refresh()

    def refresh(self, allow_delete=False):
        self.target["replacement"]["allow_delete"] = allow_delete
        write_json(self.root / "store-upload.json", self.profile)
        self.exporter.output.unlink(missing_ok=True)
        self.remote, _, _ = self.exporter.export(self.data, identity=self.identity)
        self.prepare_plan()

    def run_transfer(self, environment=None, **options):
        env_log = self.tmp / "environment.json"
        result, calls = self.run_readback(options={
            "mode": "transfer", "deadline": 0.2, "group_deadline": 0.15, "poll_interval": 0.01, **options,
        }, extra_env={"FAKE_ASC_ENV_LOG": str(env_log), "SPACESHIP_TIMEOUT": "777",
                      "SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT": "888", **(environment or {})}, allow_writes=True)
        if env_log.exists():
            self.assertEqual(json.loads(env_log.read_text()), {
                "request": (environment or {}).get("SPACESHIP_TIMEOUT", "777"),
                "upload": (environment or {}).get("SPACESHIP_SCREENSHOT_UPLOAD_TIMEOUT", "888"),
            })
        return result, calls

    def writes(self, calls):
        return [c for c in calls if c["call"] in {"create", "upload", "delete", "reorder"}]

    def success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(result.stdout.count("\n"), 1)
        self.assertEqual(report["mode"], "transfer")
        self.assertEqual(report["provenance"], {"status": "unverified-import"})
        self.assertTrue(all(g["readback"]["complete"] and g["readback"]["checksums_match"] for g in report["groups"]))
        self.assert_clean()
        return report

    def matching(self, index, state="COMPLETE"):
        locale = ("en-US", "ko")[index]
        self.declared[index]["screenshots"] = [
            {"id": f"matching-{index}-{i}", "source_file_checksum": hashlib.md5(p.read_bytes()).hexdigest(),
             "asset_delivery_state": {"state": state}, "image_asset": {"width": 1242, "height": 2688}}
            for i, p in enumerate(p for p in self.sources if p.parent.name == locale)
        ]

    def test_invariants_2_4_8_9_uploads_only_staged_declared_pairs(self):
        self.data["print"] = True
        self.data["create_output"] = {"during": "App.find", "path": str(self.sources[0]), "content": "source replaced"}
        report = self.success((run := self.run_transfer())[0])
        uploads = [c["arguments"] for c in self.writes(run[1])]
        self.assertEqual(len(uploads), 3)
        self.assertEqual({u["set"] for u in uploads}, {g["id"] for g in self.declared})
        self.assertEqual([u["position"] for u in uploads], [0, 1, 0])
        self.assertTrue(all(not u["wait_for_processing"] for u in uploads))
        self.assertTrue(all(u["path"].startswith(str(self.stage_parent)) for u in uploads))
        expected = {i["sha256"] for slots in self.plan["payload"]["listing"]["images"].values() for images in slots.values() for i in images}
        self.assertEqual({u["sha256"] for u in uploads}, expected)
        self.assertTrue(all(g["action"] == "upload" for g in report["groups"]))
        self.assertTrue(all(u["request_timeout"] == "60" and u["upload_timeout"] == "1" for u in uploads))

    def test_invariants_2_and_5_all_staged_files_checked_before_any_write(self):
        for during in ("App.find", "poll"):
            with self.subTest(during=during):
                self.matching(1)
                self.refresh()
                self.data["tamper_stage"] = during
                result, calls = self.run_transfer()
                self.assert_refused(result, "staged checksum")
                self.assertEqual(self.writes(calls), [])
                self.data.pop("tamper_stage")

    def test_invariant_4_creates_exactly_one_missing_set(self):
        self.locals[0]["sets"].pop(0)
        self.refresh()
        result, calls = self.run_transfer()
        self.success(result)
        creates = [c["arguments"] for c in calls if c["call"] == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual((creates[0]["locale"], creates[0]["slot"]), ("en-US", "APP_IPHONE_65"))

    def test_invariants_4_and_5_later_replacement_refuses_before_any_write(self):
        self.matching(1)
        self.declared[1]["screenshots"][0]["source_file_checksum"] = "0" * 32
        self.refresh()
        result, calls = self.run_transfer()
        self.assert_refused(result, "allow_delete")
        self.assertEqual(self.writes(calls), [])

    def test_invariant_4_explicit_replacement_deletes_only_declared_images(self):
        self.matching(0)
        self.declared[0]["screenshots"][0]["source_file_checksum"] = "0" * 32
        self.refresh(allow_delete=True)
        result, calls = self.run_transfer()
        report = self.success(result)
        self.assertEqual(report["groups"][0]["action"], "replace")
        self.assertEqual([c["arguments"]["id"] for c in calls if c["call"] == "delete"], ["matching-0-0", "matching-0-1"])

    def test_invariant_5_matching_failed_group_refuses_before_any_write(self):
        self.matching(1, "FAILED")
        self.refresh()
        result, calls = self.run_transfer()
        self.assert_refused(result, "processing failed")
        self.assertEqual(self.writes(calls), [])

    def test_invariant_5_matching_processing_group_settles_before_first_write(self):
        self.matching(1, "PROCESSING")
        self.data["settle_after"] = 2
        self.refresh()
        result, calls = self.run_transfer()
        report = self.success(result)
        self.assertEqual(report["groups"][1]["action"], "unchanged")
        first_write = next(i for i, c in enumerate(calls) if c in self.writes(calls))
        self.assertGreaterEqual(len([c for c in calls[:first_write] if c["call"] == "poll"]), 2)

    def test_invariant_5_unchanged_processing_timeout_has_no_writes(self):
        self.matching(1, "PROCESSING")
        self.refresh()
        result, calls = self.run_transfer()
        self.assert_refused(result, "deadline")
        self.assertEqual(self.writes(calls), [])

    def test_invariant_7_fully_unchanged_run_still_gets_final_read(self):
        self.matching(0)
        self.matching(1)
        self.refresh()
        result, calls = self.run_transfer()
        report = self.success(result)
        self.assertTrue(all(g["action"] == "unchanged" for g in report["groups"]))
        self.assertEqual(self.writes(calls), [])
        self.assertEqual(len([c for c in calls if c["call"] == "App.find"]), 2)

    def test_invariants_6_and_7_late_processing_and_checksum(self):
        self.data.update(processing="PROCESSING", checksum="", settle_after=2)
        self.success(self.run_transfer()[0])

    def test_invariants_6_and_7_bad_processing_or_checksum_fails(self):
        for values, error in [({"processing": "FAILED"}, "processing failed"),
                              ({"processing": "PROCESSING"}, "deadline"),
                              ({"checksum": ""}, "deadline"), ({"checksum": "0" * 32}, "checksum")]:
            with self.subTest(values=values):
                self.data.pop("processing", None)
                self.data.pop("checksum", None)
                self.data.update(values)
                result, _ = self.run_transfer()
                self.assert_refused(result, error)
                self.assertIn("possibly changed: en-US/APP_IPHONE_65", result.stderr)

    def test_invariant_7_reorders_once_and_requires_correct_readback(self):
        self.data["reverse"] = True
        result, calls = self.run_transfer()
        self.success(result)
        self.assertEqual(len([c for c in calls if c["call"] == "reorder"]), 1)
        self.data["ignore_reorder"] = True
        result, calls = self.run_transfer()
        self.assert_refused(result, "order")
        self.assertEqual(len([c for c in calls if c["call"] == "reorder"]), 1)

    def test_invariant_7_final_read_detects_preserved_declared_build_and_state_changes(self):
        for change in ("preserved", "declared", "build", "state", "set_id", "declared_id", "review"):
            with self.subTest(change=change):
                self.data["final_change"] = change
                result, _ = self.run_transfer()
                self.assert_refused(result, "possibly changed:")

    def test_invariant_6_provider_retry_and_upload_timeout_are_bounded(self):
        for behavior in ("placeholder_retry", "upload_timeout"):
            with self.subTest(behavior=behavior):
                self.data.pop("placeholder_retry", None)
                self.data.pop("upload_timeout", None)
                self.data[behavior] = True
                start = time.monotonic()
                result, calls = self.run_transfer()
                self.assertLess(time.monotonic() - start, 5)
                self.assert_refused(result, "deadline")
                self.assertTrue(self.writes(calls))

    def test_invariant_6_uploads_share_the_group_deadline(self):
        self.data["upload_delay"] = 0.07
        result, calls = self.run_transfer(group_deadline=0.1, deadline=0.3)
        self.assert_refused(result, "deadline")
        self.assertEqual([c["arguments"]["set"] for c in calls if c["call"] == "upload"],
                         [self.declared[0]["id"], self.declared[0]["id"]])
        self.assertEqual([c["arguments"]["position"] for c in calls if c["call"] == "uploaded"], [0])

    def test_invariant_6_every_write_is_bounded_including_429_retries(self):
        for call in ("upload", "create", "delete", "reorder"):
            with self.subTest(call=call):
                if call == "create":
                    self.locals[0]["sets"].remove(self.declared[0])
                elif call == "delete":
                    self.locals[0]["sets"].insert(0, self.declared[0])
                    self.matching(0)
                    self.declared[0]["screenshots"][0]["source_file_checksum"] = "0" * 32
                elif call == "reorder":
                    self.declared[0]["screenshots"] = []
                    self.data["reverse"] = True
                self.refresh(allow_delete=True)
                self.data["hang"] = {"call": call, "seconds": 10}
                result, calls = self.run_transfer()
                self.assert_refused(result, "deadline")
                self.assertIn(call, [c["call"] for c in self.writes(calls)])
                self.data.pop("hang")

    def test_invariant_6_bounds_reject_invalid_values_before_provider_reads(self):
        for key in ("group_deadline", "poll_interval", "request_timeout"):
            for value in (0, -1, 601):
                with self.subTest(key=key, value=value):
                    result, calls = self.run_transfer(**{key: value})
                    self.assert_refused(result, "deadline")
                    self.assertEqual(calls, [])

    def test_invariant_7_cleanup_failure_keeps_all_possibly_changed_group_names(self):
        result, calls = self.run_transfer(environment={"FAKE_TRANSFER_CLEANUP_ERROR": "1"})
        self.assert_refused(result, "injected cleanup error")
        self.assertIn("possibly changed: en-US/APP_IPHONE_65, ko/APP_IPAD_PRO_3GEN_129", result.stderr)
        self.assertEqual(len([c for c in calls if c["call"] == "uploaded"]), 3)
