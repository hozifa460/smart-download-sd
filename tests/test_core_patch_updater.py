"""
Automated Test Module for Smart Download (SD) OTA Core Hot-Patch Updater.
Tests CoreHotPatchUpdater, build_core_patch_zip, _ExternalCoreFinder, and init_core_loader.
"""
import os
import sys
import tempfile
import time
import json
import zipfile
import io
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root and src/ are in sys.path
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

os.environ["SD_DISABLE_SYSTEM_TRAY"] = "1"
os.environ["SD_DISABLE_STARTUP_TOAST"] = "1"
os.environ["SD_DISABLE_AUTO_UPDATE"] = "1"
os.environ["SD_LANGUAGE"] = "en"
if not os.environ.get("SD_CONFIG_DIR"):
    _sd_test_cfg = os.path.join(tempfile.gettempdir(), "sd_test_isolated_cfg")
    os.makedirs(_sd_test_cfg, exist_ok=True)
    os.environ["SD_CONFIG_DIR"] = _sd_test_cfg

from updater import (
    build_core_patch_zip,
    CoreHotPatchUpdater,
    _ExternalCoreFinder,
    init_core_loader,
    is_version_ge,
    get_core_plugin_dir,
    APP_VERSION,
    APP_NAME,
)


class _MockStreamResp:
    """Mock HTTP response providing read() and context manager interface."""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)
        self.headers = {"Content-Length": str(len(data))}

    def read(self, sz: int = -1):
        return self._buf.read(sz)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestCoreHotPatchAndZeroRebuildWorkflow(unittest.TestCase):
    """Verifies fast core patch packaging, atomic extraction, rollback, and dynamic loading."""

    def test_build_core_patch_zip_completeness_and_speed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_zip = os.path.join(tmp_dir, "SmartDownload-CorePatch.zip")
            t0 = time.time()
            res_path = build_core_patch_zip(out_zip, version="2.0.1")
            elapsed = time.time() - t0

            self.assertEqual(res_path, os.path.abspath(out_zip))
            self.assertTrue(os.path.isfile(out_zip))
            self.assertLess(elapsed, 1.0, f"Zip packaging took too long: {elapsed:.3f}s")

            file_size = os.path.getsize(out_zip)
            # Lightweight patch should be ~100-200 KB
            self.assertGreater(file_size, 50 * 1024)
            self.assertLess(file_size, 500 * 1024)

            with zipfile.ZipFile(out_zip, "r") as zf:
                names = zf.namelist()
                self.assertIn("core_version.json", names)
                self.assertIn("smart_download/__init__.py", names)
                self.assertIn("smart_download/config.py", names)
                self.assertIn("smart_download/locales/ar.json", names)
                self.assertIn("smart_download/locales/en.json", names)

                manifest_raw = zf.read("core_version.json").decode("utf-8")
                manifest = json.loads(manifest_raw)
                self.assertEqual(manifest["version"], "2.0.1")
                self.assertEqual(manifest["app_name"], APP_NAME)

    def test_core_hot_patch_version_verification(self):
        # is_version_ge edge cases
        self.assertTrue(is_version_ge("2.1.0", "2.0.0"))
        self.assertTrue(is_version_ge("2.0.1", "2.0.0"))
        self.assertTrue(is_version_ge("2.0.0", "2.0.0"))
        self.assertTrue(is_version_ge("v2.0.0", "2.0.0"))
        self.assertTrue(is_version_ge("2.0", "2.0.0"))
        self.assertTrue(is_version_ge("2.0.0", "2.0"))
        self.assertFalse(is_version_ge("1.9.9", "2.0.0"))
        self.assertFalse(is_version_ge("2.0.0-alpha", "2.0.0"))
        self.assertFalse(is_version_ge("", "2.0.0"))
        self.assertFalse(is_version_ge(None, "2.0.0"))
        self.assertTrue(is_version_ge("2.0.0", ""))
        self.assertTrue(is_version_ge("2.0.0", None))
        self.assertFalse(is_version_ge("", ""))
        self.assertFalse(is_version_ge(None, None))

        with tempfile.TemporaryDirectory() as tmp_dir:
            updater = CoreHotPatchUpdater(plugin_dir=tmp_dir, current_version="2.0.0")
            self.assertFalse(updater.is_plugin_valid())
            self.assertIsNone(updater.get_plugin_version())

            # Add core_version.json and smart_download package files
            pkg_dir = os.path.join(tmp_dir, "smart_download")
            os.makedirs(pkg_dir, exist_ok=True)
            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write('"""test init"""\n')
            with open(os.path.join(pkg_dir, "config.py"), "w", encoding="utf-8") as f:
                f.write('APP_VERSION = "2.0.1"\n')
            with open(os.path.join(tmp_dir, "core_version.json"), "w", encoding="utf-8") as f:
                json.dump({"version": "2.0.1"}, f)

            self.assertTrue(updater.is_plugin_valid())
            self.assertEqual(updater.get_plugin_version(), "2.0.1")

    def test_core_hot_patch_atomic_extraction_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_zip = os.path.join(tmp_dir, "patch.zip")
            build_core_patch_zip(patch_zip, version="2.0.1")

            target_dir = os.path.join(tmp_dir, "core_plugin")
            updater = CoreHotPatchUpdater(plugin_dir=target_dir, current_version="2.0.0")

            # 1. Successful atomic application
            applied = updater.apply_core_patch(patch_zip, target_dir=target_dir)
            self.assertTrue(applied)
            self.assertTrue(updater.is_plugin_valid(target_dir))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.1")

            # 2. Corrupt archive rollback: target_dir must remain at 2.0.1!
            corrupt_zip = os.path.join(tmp_dir, "corrupt.zip")
            with zipfile.ZipFile(corrupt_zip, "w") as zf:
                zf.writestr("unrelated.txt", "not a valid core patch")

            with self.assertRaises(ValueError):
                updater.apply_core_patch(corrupt_zip, target_dir=target_dir)

            # Target directory must still be intact and valid
            self.assertTrue(updater.is_plugin_valid(target_dir))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.1")

            # 3. Zip Slip path traversal attack rejection
            slip_zip = os.path.join(tmp_dir, "slip.zip")
            with zipfile.ZipFile(slip_zip, "w") as zf:
                zf.writestr("../../evil.txt", "exploit")
                zf.writestr("core_version.json", json.dumps({"version": "2.0.2"}))

            with self.assertRaises(ValueError):
                updater.apply_core_patch(slip_zip, target_dir=target_dir)

            self.assertTrue(updater.is_plugin_valid(target_dir))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.1")

    def test_core_hot_patch_transient_swap_retry_and_concurrency(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_zip = os.path.join(tmp_dir, "patch.zip")
            build_core_patch_zip(patch_zip, version="2.0.1")

            target_dir = os.path.join(tmp_dir, "core_plugin")
            updater = CoreHotPatchUpdater(plugin_dir=target_dir, current_version="2.0.0")

            # Initial apply
            self.assertTrue(updater.apply_core_patch(patch_zip, target_dir=target_dir))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.1")

            # 1. Transient Windows lock simulation during directory swap (retries and recovers)
            patch_zip_v2 = os.path.join(tmp_dir, "patch_v2.zip")
            build_core_patch_zip(patch_zip_v2, version="2.0.2")

            call_counts = {"attempts": 0}
            real_replace = CoreHotPatchUpdater._safe_replace_dir

            def _flaky_replace(src, dst, retries=5, delay=0.06):
                call_counts["attempts"] += 1
                if call_counts["attempts"] == 2:
                    raise PermissionError("Simulated transient Windows file lock")
                return real_replace(src, dst, retries=retries, delay=delay)

            with patch.object(CoreHotPatchUpdater, "_safe_replace_dir", side_effect=_flaky_replace):
                # When replace fails critically, target must rollback to previous valid plugin!
                with self.assertRaises(PermissionError):
                    updater.apply_core_patch(patch_zip_v2, target_dir=target_dir)

            self.assertTrue(updater.is_plugin_valid(target_dir))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.1")

            # 2. Concurrency: multiple threads applying patches simultaneously
            results = []
            def _worker():
                res = updater.apply_core_patch(patch_zip_v2, target_dir=target_dir)
                results.append(res)

            import threading
            t1 = threading.Thread(target=_worker)
            t2 = threading.Thread(target=_worker)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)

            self.assertEqual(len(results), 2)
            self.assertTrue(all(results))
            self.assertEqual(updater.get_plugin_version(target_dir), "2.0.2")

    def test_core_hot_patch_check_and_download(self):
        updater = CoreHotPatchUpdater(current_version="2.0.0")

        mock_release = {
            "tag_name": "v2.1.0",
            "body": "Fixes and performance updates",
            "assets": [
                {
                    "name": "SmartDownload-CorePatch.zip",
                    "browser_download_url": "https://github.com/mock/releases/download/v2.1.0/SmartDownload-CorePatch.zip",
                    "size": 125000,
                },
                {
                    "name": "SmartDownload-Setup.exe",
                    "browser_download_url": "https://github.com/mock/releases/download/v2.1.0/SmartDownload-Setup.exe",
                    "size": 55000000,
                }
            ]
        }

        with patch("urllib.request.urlopen", return_value=_MockStreamResp(json.dumps(mock_release).encode("utf-8"))):
            info = updater.check_for_core_patch()
            self.assertTrue(info["success"])
            self.assertTrue(info["patch_available"])
            self.assertEqual(info["latest_version"], "2.1.0")
            self.assertEqual(info["patch_size"], 125000)
            self.assertIn("SmartDownload-CorePatch.zip", info["patch_url"])

        dummy_zip_bytes = b"PK\x05\x06" + b"\x00" * 18
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_p = os.path.join(tmp_dir, "test_patch.zip")
            with patch("urllib.request.urlopen", return_value=_MockStreamResp(dummy_zip_bytes)):
                res = updater.download_core_patch("https://example.com/patch.zip", dest_path=dest_p)
                self.assertEqual(res, os.path.abspath(dest_p))
                self.assertTrue(os.path.isfile(dest_p))

    def test_external_core_finder_and_dev_source_loader(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dev_root = os.path.join(tmp_dir, "dev_src")
            pkg_dir = os.path.join(dev_root, "smart_download")
            os.makedirs(pkg_dir, exist_ok=True)
            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write('"""dev init"""\n')
            with open(os.path.join(pkg_dir, "config.py"), "w", encoding="utf-8") as f:
                f.write('APP_VERSION = "2.9.9"\n')

            finder = _ExternalCoreFinder(dev_root)
            self.assertIsNone(finder.find_spec("unrelated_package"))
            spec = finder.find_spec("smart_download")
            self.assertIsNotNone(spec)
            self.assertEqual(spec.name, "smart_download")

            # Test finder resilient against frozen bundle path pollution
            sub_spec_frozen = finder.find_spec("smart_download.config", path=["C:\\frozen\\smart_download"])
            self.assertIsNotNone(sub_spec_frozen)
            self.assertEqual(sub_spec_frozen.origin, os.path.abspath(os.path.join(pkg_dir, "config.py")))

            # Test init_core_loader with SD_DEV_SRC override and actual module reflection
            orig_dev_src = os.environ.get("SD_DEV_SRC")
            orig_sys_path = list(sys.path)
            orig_meta_path = list(sys.meta_path)
            orig_modules = {k: v for k, v in sys.modules.items() if k == "smart_download" or k.startswith("smart_download.")}
            try:
                os.environ["SD_DEV_SRC"] = dev_root
                mode = init_core_loader(force=True)
                self.assertEqual(mode, "dev")
                self.assertEqual(os.path.abspath(sys.path[0]), os.path.abspath(dev_root))
                self.assertIsInstance(sys.meta_path[0], _ExternalCoreFinder)

                # CRITICAL: Verify imported module actually reflects dev version!
                from smart_download import config
                self.assertEqual(config.APP_VERSION, "2.9.9")
                self.assertEqual(os.path.abspath(config.__file__), os.path.abspath(os.path.join(pkg_dir, "config.py")))
            finally:
                if orig_dev_src is not None:
                    os.environ["SD_DEV_SRC"] = orig_dev_src
                else:
                    os.environ.pop("SD_DEV_SRC", None)
                sys.path[:] = orig_sys_path
                sys.meta_path[:] = orig_meta_path
                for k in list(sys.modules.keys()):
                    if k == "smart_download" or k.startswith("smart_download."):
                        sys.modules.pop(k, None)
                sys.modules.update(orig_modules)

    def test_init_core_loader_plugin_mode(self):
        orig_sys_path = list(sys.path)
        orig_meta_path = list(sys.meta_path)
        orig_modules = {k: v for k, v in sys.modules.items() if k == "smart_download" or k.startswith("smart_download.")}

        with tempfile.TemporaryDirectory() as tmp_dir:
            plugin_root = os.path.join(tmp_dir, "core_plugin")
            pkg_dir = os.path.join(plugin_root, "smart_download")
            os.makedirs(pkg_dir, exist_ok=True)
            with open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8") as f:
                f.write('"""plugin init"""\n')
            with open(os.path.join(pkg_dir, "config.py"), "w", encoding="utf-8") as f:
                f.write('APP_VERSION = "3.5.0"\n')
            with open(os.path.join(plugin_root, "core_version.json"), "w", encoding="utf-8") as f:
                json.dump({"version": "3.5.0"}, f)

            try:
                with patch("smart_download.services.core_patch_updater.get_core_plugin_dir", return_value=plugin_root):
                    mode = init_core_loader(force=True)
                    self.assertEqual(mode, "plugin")
                    self.assertEqual(os.path.abspath(sys.path[0]), os.path.abspath(plugin_root))
                    self.assertIsInstance(sys.meta_path[0], _ExternalCoreFinder)

                    from smart_download import config
                    self.assertEqual(config.APP_VERSION, "3.5.0")
            finally:
                sys.path[:] = orig_sys_path
                sys.meta_path[:] = orig_meta_path
                for k in list(sys.modules.keys()):
                    if k == "smart_download" or k.startswith("smart_download."):
                        sys.modules.pop(k, None)
                sys.modules.update(orig_modules)


    def test_services_package_namespace_reexports(self):
        import smart_download.services as sds
        self.assertTrue(hasattr(sds, "CoreHotPatchUpdater"))
        self.assertTrue(hasattr(sds, "build_core_patch_zip"))
        self.assertTrue(hasattr(sds, "init_core_loader"))
        self.assertTrue(hasattr(sds, "_ExternalCoreFinder"))
        self.assertTrue(hasattr(sds, "get_core_plugin_dir"))
        self.assertTrue(hasattr(sds, "is_version_ge"))


if __name__ == "__main__":
    unittest.main()

