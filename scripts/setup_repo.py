"""One-time GitHub repo setup script.

Usage:
    python scripts/setup_repo.py <org/repo>
    python scripts/setup_repo.py bedrock-python/mattermind

Run AFTER the first CI pass so "All checks passed" exists in GitHub.
"""

from __future__ import annotations

import json
import subprocess
import sys


def gh(*args: str, input: str | None = None, silent: bool = False) -> str:
    result = subprocess.run(
        ["gh", *args],
        input=input,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not silent:
        print(f"  ✗ gh {' '.join(args)}")
        print(f"    {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/setup_repo.py <org/repo>")
        sys.exit(1)

    repo = sys.argv[1]
    org, name = repo.split("/", 1)

    print(f"Setting up {repo}...\n")

    print("  → Creating environments...")
    gh("api", f"repos/{repo}/environments/pypi", "-X", "PUT", silent=True)
    gh("api", f"repos/{repo}/environments/github-pages", "-X", "PUT", silent=True)

    print("  → Enabling GitHub Pages (GitHub Actions source)...")
    gh(
        "api", f"repos/{repo}/pages",
        "-X", "POST",
        "-H", "Accept: application/vnd.github+json",
        "-f", "build_type=workflow",
        silent=True,
    )

    print("  → Allowing Actions to create pull requests...")
    gh(
        "api", f"repos/{repo}/actions/permissions/workflow",
        "-X", "PUT",
        "-f", "default_workflow_permissions=write",
        "-f", "can_approve_pull_request_reviews=true",
    )

    print("  → Setting branch protection on master...")
    protection = json.dumps({
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": "All checks passed"}],
        },
        "enforce_admins": False,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "allow_force_pushes": False,
        "allow_deletions": False,
    })
    gh(
        "api", f"repos/{repo}/branches/master/protection",
        "-X", "PUT",
        "-H", "Accept: application/vnd.github+json",
        "--input", "-",
        input=protection,
    )

    print("\n✓ Done!\n")
    print("Remaining manual steps:")
    print(f"  1. PyPI Trusted Publisher → https://pypi.org/manage/account/publishing/")
    print(f"     project: {name} | org: {org} | repo: {name} | workflow: publish.yml | env: pypi")
    print(f"  2. CODECOV_TOKEN → https://app.codecov.io/gh/{repo}")
    print(f"     GitHub repo → Settings → Secrets → Actions → CODECOV_TOKEN")


if __name__ == "__main__":
    main()
