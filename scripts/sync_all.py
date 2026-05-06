#!/usr/bin/env python3
"""
Master sync script — chạy 3 sync scripts (POD + Growth + Project) liên tiếp,
tổng hợp kết quả, optionally commit & push lên GitHub Pages.

Usage:
    python3 scripts/sync_all.py            # sync + show diff (no commit)
    python3 scripts/sync_all.py --commit   # sync + auto commit & push
    python3 scripts/sync_all.py --dry-run  # show preview only, no apply
"""

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = [
    ("POD",     "scripts/sync_pod.py"),
    ("Growth",  "scripts/sync_growth.py"),
    ("Project", "scripts/sync_project.py"),
]


def run(cmd, cwd=None):
    """Run subprocess, return (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO)
    return result.returncode, result.stdout, result.stderr


def main():
    dry_run = "--dry-run" in sys.argv
    do_commit = "--commit" in sys.argv

    print("=" * 60)
    print("MASTER SYNC: POD + Growth + Project")
    print("=" * 60)

    # Run validation FIRST (if validate.py exists)
    validate_script = REPO / "scripts" / "validate.py"
    if validate_script.exists():
        print("\n[0/4] Validation pre-sync...")
        rc, out, err = run(["python3", str(validate_script)])
        if rc != 0:
            print(f"  ⚠️  Validation issues:\n{out}{err}")
        else:
            # Print last few lines
            lines = (out or "").strip().split("\n")
            for line in lines[-10:]:
                print(f"  {line}")

    results = []
    apply_flag = [] if dry_run else ["--apply"]

    for i, (name, script) in enumerate(SCRIPTS, start=1):
        print(f"\n[{i}/4] Sync {name}...")
        t0 = time.time()
        rc, out, err = run(["python3", script] + apply_flag)
        elapsed = time.time() - t0
        if rc != 0:
            print(f"  ❌ FAILED ({elapsed:.1f}s)")
            print(err or out)
            sys.exit(1)
        # Extract key lines from output
        summary_lines = []
        for line in (out or "").split("\n"):
            line = line.strip()
            if any(k in line for k in (
                "Total project rows:", "Filtered empty rows:",
                "Quarter Actual:", "Weekly rows:", "Sources:", "Verticals:",
                "H1 Actual:", "Latest month with actual:",
                "Đã update", "Không có thay đổi",
            )):
                summary_lines.append(f"  {line}")
        for line in summary_lines:
            print(line)
        print(f"  ⏱  {elapsed:.1f}s")
        results.append((name, rc, summary_lines, elapsed))

    # Show git diff stat
    print("\n[4/4] Git status:")
    rc, out, err = run(["git", "diff", "--stat", "index.html"])
    if out.strip():
        print(out)
    else:
        print("  (không có thay đổi)")

    if dry_run:
        print("\n--dry-run mode, không ghi & không commit.")
        return

    if do_commit:
        rc, out, err = run(["git", "diff", "--stat", "index.html"])
        if not out.strip():
            print("\nKhông có thay đổi, skip commit.")
            return
        # Build commit message with sync stats
        commit_lines = [
            "Sync all sections từ Total Dashboard sheet",
            "",
            "Sync stats:",
        ]
        for name, _, summary, elapsed in results:
            commit_lines.append(f"- {name} ({elapsed:.1f}s):")
            for s in summary[:3]:
                commit_lines.append(f"  {s.strip()}")
        commit_msg = "\n".join(commit_lines)

        print("\n[5/5] Commit & push...")
        rc, out, err = run(["git", "add", "index.html"])
        rc, out, err = run(["git", "commit", "-m", commit_msg])
        if rc != 0:
            print(f"  ❌ Commit failed:\n{err or out}")
            sys.exit(1)
        print(f"  ✓ Committed")
        rc, out, err = run(["git", "push", "origin", "main"])
        if rc != 0:
            print(f"  ❌ Push failed:\n{err or out}")
            sys.exit(1)
        print(f"  ✓ Pushed → GitHub Pages sẽ deploy ~1 phút")
        print("\nLive: https://ntt9d1130-creator.github.io/Pinpoint-dashboard/")
    else:
        print("\nThêm --commit để auto commit & push.")


if __name__ == "__main__":
    main()
