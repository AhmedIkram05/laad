"""Checkov IaC Compliance Tests — validates Terraform security posture.

These tests run checkov programmatically against the terraform/ directory
to ensure no unexpected security regressions are introduced. Known
accepted-dev findings are suppressed via terraform/.checkov.yml.

Skipped automatically when running inside Docker (no terraform/ directory
available). Designed to run in CI on the host runner where both checkov
and terraform/ are present.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "terraform")
IN_DOCKER = os.path.exists("/.dockerenv")
CHECKOV_AVAILABLE = (
    subprocess.run(["which", "checkov"], capture_output=True, text=True).returncode == 0
)

pytestmark = pytest.mark.skipif(
    IN_DOCKER or not CHECKOV_AVAILABLE or not os.path.isdir(TERRAFORM_DIR),
    reason="checkov compliance tests require checkov on host with terraform/ accessible",
)


def _run_checkov() -> dict:
    """Run checkov and return parsed results.

    ``.checkov.yml`` in the terraform/ directory suppresses all known
    dev-environment baseline findings and excludes test wrapper dirs.
    """
    cmd = [
        "checkov",
        "-d",
        os.path.abspath(TERRAFORM_DIR),
        "--framework",
        "terraform",
        "--quiet",
        "--output",
        "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode not in (0, 1):
        pytest.fail(f"checkov exited with code {result.returncode}: {result.stderr}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"checkov output is not valid JSON: {result.stdout[:500]}")

    return data


class TestCheckovCompliance:
    """4 tests: checkov IaC compliance assertions."""

    def test_checkov_runs_successfully(self):
        """Checkov must complete without fatal errors."""
        data = _run_checkov()
        assert "results" in data, "checkov output missing 'results' key"
        assert "passed_checks" in data["results"], "missing passed_checks"
        assert "failed_checks" in data["results"], "missing failed_checks"

    def test_no_unexpected_critical_or_high_failures(self):
        """No CRITICAL or HIGH severity failures should exist.

        Known high-severity findings are suppressed via .checkov.yml,
        so any HIGH/CRITICAL failure here is an unexpected regression.
        """
        data = _run_checkov()
        failed = data["results"].get("failed_checks", [])

        unexpected = []
        for check in failed:
            sev = (check.get("severity") or "NONE").upper()
            cid = check.get("check_id", "")
            if sev in ("CRITICAL", "HIGH"):
                unexpected.append(f"{cid} ({sev}): {check.get('check_name', '')}")

        assert not unexpected, (
            "Unexpected CRITICAL/HIGH failures.\n"
            "Either fix the IaC issue or add the check ID to terraform/.checkov.yml:\n"
            + "\n".join(unexpected)
        )

    def test_zero_failures_baseline(self):
        """Checkov must report zero failures with current .checkov.yml.

        All accepted dev-environment findings are suppressed via
        terraform/.checkov.yml. Any failure here means either:
        1. A new check ID was introduced that isn't yet in .checkov.yml
        2. An existing check ID that was in .checkov.yml was removed

        Fix: add the new check ID to terraform/.checkov.yml or fix the IaC.
        """
        data = _run_checkov()
        total_failed = len(data["results"].get("failed_checks", []))
        assert total_failed == 0, (
            f"Expected 0 checkov failures (known findings suppressed "
            f"via .checkov.yml), got {total_failed}. "
            f"Check the failing check IDs and either fix the IaC or "
            f"add them to terraform/.checkov.yml."
        )

    def test_bootstrap_and_modules_scanned(self):
        """Checkov must scan bootstrap/ and modules/ directories."""
        data = _run_checkov()
        # With .checkov.yml suppressing failures, check passed_checks
        passed = data["results"].get("passed_checks", [])
        passed_files = {c.get("file_path", "") for c in passed}

        bootstrap_scanned = any("/bootstrap/" in f for f in passed_files)
        modules_scanned = any("/modules/" in f for f in passed_files)

        assert bootstrap_scanned, (
            "No results from bootstrap/ directory. "
            "Check that the scanning path includes bootstrap/"
        )
        assert modules_scanned, (
            "No results from modules/ directory. "
            "Check that the scanning path includes modules/"
        )
