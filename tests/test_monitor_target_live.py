from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "tmp" / "monitor_target_live_1s.py"
)
SPEC = importlib.util.spec_from_file_location("monitor_target_live_1s", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)


class MonitorTargetLiveTests(unittest.TestCase):
    def test_health_grace_recovers_from_a_transient_failure(self) -> None:
        grace = MONITOR.HealthGrace(5.0)

        self.assertFalse(grace.should_abort(False, now=10.0))
        self.assertFalse(grace.should_abort(False, now=14.9))
        self.assertTrue(grace.degraded)
        self.assertFalse(grace.should_abort(True, now=15.0))
        self.assertFalse(grace.degraded)

    def test_health_grace_aborts_after_a_persistent_failure(self) -> None:
        grace = MONITOR.HealthGrace(5.0)

        self.assertFalse(grace.should_abort(False, now=10.0))
        self.assertTrue(grace.should_abort(False, now=15.0))

    def test_load_json_retries_a_transient_permission_error(self) -> None:
        path = MODULE_PATH.parent / "test-monitor-heartbeat.json"
        path.write_text('{"healthy": true}', encoding="utf-8")
        self.addCleanup(path.unlink, missing_ok=True)
        original_read_text = Path.read_text
        attempts = 0

        def flaky_read_text(self: Path, *args, **kwargs) -> str:
            nonlocal attempts
            if self == path:
                attempts += 1
                if attempts == 1:
                    raise PermissionError("heartbeat replacement in progress")
            return original_read_text(self, *args, **kwargs)

        with patch.object(Path, "read_text", flaky_read_text):
            self.assertEqual(MONITOR.load_json(path), {"healthy": True})

        self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
