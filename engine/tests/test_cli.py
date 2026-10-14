from __future__ import annotations

import json
import os
import subprocess
import sys


def _run(tmp_path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "JYOTISHA_DATA_DIR": str(tmp_path),
    }
    return subprocess.run(
        [sys.executable, "-m", "jyotisha.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_json_commands_emit_one_parseable_document(tmp_path) -> None:
    result = _run(tmp_path, "--format", "json", "doctor")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ledger"]["ok"] is True
    assert payload["status"] == "warning"


def test_unsupported_structured_output_fails_instead_of_mixing_text(tmp_path) -> None:
    result = _run(tmp_path, "--format", "json", "chart")
    assert result.returncode == 2
    assert "not supported by chart" in result.stderr
    assert result.stdout == ""
