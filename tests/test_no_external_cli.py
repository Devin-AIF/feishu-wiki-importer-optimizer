"""整套离线测试必须在没有可执行 `lark-cli` 的环境中也能通过。"""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NoExternalCliTests(unittest.TestCase):
    def test_safety_suite_does_not_execute_lark_cli(self):
        env = dict(os.environ)
        env["PATH"] = "/usr/bin:/bin"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_safety_regressions",
                "-q",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
