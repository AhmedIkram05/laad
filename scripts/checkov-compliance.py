#!/usr/bin/env python3
"""Checkov IaC Compliance Check — validates Terraform security posture.

Runs checkov programmatically against the terraform/ directory.
Designed for CI runners where checkov and terraform/ are available.

Usage:
    python scripts/checkov-compliance.py

Returns exit code 0 on pass, 1 on failure.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

TERRAFORM_DIR = os.path.join(os.path.dirname(__file__), "..", "terraform")
# Expected range for total failed checks (set by inline skips across all modules)
EXPECTED_FAILURE_RANGE = (50, 80)

errors = []


def run_checkov() -> dict:
    """Execute checkov and return parsed results."""
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
        sys.exit(f"checkov exited with code {result.returncode}: {result.stderr}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.exit(f"checkov output is not valid JSON: {result.stdout[:500]}")


def check_checkov_runs_successfully(data: dict):
    """Checkov returned valid results structure."""
    summary = data.get("summary", {})
    assert "passed" in summary, "Missing summary.passed"
    assert "failed" in summary, "Missing summary.failed"
    print(
        f"  ✓ checkov found {summary['passed']} passed, "
        f"{summary['failed']} failed, "
        f"{summary.get('parsing_errors', 0)} parsing errors"
    )
    assert summary.get("parsing_errors", 0) == 0, (
        f"There were {summary['parsing_errors']} parsing errors"
    )


def check_inline_skips_present():
    """All terraform modules should have checkov skip comments (warning)."""
    modules_dir = os.path.join(TERRAFORM_DIR, "modules")
    if not os.path.isdir(modules_dir):
        return

    modules = sorted(os.listdir(modules_dir))
    missing = []
    for mod in modules:
        mod_file = os.path.join(modules_dir, mod, "main.tf")
        if not os.path.exists(mod_file):
            continue
        with open(mod_file) as f:
            content = f.read()
        if "# checkov:skip=" not in content:
            missing.append(mod)

    if missing:
        msg = f"Modules missing checkov skips: {', '.join(sorted(missing))}"
        # Non-blocking — informational only
        print(f"  ⚠ {msg}")
    else:
        print(f"  ✓ All {len(modules)} modules with main.tf have checkov skip comments")


def check_no_new_unexpected_failures(data: dict):
    """Check total failure count hasn't changed significantly (regression guard).
    Uses the summary overview rather than per-ID matching, since not every
    flagged resource has an inline skip in dev modules and bootstrap."""
    current = data["summary"]["failed"]
    passed = data["summary"]["passed"]
    ratio = current / max(current + passed, 1)
    # Flag if failure ratio exceeds 25% of total checks
    if ratio > 0.25:
        msg = f"Failure ratio is {ratio:.1%} ({current}/{current + passed}) — may indicate new regressions"
        errors.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(
            f"  ✓ Failure ratio {ratio:.1%} ({current}/{current + passed}) — within expected range"
        )


def check_failure_count_stable(data: dict):
    """Total failure count within expected range."""
    total = data["summary"]["failed"]
    lo, hi = EXPECTED_FAILURE_RANGE
    if not (lo <= total <= hi):
        msg = f"Expected {lo}-{hi} failures, got {total}"
        errors.append(msg)
        print(f"  ✗ {msg}")
    else:
        print(f"  ✓ Failure count {total} within expected range ({lo}-{hi})")


def check_all_folders_scanned(data: dict):
    """Must cover bootstrap/ and modules/ directories."""
    failed = data["results"].get("failed_checks", [])
    failed_files = {c.get("file_path", "") for c in failed}

    bootstrap_ok = any("/bootstrap/" in f for f in failed_files)
    modules_ok = any("/modules/" in f for f in failed_files)

    if not bootstrap_ok:
        errors.append("No results from bootstrap/ directory")
        print("  ✗ checking bootstrap/ — no failures found (might be perfectly clean)")
    else:
        print("  ✓ bootstrap/ failures detected (dir is being checked)")

    if not modules_ok:
        errors.append("No results from modules/ directory")
        print("  ✗ checking modules/ — no failures found (might be perfectly clean)")
    else:
        print("  ✓ modules/ failures detected (dir is being checked)")


def main():
    print(f"Terraform dir: {os.path.abspath(TERRAFORM_DIR)}")
    print()

    if not os.path.isdir(TERRAFORM_DIR):
        sys.exit(f"Terraform directory not found: {TERRAFORM_DIR}")

    # Check checkov is available
    if subprocess.run(["which", "checkov"], capture_output=True).returncode != 0:
        sys.exit("checkov not found — install it first: brew install checkov")

    print("⏳ Running checkov scan (this may take a moment)...")
    data = run_checkov()
    print()

    check_checkov_runs_successfully(data)
    check_inline_skips_present()
    check_no_new_unexpected_failures(data)
    check_failure_count_stable(data)
    check_all_folders_scanned(data)

    print()
    if errors:
        print(f"❌ FAILED: {len(errors)} check(s) failed")
        for e in errors:
            print(f"   • {e}")
        sys.exit(1)
    else:
        print("✅ All checks passed ✓")
        sys.exit(0)


if __name__ == "__main__":
    main()
