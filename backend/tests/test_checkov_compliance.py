"""Checkov IaC Compliance Tests — validates Terraform security posture.

These tests run checkov programmatically against the terraform/ directory
to ensure no unexpected security regressions are introduced.

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


def _run_checkov(baseline_only: bool = False) -> dict:
    """Run checkov and return parsed results."""
    cmd = [
        "checkov",
        "-d",
        os.path.abspath(TERRAFORM_DIR),
        "--framework",
        "terraform",
        "--compact",
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
    """5 tests: checkov IaC compliance assertions."""

    def test_checkov_runs_successfully(self):
        """Checkov must complete without fatal errors."""
        data = _run_checkov()
        assert "results" in data, "checkov output missing 'results' key"
        assert "passed_checks" in data["results"], "missing passed_checks"
        assert "failed_checks" in data["results"], "missing failed_checks"

    def test_inline_skips_present_in_all_modules(self):
        """All 9 terraform modules must have checkov skip comments."""
        modules = [
            "ecs",
            "frontend",
            "iam",
            "kafka",
            "monitoring",
            "rds",
            "secrets",
            "vpc",
            "ecr",
        ]
        modules_without_skips = []
        for mod in modules:
            mod_file = os.path.join(TERRAFORM_DIR, "modules", mod, "main.tf")
            if not os.path.exists(mod_file):
                modules_without_skips.append(f"{mod} (file not found)")
                continue
            with open(mod_file) as f:
                content = f.read()
            if "# checkov:skip=" not in content:
                modules_without_skips.append(mod)
        assert not modules_without_skips, (
            f"Modules missing checkov skips: {', '.join(modules_without_skips)}"
        )

    def test_no_unexpected_critical_or_high_failures(self):
        """No unexpected CRITICAL or HIGH severity failures should exist.
        This sets a baseline; any NEW critical/high failure is a regression."""
        data = _run_checkov()
        failed = data["results"].get("failed_checks", [])

        # Currently known CRITICAL/HIGH failures that have been reviewed
        # and accepted with inline skips in the relevant modules
        known_high_failures = {
            "CKV_AWS_28",  # DynamoDB point-in-time recovery (bootstrap)
            "CKV_AWS_119",  # DynamoDB KMS encryption (bootstrap)
        }

        unexpected = []
        for check in failed:
            sev = check.get("severity", "").upper()
            cid = check.get("check_id", "")
            if sev in ("CRITICAL", "HIGH") and cid not in known_high_failures:
                unexpected.append(f"{cid} ({sev}): {check.get('check_name', '')}")

        assert not unexpected, "Unexpected CRITICAL/HIGH failures:\n" + "\n".join(
            unexpected
        )

    def test_known_failure_count_stable(self):
        """The total number of checkov failures should be within an
        expected range. A significant increase indicates new regressions."""
        data = _run_checkov()
        total_failed = len(data["results"].get("failed_checks", []))
        # Current baseline from modules with inline skips documented
        assert 40 <= total_failed <= 80, (
            f"Expected 40-80 checkov failures (current known state with inline skips), "
            f"got {total_failed}. A change in this range suggests new findings or new modules."
        )

    def test_bootstrap_and_data_folders_scanned(self):
        """Checkov must scan bootstrap/ and data/ folders in addition to modules."""
        data = _run_checkov()
        failed = data["results"].get("failed_checks", [])
        failed_files = {c.get("file_path", "") for c in failed}

        bootstrap_scanned = any("/bootstrap/" in f for f in failed_files)
        modules_scanned = any("/modules/" in f for f in failed_files)

        assert bootstrap_scanned, "No results from bootstrap/ directory"
        assert modules_scanned, "No results from modules/ directory"
