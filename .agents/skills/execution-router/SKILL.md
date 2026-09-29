---
name: execution-router
description: Choose the most efficient execution path for Christmas Quiz work: GitHub/web-chat orchestration, local Codex, or Codex Cloud. Use when the user asks where/how work should run, asks for implementation prompts, or when selecting the wrong environment would materially increase iteration cost.
---

Use this skill before substantial work when execution environment materially affects speed, observability, or validation. The goal is to route work to the cheapest environment that can reliably satisfy the required feedback loop.

## Boundary

- Follow `AGENTS.md` and repository authority.
- Routing is about execution efficiency, not reducing quality gates.
- Do not claim an environment can run tools it does not have. When this chat cannot execute a required local workflow, provide the bounded prompt/packet for the chosen environment instead.
- Prefer one primary environment for a task. Split work only when there is a clear handoff boundary.

## 1. Classify the task

Identify:
- whether the task is analysis/orchestration or code implementation;
- whether repeated local test/debug cycles are expected;
- whether Docker, Playwright, browser/device behavior, LAN/network access, or local files/services are required;
- whether the implementation packet is small and well specified;
- whether GitHub state/reviews/CI/merging dominate the work;
- whether the issue is oversized and first needs decomposition or a contract.

Apply `.agents/skills/work-github-issue/SKILL.md` sizing rules when a GitHub issue is involved.

## 2. Route to GitHub/web-chat orchestration

Prefer this path for:
- issue/PR analysis and decomposition;
- specification and architecture review;
- review-comment triage;
- CI/log diagnosis using repository evidence;
- issue creation/refinement;
- merge ordering and safe landing;
- small repository/documentation changes that can be safely made and validated through GitHub;
- preparing precise prompts/handoffs for local or cloud implementation.

This path is especially useful when the task is mostly repository state rather than rapid code/test iteration.

## 3. Route to local Codex

Prefer local execution when the task benefits from a tight edit/test/debug loop or local environment access, especially:
- Playwright/browser debugging;
- Docker/Compose behavior;
- flaky or timing-sensitive test reproduction;
- UI work requiring repeated visual/browser verification;
- LAN/device/phone/TV/network testing;
- packaging/setup problems that differ between environments;
- multi-file refactors where many focused tests should run before a push.

Local Codex should still use repository skills/agents and a short-lived branch. Give it the smallest issue/stage packet and focused validation commands/expectations.

## 4. Route to Codex Cloud

Prefer Cloud when:
- the task is a bounded, well-specified implementation packet;
- repository setup is known to work in Cloud;
- no local hardware/network/browser observation is required;
- validation can be performed with repository tests and GitHub Actions;
- the expected work fits one issue skill packet or one explicit staged-work packet.

Avoid Cloud for ambiguous exploratory work, repeated environment debugging, or large cross-domain mandates. First decompose/contract those tasks elsewhere.

## 5. Split only at durable handoffs

Useful splits include:
- chat investigates/sizes -> local Codex implements/tests -> chat reviews/lands;
- chat diagnoses CI -> owning local/cloud agent repairs -> chat verifies/lands;
- architect/contract stage -> one bounded implementation environment.

Do not bounce the same unresolved implementation repeatedly between environments. Preserve a durable handoff: issue/contract, branch, PR, exact SHA, failing test, or written diagnosis.

## 6. Output

When routing is the requested deliverable, report for each task:
- chosen environment;
- why that environment fits;
- required skill/agent;
- expected validation route;
- concise copy-paste prompt when the user must start the task elsewhere.

If the current chat is the selected environment and the user already authorized the work, proceed rather than merely recommending it.
