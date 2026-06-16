from __future__ import annotations

import os
import subprocess
import sys


def test_live_eval_command_skips_without_env():
    env = os.environ.copy()
    env.pop("RUN_LIVE_EVALS", None)

    result = subprocess.run(
        [sys.executable, "scripts/run_evals.py", "--live"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0
    assert "Skipping live evals" in result.stdout
