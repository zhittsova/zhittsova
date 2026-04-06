#!/usr/bin/env python3
"""Enable auto-merge for eligible Dependabot GitHub Actions PRs."""

import json
import os
import subprocess
import sys
from typing import Any, Final

DEPENDABOT_LOGIN: Final[str] = "dependabot[bot]"
DEPENDABOT_BRANCH_PREFIX: Final[str] = "dependabot/github_actions/"
TARGET_BASE_BRANCH: Final[str] = "main"


def env_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"{name} is required")
    return value


def run_gh(args: list[str], *, expect_json: bool = False) -> Any:
    result = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"gh {' '.join(args)} failed: {detail}")

    if not expect_json:
        return result.stdout

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("gh command did not return valid JSON") from exc


def should_process_pr(pr: dict[str, Any]) -> bool:
    head_ref = str(pr.get("headRefName") or "")
    base_ref = str(pr.get("baseRefName") or "")
    is_draft = bool(pr.get("isDraft"))
    author_login = str((pr.get("author") or {}).get("login") or "")

    if author_login != DEPENDABOT_LOGIN:
        return False
    if not head_ref.startswith(DEPENDABOT_BRANCH_PREFIX):
        return False
    if base_ref != TARGET_BASE_BRANCH:
        return False
    if is_draft:
        return False
    return True


def checks_are_green(pr_number: int, repository: str) -> bool:
    result = subprocess.run(
        ["gh", "pr", "checks", str(pr_number), "--repo", repository],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def process_pr(pr_number: int, repository: str) -> None:
    pr = run_gh(
        [
            "pr",
            "view",
            str(pr_number),
            "--repo",
            repository,
            "--json",
            "number,url,headRefName,baseRefName,isDraft,createdAt,autoMergeRequest,author",
        ],
        expect_json=True,
    )

    pr_url = str(pr.get("url") or f"PR #{pr_number}")

    if not should_process_pr(pr):
        print(f"Skipping PR #{pr_number} (not eligible yet)")
        return

    if pr.get("autoMergeRequest") is not None:
        print(f"Auto-merge already enabled for {pr_url}")
        return

    if not checks_are_green(pr_number, repository):
        print(f"Checks are not green yet for {pr_url}")
        return

    print(f"Enabling auto-merge for {pr_url}")
    run_gh(
        [
            "pr",
            "merge",
            pr_url,
            "--repo",
            repository,
            "--auto",
            "--squash",
            "--delete-branch",
        ]
    )


def list_candidate_pr_numbers(repository: str) -> list[int]:
    prs = run_gh(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--json",
            "number,headRefName,baseRefName,author,isDraft",
        ],
        expect_json=True,
    )

    numbers: list[int] = []
    for pr in prs:
        if should_process_pr(pr):
            number = pr.get("number")
            if isinstance(number, int):
                numbers.append(number)
    return numbers


def main() -> int:
    try:
        _ = env_required("GH_TOKEN")
        repository = env_required("REPOSITORY")
        event_name = env_required("EVENT_NAME")
        event_actor = env_required("EVENT_ACTOR")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if event_name == "pull_request_target":
        if event_actor != DEPENDABOT_LOGIN:
            print(f"Skipping non-Dependabot actor: {event_actor}")
            return 0

        pr_number_raw = os.getenv("PR_NUMBER", "").strip()
        if pr_number_raw == "":
            print(
                "PR_NUMBER is required for pull_request_target events", file=sys.stderr
            )
            return 1

        try:
            pr_number = int(pr_number_raw)
        except ValueError:
            print(
                f"PR_NUMBER must be an integer, got {pr_number_raw!r}", file=sys.stderr
            )
            return 1

        process_pr(pr_number, repository)
        return 0

    pr_numbers = list_candidate_pr_numbers(repository)
    if not pr_numbers:
        print("No open Dependabot GitHub Actions PRs found")
        return 0

    for pr_number in pr_numbers:
        process_pr(pr_number, repository)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
