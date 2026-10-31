"""Offline tests for packaging paths and the one-minute onboarding layer.

Covered here:

* config resolution chain: ``MEDRADAR_CONFIG_DIR`` -> source tree -> installed
  ``share/medradar/config`` -> in-package ``_config``;
* ``MEDRADAR_HOME`` moving ``data/out/cache`` out of the checkout;
* ``run_demo`` rendering the committed snapshot with zero network access;
* ``run_doctor`` reporting FAIL instead of raising when files are missing;
* ``watchlist_add/remove/list`` atomic, idempotent, Chinese-preserving edits.

Everything runs against temporary directories; the only reads from the
checkout are the committed config templates and metrics snapshot.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from medradar import config
from medradar.onboarding import (
    FAIL,
    PASS,
    WARN,
    find_demo_metrics,
    run_demo,
    run_doctor,
    watchlist_add,
    watchlist_list,
    watchlist_path,
    watchlist_remove,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = REPO_ROOT / "config"
FIXTURE_METRICS = REPO_ROOT / "tests" / "fixtures" / "metrics_sample.json"


# ----------------------------------------------------------------- path resolution
class ConfigResolutionTests(unittest.TestCase):
    def test_env_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resolved = config.resolve_config_dir({"MEDRADAR_CONFIG_DIR": tmp})
            self.assertEqual(resolved, Path(tmp))

    def test_env_override_is_used_verbatim_even_if_missing(self) -> None:
        missing = Path(tempfile.gettempdir()) / "medradar-definitely-not-here"
        self.assertEqual(
            config.resolve_config_dir({"MEDRADAR_CONFIG_DIR": str(missing)}),
            missing,
        )

    def test_source_tree_config_is_the_default_in_a_checkout(self) -> None:
        self.assertTrue((SOURCE_CONFIG / "companies_device.json").is_file())
        self.assertTrue(
            config.resolve_config_dir({}).is_dir(),
            "default config dir must exist when running the suite from a checkout",
        )
        self.assertEqual(config.resolve_config_dir({}), SOURCE_CONFIG)
        self.assertEqual(config.CONFIG_ORIGIN, "source")

    def test_installed_share_layout_is_discovered(self) -> None:
        """Simulate a wheel install: no source ``config/`` next to the package."""
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            installed = prefix / "share" / "medradar" / "config"
            installed.mkdir(parents=True)
            with mock.patch.object(config, "SOURCE_ROOT", prefix), mock.patch.object(
                config, "_data_prefixes", lambda: [prefix]
            ):
                self.assertEqual(config.resolve_config_dir({}), installed)
                self.assertEqual(config._resolve_config({})[1], "installed")

    def test_in_package_config_is_the_last_resort(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            with mock.patch.object(config, "SOURCE_ROOT", prefix), mock.patch.object(
                config, "_data_prefixes", lambda: [prefix]
            ):
                self.assertEqual(config.resolve_config_dir({}), config.BUNDLED_CONFIG_DIR)
                self.assertEqual(config._resolve_config({})[1], "package")

    def test_medradar_home_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(config.resolve_home({"MEDRADAR_HOME": tmp}), Path(tmp))

    def test_source_checkout_defaults_home_to_repo_root(self) -> None:
        self.assertEqual(config.resolve_home({}), REPO_ROOT)

    def test_installed_default_home_is_dot_medradar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(config, "SOURCE_ROOT", Path(tmp)):
                expected = Path(os.path.expanduser("~")) / ".medradar"
                self.assertEqual(config.resolve_home({}), expected)

    def test_env_override_seen_by_a_fresh_interpreter(self) -> None:
        """The variables must work for a real process, not just our in-memory call."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cfg_dir = base / "cfg-copy"
            home = base / "home"
            shutil.copytree(SOURCE_CONFIG, cfg_dir)
            env = {
                key: value
                for key, value in os.environ.items()
                if key not in {"MEDRADAR_CONFIG_DIR", "MEDRADAR_HOME", "PYTHONPATH"}
            }
            env.update(
                PYTHONPATH=str(REPO_ROOT),
                MEDRADAR_CONFIG_DIR=str(cfg_dir),
                MEDRADAR_HOME=str(home),
                PYTHONIOENCODING="utf-8",
            )
            code = (
                "import json, medradar.config as c;"
                "from medradar.config import load_companies;"
                "print(json.dumps({'config_dir': str(c.CONFIG_DIR),"
                " 'origin': c.CONFIG_ORIGIN, 'root': str(c.ROOT),"
                " 'data': str(c.DATA_DIR), 'out': str(c.OUT_DIR),"
                " 'cache': str(c.CACHE_DIR),"
                " 'companies': len(load_companies('device').all())}))"
            )
            proc = subprocess.run(
                [sys.executable, "-c", code],
                cwd=str(base),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertEqual(Path(payload["config_dir"]), cfg_dir)
            self.assertEqual(payload["origin"], "env")
            self.assertEqual(Path(payload["root"]), home)
            self.assertEqual(Path(payload["data"]), home / "data")
            self.assertEqual(Path(payload["out"]), home / "out")
            self.assertEqual(Path(payload["cache"]), home / "data" / "cache")
            self.assertGreater(payload["companies"], 0)
            self.assertFalse((home / "data").exists(), "resolution must not create directories")


# ------------------------------------------------------------------------- demo
class DemoTests(unittest.TestCase):
    def test_committed_snapshot_is_discoverable(self) -> None:
        snapshot = find_demo_metrics()
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertTrue(snapshot.is_file())
        self.assertEqual(snapshot.name, "metrics.json")

    def test_demo_offline_from_committed_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "demo"
            started = time.perf_counter()
            result = run_demo(out_dir=out_dir)
            wall = time.perf_counter() - started

            self.assertEqual(result["status"], "ok", result.get("error"))
            self.assertLess(wall, 60.0, "demo must stay under the 60 second budget")
            self.assertLess(result["elapsed_seconds"], 60.0)
            index = Path(result["index_html"])
            self.assertTrue(index.is_file())
            self.assertGreater(index.stat().st_size, 1_000)
            self.assertIn("<html", index.read_text(encoding="utf-8", errors="replace").lower())
            for name in ("report_zh.md", "report_en.md", "summary.csv"):
                self.assertTrue((out_dir / name).is_file(), name)
            self.assertEqual(Path(result["out_dir"]), out_dir)
            self.assertTrue(str(result["snapshot"]).endswith("metrics.json"))
            self.assertGreater(result["device_companies"], 0)
            self.assertGreater(result["chapters_zh"], 0)

    def test_demo_first_run_has_no_dead_links(self) -> None:
        """First-run UX: every local link in the demo report must resolve.

        This is the regression test for the release blocker where the demo page
        offered "interactive dashboard" and "1-minute replay" buttons but wrote
        neither file.
        """
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "demo"
            result = run_demo(out_dir=out_dir)
            self.assertEqual(result["status"], "ok", result.get("error"))
            self.assertTrue((out_dir / "dashboard.html").is_file(), "demo must build the dashboard")
            html = (out_dir / "index.html").read_text(encoding="utf-8", errors="replace")
            hrefs = [
                href for href in re.findall(r'href="([^"]+)"', html)
                if not href.startswith(("http://", "https://", "#", "mailto:", "data:"))
            ]
            missing = sorted({href for href in hrefs if not (out_dir / href).exists()})
            self.assertEqual(missing, [], f"dead links in demo: {missing}")

    def test_demo_uses_an_explicit_fixture_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "demo"
            result = run_demo(out_dir=out_dir, metrics_path=FIXTURE_METRICS)
            self.assertEqual(result["status"], "ok", result.get("error"))
            self.assertEqual(Path(result["snapshot"]), FIXTURE_METRICS)
            self.assertTrue((out_dir / "index.html").is_file())

    def test_demo_reports_a_missing_snapshot_instead_of_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            result = run_demo(out_dir=Path(tmp) / "demo", metrics_path=missing)
            self.assertEqual(result["status"], "failed")
            self.assertIn("error", result)
            self.assertIn("searched", result)

    def test_demo_rejects_an_unparsable_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "metrics.json"
            broken.write_text("{not json", encoding="utf-8")
            result = run_demo(out_dir=Path(tmp) / "demo", metrics_path=broken)
            self.assertEqual(result["status"], "failed")

    def test_demo_never_writes_next_to_the_installed_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(out_dir=Path(tmp) / "demo")
            self.assertEqual(result["status"], "ok")
            for produced in result["files"].values():
                self.assertTrue(
                    str(Path(produced)).startswith(str(Path(tmp))),
                    f"{produced} escaped the requested output directory",
                )


# ------------------------------------------------------------------------ doctor
class DoctorTests(unittest.TestCase):
    def test_doctor_reports_all_six_checks_offline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_doctor(home=Path(tmp), network=False)
            self.assertEqual(report["status"], "ok", report.get("failures"))
            self.assertEqual(
                [check["name"] for check in report["checks"]],
                ["python", "config_dir", "config_files", "data_dir", "db", "network"],
            )
            by_name = {check["name"]: check for check in report["checks"]}
            self.assertEqual(by_name["python"]["status"], PASS)
            self.assertEqual(by_name["data_dir"]["status"], PASS)
            self.assertEqual(by_name["db"]["status"], PASS)
            self.assertEqual(by_name["network"]["status"], WARN)
            self.assertIn("network", report["warnings"])
            self.assertEqual(report["failures"], [])
            self.assertTrue(all("detail" in check for check in report["checks"]))
            self.assertEqual(Path(report["home"]), Path(tmp))

    def test_doctor_missing_config_files_fails_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            empty_config = Path(tmp) / "config"
            empty_config.mkdir()
            report = run_doctor(config_dir=empty_config, home=Path(tmp) / "home", network=False)
            self.assertEqual(report["status"], "fail")
            self.assertIn("config_files", report["failures"])
            files_check = next(c for c in report["checks"] if c["name"] == "config_files")
            self.assertEqual(files_check["status"], FAIL)
            self.assertIn("missing", files_check["detail"])

    def test_doctor_missing_config_dir_fails_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            report = run_doctor(config_dir=missing, home=Path(tmp) / "home", network=False)
            self.assertEqual(report["status"], "fail")
            self.assertIn("config_dir", report["failures"])
            self.assertIn("config_files", report["failures"])
            self.assertIn("hint", report)

    def test_doctor_network_probe_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = run_doctor(home=Path(tmp), network=True, timeout=0.001)
            check = next(c for c in report["checks"] if c["name"] == "network")
            self.assertIn(check["status"], {PASS, WARN})
            self.assertNotIn("network", report["failures"])

    def test_doctor_does_not_write_into_the_repository_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            run_doctor(home=home, network=False)
            self.assertTrue((home / "data").is_dir())
            self.assertFalse((home / "out").exists())


# --------------------------------------------------------------------- watchlist
class WatchlistTests(unittest.TestCase):
    def _config_copy(self, tmp: str) -> Path:
        target = Path(tmp) / "config"
        shutil.copytree(SOURCE_CONFIG, target)
        return target

    def test_list_returns_curated_companies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._config_copy(tmp)
            companies = watchlist_list(config_dir=cfg)
            self.assertGreater(len(companies), 0)
            self.assertIn("medtronic", [company["key"] for company in companies])
            medtronic = next(c for c in companies if c["key"] == "medtronic")
            self.assertEqual(medtronic["name_zh"], "美敦力")

    def test_add_is_idempotent_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._config_copy(tmp)
            path = watchlist_path(cfg)
            original = path.read_bytes()
            before = watchlist_list(config_dir=cfg)

            first = watchlist_add(
                "acme_robotics",
                name_en="ACME Robotics",
                name_zh="艾克米机器人",
                ticker="ACME",
                aliases=["ACME ROBOTICS INC"],
                config_dir=cfg,
            )
            self.assertEqual(first["status"], "added")
            self.assertEqual(first["count"], len(before) + 1)
            after_first = path.read_bytes()
            self.assertNotEqual(original, after_first)

            second = watchlist_add(
                "ACME Robotics",
                name_en="ACME Robotics",
                config_dir=cfg,
            )
            self.assertEqual(second["status"], "exists")
            self.assertEqual(second["count"], len(before) + 1)
            self.assertEqual(path.read_bytes(), after_first, "no-op add must not rewrite the file")

            text = path.read_text(encoding="utf-8")
            self.assertIn("艾克米机器人", text)
            self.assertIn("美敦力", text)
            payload = json.loads(text)
            self.assertEqual(payload["schema"], json.loads(original)["schema"])
            self.assertIn("companies", payload)

            added = next(c for c in watchlist_list(config_dir=cfg) if c["key"] == "acme_robotics")
            self.assertEqual(added["name_zh"], "艾克米机器人")
            self.assertEqual(added["ticker"], "ACME")

    def test_remove_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._config_copy(tmp)
            keys_before = [company["key"] for company in watchlist_list(config_dir=cfg)]
            original_companies = json.loads(watchlist_path(cfg).read_text(encoding="utf-8"))["companies"]

            watchlist_add("acme_robotics", name_en="ACME Robotics", config_dir=cfg)
            removed = watchlist_remove("ACME_Robotics", config_dir=cfg)
            self.assertEqual(removed["status"], "removed")
            self.assertEqual(removed["count"], len(keys_before))

            again = watchlist_remove("acme_robotics", config_dir=cfg)
            self.assertEqual(again["status"], "missing")
            self.assertEqual(again["count"], len(keys_before))

            final = json.loads(watchlist_path(cfg).read_text(encoding="utf-8"))["companies"]
            self.assertEqual([c["key"] for c in final], keys_before)
            self.assertEqual([c["key"] for c in final], [c["key"] for c in original_companies])

    def test_original_config_is_not_modified(self) -> None:
        source = SOURCE_CONFIG / "companies_device.json"
        before = source.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._config_copy(tmp)
            watchlist_add("acme_robotics", name_en="ACME Robotics", config_dir=cfg)
        self.assertEqual(source.read_bytes(), before)

    def test_watchlist_on_missing_config_raises_a_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                watchlist_list(config_dir=Path(tmp) / "nope")
            with self.assertRaises(FileNotFoundError):
                watchlist_add("x", config_dir=Path(tmp) / "nope")

    def test_empty_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._config_copy(tmp)
            with self.assertRaises(ValueError):
                watchlist_add("   ", config_dir=cfg)


if __name__ == "__main__":
    unittest.main()
