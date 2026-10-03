#!/usr/bin/env python3
"""Detect unattended autonomous PR runs from durable GitHub checkpoints."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

MARKER_RE = re.compile(
    r"<!--\s*agent-run-health\s*(\{.*?\})\s*-->",
    re.DOTALL,
)
NOTIFICATION_PREFIX = "<!-- agent-run-watchdog:"
VALID_MODES = {"active", "handoff", "stalled", "complete"}
VALID_EXPECTED = {"ci", "review", "none"}
TRUSTED_CHECKPOINT_ASSOCIATIONS = {"OWNER", "COLLABORATOR"}
WATCHDOG_COMMENT_LOGIN = "github-actions[bot]"


@dataclass(frozen=True)
class Evidence:
    kind: str
    observed_at: datetime
    summary: str
    url: str = ""


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def parse_marker(body: str) -> dict[str, str] | None:
    match = MARKER_RE.search(body or "")
    if match is None:
        return None
    data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise ValueError("run-health marker must be a JSON object")

    required = ("mode", "phase", "expected", "head_sha")
    if any(not isinstance(data.get(key), str) or not data[key] for key in required):
        raise ValueError("run-health marker is missing required string fields")
    if data["mode"] not in VALID_MODES:
        raise ValueError(f"unsupported run-health mode: {data['mode']}")
    if data["expected"] not in VALID_EXPECTED:
        raise ValueError(f"unsupported expected event: {data['expected']}")
    return data


def render_marker(marker: dict[str, Any]) -> str:
    encoded = json.dumps(marker, sort_keys=True, separators=(",", ":"))
    head = str(marker["head_sha"])[:12]
    return (
        f"<!-- agent-run-health {encoded} -->\n"
        f"Run health: `{marker['mode']}` · phase `{marker['phase']}` · "
        f"waiting for `{marker['expected']}` · head `{head}`."
    )


def is_trusted_checkpoint_comment(comment: dict[str, Any]) -> bool:
    return comment.get("author_association") in TRUSTED_CHECKPOINT_ASSOCIATIONS


def latest_checkpoint(
    comments: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str]] | None:
    checkpoints = []
    for comment in comments:
        if not is_trusted_checkpoint_comment(comment):
            continue
        try:
            marker = parse_marker(comment.get("body", ""))
        except (json.JSONDecodeError, ValueError):
            continue
        if marker is not None:
            checkpoints.append((parse_time(comment["updated_at"]), comment, marker))
    if not checkpoints:
        return None
    _, comment, marker = max(checkpoints, key=lambda item: item[0])
    return comment, marker


def latest_ci_evidence(
    workflow_runs: list[dict[str, Any]],
    head_sha: str,
) -> Evidence | None:
    candidates = []
    for run in workflow_runs:
        if run.get("head_sha") != head_sha or run.get("status") != "completed":
            continue
        if run.get("name") != "CI":
            continue
        observed = parse_time(run["updated_at"])
        conclusion = run.get("conclusion") or "unknown"
        number = run.get("run_number")
        candidates.append(
            Evidence(
                kind="ci",
                observed_at=observed,
                summary=f"CI run #{number} completed with {conclusion}",
                url=run.get("html_url", ""),
            )
        )
    return max(candidates, key=lambda item: item.observed_at, default=None)


def latest_review_evidence(
    reviews: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    head_sha: str,
) -> Evidence | None:
    candidates = []

    for review in reviews:
        if review.get("commit_id") != head_sha:
            continue
        timestamp = review.get("submitted_at")
        if not timestamp:
            continue
        candidates.append(
            Evidence(
                kind="review",
                observed_at=parse_time(timestamp),
                summary=(
                    "PR review submitted with state "
                    f"{review.get('state', 'unknown')}"
                ),
                url=review.get("html_url", ""),
            )
        )

    for comment in review_comments:
        if comment.get("commit_id") != head_sha:
            continue
        timestamp = comment.get("updated_at") or comment.get("created_at")
        if not timestamp:
            continue
        candidates.append(
            Evidence(
                kind="review-comment",
                observed_at=parse_time(timestamp),
                summary="Inline PR review comment added or updated",
                url=comment.get("html_url", ""),
            )
        )

    return max(candidates, key=lambda item: item.observed_at, default=None)


def should_stall(
    marker: dict[str, str],
    checkpoint_updated_at: datetime,
    current_head_sha: str,
    evidence: Evidence | None,
    now: datetime,
    threshold: timedelta,
) -> bool:
    if marker["mode"] != "active":
        return False
    if marker["expected"] == "none":
        return False
    if marker["head_sha"] != current_head_sha:
        return False
    if evidence is None or evidence.observed_at <= checkpoint_updated_at:
        return False
    return now - evidence.observed_at >= threshold


def stall_key(
    pr_number: int,
    checkpoint_comment: dict[str, Any],
    marker: dict[str, str],
) -> str:
    value = (
        f"{pr_number}|{checkpoint_comment.get('id')}|"
        f"{checkpoint_comment.get('updated_at')}|{marker['head_sha']}|"
        f"{marker['phase']}|{marker['expected']}"
    )
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def is_watchdog_notification(comment: dict[str, Any], marker: str) -> bool:
    return (
        marker in comment.get("body", "")
        and comment.get("user", {}).get("login") == WATCHDOG_COMMENT_LOGIN
    )


def notification_body(
    pr_number: int,
    marker: dict[str, str],
    evidence: Evidence,
    key: str,
) -> str:
    next_action = {
        "ci": (
            "Re-fetch the current PR/head and completed CI. Diagnose failures or "
            "continue through the next review/landing gate if CI is green."
        ),
        "review": (
            "Re-fetch the current PR/head plus review submissions/comments. "
            "Address actionable findings or continue if review is clear."
        ),
    }.get(marker["expected"], "Re-fetch the current PR state before continuing.")

    evidence_link = f" ({evidence.url})" if evidence.url else ""
    return (
        f"{NOTIFICATION_PREFIX}{key} -->\n"
        "### Autonomous run appears stalled\n\n"
        f"- PR: #{pr_number}\n"
        f"- Head: `{marker['head_sha']}`\n"
        f"- Phase: `{marker['phase']}`\n"
        f"- Expected event: `{marker['expected']}`\n"
        f"- New evidence: {evidence.summary}{evidence_link}\n\n"
        f"**Resume packet:** {next_action}\n\n"
        "The watchdog only detects and records the stall. It does not merge, "
        "edit product code, or restart a stopped ChatGPT/web-chat execution."
    )


class GitHubClient:
    def __init__(self, repo: str, token: str, api_url: str) -> None:
        self.repo = repo
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "christmas-quiz-agent-run-watchdog",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                if response.status == 204:
                    return None
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise RuntimeError(
                f"GitHub API {method} {path} failed: {exc.code} {detail}"
            ) from exc

    def get(self, path: str) -> Any:
        return self.request("GET", path)

    def get_all(self, path: str) -> list[dict[str, Any]]:
        items = []
        page = 1
        separator = "&" if "?" in path else "?"
        while True:
            batch = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(batch, list):
                raise RuntimeError(f"expected list response while paginating {path}")
            items.extend(batch)
            if len(batch) < 100:
                return items
            page += 1

    def post(self, path: str, payload: dict[str, Any]) -> Any:
        return self.request("POST", path, payload)


def review_evidence(
    client: GitHubClient,
    pr_number: int,
    head_sha: str,
) -> Evidence | None:
    reviews = client.get_all(
        f"/repos/{client.repo}/pulls/{pr_number}/reviews"
    )
    review_comments = client.get_all(
        f"/repos/{client.repo}/pulls/{pr_number}/comments"
    )
    return latest_review_evidence(reviews, review_comments, head_sha)


def ci_evidence(
    client: GitHubClient,
    head_sha: str,
) -> Evidence | None:
    query = urllib.parse.urlencode(
        {
            "head_sha": head_sha,
            "event": "pull_request",
            "per_page": 50,
        }
    )
    result = client.get(f"/repos/{client.repo}/actions/runs?{query}")
    return latest_ci_evidence(result.get("workflow_runs", []), head_sha)


def revalidate_stall_candidate(
    client: GitHubClient,
    pr_number: int,
    head_sha: str,
    checkpoint_comment: dict[str, Any],
    marker: dict[str, str],
    evidence: Evidence,
    now: datetime,
    threshold: timedelta,
) -> tuple[bool, list[dict[str, Any]]]:
    current_pull = client.get(f"/repos/{client.repo}/pulls/{pr_number}")
    if current_pull.get("state") != "open":
        return False, []
    if current_pull.get("head", {}).get("sha") != head_sha:
        return False, []

    comments = client.get_all(f"/repos/{client.repo}/issues/{pr_number}/comments")
    checkpoint = latest_checkpoint(comments)
    if checkpoint is None:
        return False, comments

    current_comment, current_marker = checkpoint
    if current_comment.get("id") != checkpoint_comment.get("id"):
        return False, comments
    if current_comment.get("updated_at") != checkpoint_comment.get("updated_at"):
        return False, comments
    if current_marker != marker:
        return False, comments

    current_updated_at = parse_time(current_comment["updated_at"])
    if not should_stall(
        current_marker,
        current_updated_at,
        head_sha,
        evidence,
        now,
        threshold,
    ):
        return False, comments
    return True, comments


def run_watchdog(
    client: GitHubClient,
    threshold_minutes: int,
    dry_run: bool,
) -> int:
    now = datetime.now(timezone.utc)
    threshold = timedelta(minutes=threshold_minutes)
    pulls = client.get_all(f"/repos/{client.repo}/pulls?state=open")
    stalled_count = 0

    for pull in pulls:
        pr_number = int(pull["number"])
        comments = client.get_all(
            f"/repos/{client.repo}/issues/{pr_number}/comments"
        )
        checkpoint = latest_checkpoint(comments)
        if checkpoint is None:
            continue

        checkpoint_comment, marker = checkpoint
        try:
            checkpoint_updated_at = parse_time(checkpoint_comment["updated_at"])
        except (KeyError, ValueError):
            print(f"PR #{pr_number}: invalid checkpoint timestamp", file=sys.stderr)
            continue

        head_sha = pull["head"]["sha"]
        if marker["mode"] != "active":
            continue
        if marker["head_sha"] != head_sha:
            print(
                f"PR #{pr_number}: checkpoint head differs from current head; "
                "leaving it for the next primary-thread resume"
            )
            continue

        if marker["expected"] == "ci":
            evidence = ci_evidence(client, head_sha)
        elif marker["expected"] == "review":
            evidence = review_evidence(client, pr_number, head_sha)
        else:
            continue

        if not should_stall(
            marker,
            checkpoint_updated_at,
            head_sha,
            evidence,
            now,
            threshold,
        ):
            continue

        assert evidence is not None
        key = stall_key(pr_number, checkpoint_comment, marker)
        notification_marker = f"{NOTIFICATION_PREFIX}{key} -->"

        if dry_run:
            print(
                f"PR #{pr_number}: would mark stalled after {evidence.summary}; "
                f"checkpoint={checkpoint_updated_at.isoformat()}"
            )
            stalled_count += 1
            continue

        valid, current_comments = revalidate_stall_candidate(
            client,
            pr_number,
            head_sha,
            checkpoint_comment,
            marker,
            evidence,
            now,
            threshold,
        )
        if not valid:
            print(
                f"PR #{pr_number}: progress changed during watchdog evaluation; "
                "skipping stale stall notification"
            )
            continue

        already_notified = any(
            is_watchdog_notification(comment, notification_marker)
            for comment in current_comments
        )
        if already_notified:
            continue

        client.post(
            f"/repos/{client.repo}/issues/{pr_number}/comments",
            {"body": notification_body(pr_number, marker, evidence, key)},
        )
        print(
            f"PR #{pr_number}: stalled after {evidence.summary}; "
            f"checkpoint={checkpoint_updated_at.isoformat()}"
        )
        stalled_count += 1

    return stalled_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument(
        "--api-url",
        default=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    parser.add_argument("--threshold-minutes", type=int, default=45)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.repo or "/" not in args.repo:
        raise SystemExit("--repo or GITHUB_REPOSITORY must be owner/name")
    if not args.token:
        raise SystemExit("--token or GITHUB_TOKEN is required")
    if args.threshold_minutes < 1:
        raise SystemExit("--threshold-minutes must be positive")

    client = GitHubClient(args.repo, args.token, args.api_url)
    stalled = run_watchdog(client, args.threshold_minutes, args.dry_run)
    print(f"watchdog complete: {stalled} stalled run(s) detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
