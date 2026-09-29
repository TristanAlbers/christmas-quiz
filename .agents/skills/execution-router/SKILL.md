---
name: execution-router
description: Choose the most efficient execution path for Christmas Quiz work: GitHub/web-chat orchestration, local Codex, or Codex Cloud. Use when the user asks where/how work should run, asks for implementation prompts, or when selecting the wrong environment would materially increase iteration cost.
---

Use this skill before substantial work when execution environment materially affects speed, observability, validation, or model-credit cost. The goal is to route work to the cheapest environment that can reliably satisfy the required feedback loop without weakening quality gates.

## Boundary

- Follow `AGENTS.md` and repository authority.
- Routing is about execution efficiency, not reducing quality gates.
- Do not claim an environment can run tools it does not have. When this chat cannot execute a required local workflow, provide the bounded prompt/packet for the chosen environment instead.
- Prefer one primary environment for a task. Split work only when there is a clear handoff boundary.
- When Codex usage is constrained, treat local/cloud Codex as a scarce execution resource: do not spend it on waiting, polling, routine GitHub orchestration, or CI failures that can be diagnosed from GitHub evidence.

## 1. Classify the task

Identify:
- whether the task is analysis/orchestration or code implementation;
- whether GitHub Actions can provide the required deterministic execution/validation feedback even if the current chat cannot run the code locally;
- whether repeated local-only test/debug cycles are truly required, rather than merely convenient;
- whether Docker, Playwright, browser/device behavior, LAN/network access, or local files/services require direct observation unavailable in CI;
- whether the implementation packet is small and well specified;
- whether GitHub state/reviews/CI/merging dominate the work;
- whether the issue is oversized and first needs decomposition or a contract.

Apply `.agents/skills/work-github-issue/SKILL.md` sizing rules when a GitHub issue is involved.

## 2. Route to GitHub/web-chat + CI orchestration

Prefer this path by default when the repository can be safely edited through GitHub and GitHub Actions can validate the result, including ordinary implementation work that may require several CI repair iterations.

This path is especially suitable for:
- issue/PR analysis and decomposition;
- specification and architecture review;
- bounded code/documentation implementation that can be pushed coherently to a draft PR;
- review-comment triage and repair;
- CI/log diagnosis using exact-head repository evidence;
- issue creation/refinement;
- merge ordering and safe landing;
- preparing precise prompts/handoffs for local or cloud implementation when escalation is actually needed.

Use GitHub Actions as the remote deterministic executor: patch -> push -> CI -> diagnose -> repair -> push. A CI failure is normally new evidence for the next autonomous iteration, not a reason to route immediately to Codex or ask the user to continue.

When Codex budget is explicitly constrained, strongly prefer this path unless a required capability is unavailable or the GitHub-only edit/test loop has become demonstrably inefficient or ambiguous.

## 3. Route to local Codex only when it adds unique value

Prefer local execution when the task materially benefits from capabilities that GitHub/web-chat + CI cannot provide efficiently, especially:
- interactive Playwright/browser debugging that requires observing live behavior repeatedly;
- Docker/Compose behavior that differs from CI or requires local service inspection;
- LAN/device/phone/TV/network testing;
- packaging/setup problems specific to the local environment;
- flaky or timing-sensitive failures where CI evidence is insufficient to form a credible repair hypothesis;
- an editing-heavy multi-file change where direct checkout manipulation is substantially more efficient than GitHub file operations.

Do not route to local Codex merely because multiple CI iterations may be needed. Do not spend local Codex time waiting for CI/review, polling GitHub, performing routine merge orchestration, or repeatedly rereading unchanged repository state.

When local Codex is selected, give it the smallest bounded packet, relevant skills/agents, focused local validation, and an explicit durable endpoint such as commit/push to an existing branch. Return orchestration to GitHub/web-chat after that endpoint unless another local-only capability is still required.

## 4. Route to Codex Cloud

Prefer Cloud only when:
- the task is a bounded, well-specified implementation packet;
- repository setup is known to work in Cloud;
- no local hardware/network/browser observation is required;
- validation can be performed with repository tests and GitHub Actions;
- the expected work fits one issue skill packet or one explicit staged-work packet;
- using the cloud agent is worth the agentic usage cost compared with GitHub/web-chat + CI.

Avoid Cloud for ambiguous exploratory work, repeated environment debugging, routine CI/review orchestration, or large cross-domain mandates. First decompose/contract those tasks elsewhere.

## 5. Split only at durable handoffs

Useful splits include:
- chat investigates/sizes -> local Codex performs one local-only implementation/debug packet -> chat + CI verify/repair/review/land;
- chat diagnoses CI -> local Codex reproduces a genuinely local-only failure -> chat resumes at the resulting commit/SHA;
- architect/contract stage -> one bounded implementation environment.

Do not bounce the same unresolved implementation repeatedly between environments. Preserve a durable handoff: issue/contract, branch, PR, exact SHA, failing test, or written diagnosis.

## 6. Review-budget discipline

Do not trigger Codex review on known-incomplete or failing heads. Keep implementation PRs draft until required CI is green for the exact current head and current-main/mergeability has been rechecked.

For subsequent reviews after fixes, preserve the last reviewed SHA and prefer a focused instruction such as: review only changes since `<last-reviewed-SHA>`, verify the prior findings are resolved, and report regressions introduced by those fixes. This is review guidance, not a guaranteed delta-only mode.

## 7. Output

When routing is the requested deliverable, report for each task:
- chosen environment;
- why that environment fits;
- required skill/agent;
- expected validation route;
- concise copy-paste prompt when the user must start the task elsewhere.

If the current chat is the selected environment and the user already authorized the work, proceed rather than merely recommending it.
