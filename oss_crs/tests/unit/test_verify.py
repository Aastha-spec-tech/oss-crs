# SPDX-License-Identifier: MIT
"""Unit tests for scripts/verify.py verification runner."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "verify.py"
_spec = importlib.util.spec_from_file_location("verify", _SCRIPT)
verify_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_mod)


def test_constants_paths():
    """Verify configured paths for linting and type-checking."""
    assert verify_mod.RUFF_PATHS == ["oss_crs", "oss-crs-infra", "libCRS"]
    assert verify_mod.PYRIGHT_PATHS == ["oss_crs/src", "libCRS/libCRS", "oss-crs-infra"]


def test_run_prints_command_and_calls_subprocess(monkeypatch, capsys):
    """Test verify.run correctly logs command and delegates to subprocess.call."""
    calls = []

    def mock_call(cmd):
        calls.append(cmd)
        return 0

    monkeypatch.setattr(subprocess, "call", mock_call)

    ret = verify_mod.run(["echo", "hello"])

    assert ret == 0
    assert calls == [["echo", "hello"]]
    captured = capsys.readouterr()
    assert ">>> echo hello" in captured.out


def test_run_returns_subprocess_exit_code(monkeypatch):
    """Test verify.run returns non-zero code on failure."""
    monkeypatch.setattr(subprocess, "call", lambda cmd: 42)

    ret = verify_mod.run(["false"])
    assert ret == 42


def test_internal_run_all_pass(monkeypatch, capsys):
    """Test _run returns 0 and marks all steps PASS when all subcommands succeed."""
    recorded_cmds = []

    def mock_run(cmd):
        recorded_cmds.append(cmd)
        return 0

    monkeypatch.setattr(verify_mod, "run", mock_run)

    exit_code = verify_mod._run()

    assert exit_code == 0
    assert len(recorded_cmds) == 5

    # Check step commands
    assert recorded_cmds[0] == ["ruff", "check", "oss_crs", "oss-crs-infra", "libCRS"]
    assert recorded_cmds[1] == ["ruff", "format", "--check", "oss_crs", "oss-crs-infra", "libCRS"]
    assert recorded_cmds[2] == ["pyright", "oss_crs/src", "libCRS/libCRS", "oss-crs-infra"]
    assert recorded_cmds[3] == ["pytest", "-m", "not integration", "-v", "oss_crs"]
    assert recorded_cmds[4] == [
        "pytest",
        "-m",
        "not integration",
        "-o",
        "pythonpath=libCRS",
        "-v",
        "libCRS/tests",
    ]

    captured = capsys.readouterr()
    assert "--- Summary ---" in captured.out
    assert "PASS  ruff check" in captured.out
    assert "PASS  ruff format" in captured.out
    assert "PASS  pyright" in captured.out
    assert "PASS  unit tests" in captured.out
    assert "PASS  libCRS unit tests" in captured.out
    assert "FAIL" not in captured.out


def test_internal_run_partial_and_total_failures(monkeypatch, capsys):
    """Test _run reports failed steps in summary and returns 1."""
    # Fail pyright and libCRS unit tests
    def mock_run(cmd):
        if cmd[0] == "pyright":
            return 1
        if "libCRS/tests" in cmd:
            return 2
        return 0

    monkeypatch.setattr(verify_mod, "run", mock_run)

    exit_code = verify_mod._run()

    assert exit_code == 1

    captured = capsys.readouterr()
    assert "--- Summary ---" in captured.out
    assert "PASS  ruff check" in captured.out
    assert "PASS  ruff format" in captured.out
    assert "FAIL  pyright" in captured.out
    assert "PASS  unit tests" in captured.out
    assert "FAIL  libCRS unit tests" in captured.out


def test_main_exits_with_run_return_code(monkeypatch):
    """Test main() propagates the return code of _run to sys.exit."""
    monkeypatch.setattr(verify_mod, "_run", lambda: 0)
    with pytest.raises(SystemExit) as exc_info:
        verify_mod.main()
    assert exc_info.value.code == 0

    monkeypatch.setattr(verify_mod, "_run", lambda: 1)
    with pytest.raises(SystemExit) as exc_info_fail:
        verify_mod.main()
    assert exc_info_fail.value.code == 1
