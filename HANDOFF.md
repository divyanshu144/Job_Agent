# Session Handoff

**Updated:** 2026-08-02
**Branch:** main

---

## Current State

AWS cost teardown review and remediation. **No application code changed** — this
session was infrastructure audit plus documentation. `main` remains at `934ec3f`
feature-wise; the only code-tree change is a `.gitignore` line.

Audited the live AWS account against the cost runbook. Its cost figures were accurate
(July usage-type data reconciles exactly), but three rebuild-blocking errors were found
in its instructions:

1. **ALB routing was inverted.** Real config per `infra/aws/scripts/08_create_alb.sh:98-123`
   is listener default → `jobfit-frontend-tg`, with a priority-10 `/api/*` rule →
   `jobfit-api-tg`. The runbook had 443 forwarding to the API and never mentioned the
   frontend target group.
2. **`08_create_alb.sh` creates HTTP only** (see its own warning at line 136) and never
   attaches the ACM cert. The deleted ALB had an HTTPS:443 listener added manually.
3. **`05_create_redis.sh` builds `cache.t4g.micro`**, not the `cache.t3.micro` that was
   deleted.

Also corrected the running-cost table, which omitted the per-task public IPv4 charge
($0.48/day for four tasks) and therefore did not reconcile to the July bill.

Corrected runbook written to `infra/aws/RUNBOOK.md` and **gitignored** — the repo is
PUBLIC and the doc carries account, VPC, snapshot and security-group identifiers.

Tightened the `jobfit-scheduler-scaledown` trust policy with `aws:SourceAccount` +
`aws:SourceArn` conditions. First attempt used `schedule/default/*`; EventBridge
Scheduler requires the **schedule group** ARN (`schedule-group/default`). Six retries
over a minute ruled out IAM propagation lag. Corrected policy is live and **verified
end-to-end** — a temporary no-op schedule fired and CloudTrail confirmed
`assumed-role/jobfit-scheduler-scaledown` called `UpdateService` at 08:39:08Z with no
error. Temporary schedule deleted; the four production schedules remain ENABLED.

Budget lowered from $50 to **$15/month**. Thresholds are percentages so they rescaled
automatically (85% = $12.75, 100% = $15); all three notifications and the email
subscriber survived the `update-budget` replace, verified afterwards.

Then, on branch `fix/eval-severity-gating`: fixed the eval suite's severity gating.
`runner.py` computed `passed = not failures` and never consulted warnings, so
`severity="error"` findings were reported and ignored — the suite could not go red.
Error-severity warnings now promote into `failures`; `severity="warn"` stays advisory.

This exposed that the fixture was never compliant: all 5 cases violate the production
`cover_letter` 150-word minimum (bodies are 75-86 words). Suite went 5/5 → **0/5**,
exit code 1. That is the intended outcome, not a regression.

## Next Action

**Branch `fix/eval-severity-gating` is intentionally RED.** Decide how to make the
fixture honest, then unblock:

- **Option A (recommended):** raise the five mocked `cover_letter.body` texts in
  `tests/fixtures/evals/jobfit_eval_cases.json` to >=150 words so they meet the
  production validator, and delete the per-case `cover_letter_min_words` overrides
  (75/70/70/65/70) — each was tuned just *below* its own mock, which is why this
  never fired.
- **Option B:** lower `validators.py:241` from 150 if 150 is not the real product
  standard.

Pick ONE source of truth. Today there are three: validator 150,
`CompletenessRules` default 120, per-case fixture overrides 65-75.

Then re-run `python3 scripts/run_evals.py` (expect 5/5, exit 0) and
`python3 -m pytest tests/test_evals/ -q` (expect 56 passed).

Also still open from the AWS work: whether `infra/aws/RUNBOOK.md` stays gitignored
(current state) or gets committed. Repo is PUBLIC and the doc has account, VPC,
snapshot and SG identifiers; a redacted copy under `docs/` is a third option.

## Why It Stopped

Awaiting a decision on the eval fixture (Option A vs B). The severity-gating fix is
complete and correct; the red suite is the honest outcome, not a defect to patch away.

## In-Flight

- Branch `fix/eval-severity-gating` — `backend/evals/runner.py` committed there.
  `tests/test_evals/test_dataset_regression.py::test_deterministic_eval_dataset_passes`
  FAILS by design (it asserted the fixture passes; it no longer does). 55 other eval
  tests pass. **Do not merge until the fixture decision is made.**
- `main` is clean and green — the red is isolated to the branch.
- `infra/aws/RUNBOOK.md` — gitignored, intentionally untracked, lives only on this machine

## Open Questions

- **Runbook tracking** — see Next Action.
- **Next real scale-down is 2026-08-03 02:00 UTC.** The trust policy is verified via a
  synthetic invocation, but the production schedules have not yet fired under it. Worth
  a CloudTrail spot-check (`EventName=UpdateService`, principal
  `assumed-role/jobfit-scheduler-scaledown`) after that run.
- **Forecast alert will fire spuriously** for a few days — the budget forecast still
  reads ~$195 against the new $15 limit because Cost Explorer has not re-baselined on
  idle data. Not a real signal until the forecast settles near $2.
- **Carried over, not started:** profile-grounded resume generation. `resume_tailorer`
  over-omits items the candidate has in their profile/projects because it grounds against
  the base resume rather than the full profile (YAML + CV + semantic memory). Needs its
  own brainstorm + plan; touches `resume_tailorer`, `context_builder`, `profile_builder`,
  and the faithfulness validator.

## Verification Baseline

| Check | Result |
|---|---|
| `make test` | Not run — no application code changed this session |
| `make lint` | Not run — no application code changed this session |
| `make check` | Not run — no application code changed this session |

Last known good (from `934ec3f`, 2026-07-27): `make test` 713 passing · 82.88% coverage.

AWS-side verification performed this session: ECS services 0 desired / 0 running ·
RDS deleted, snapshot `jobfit-postgres-final-2026-08-02` available · **0 automated
snapshots remain** (single copy of the data) · ElastiCache, ALB and all Elastic IPs
gone · both target groups survive · 4 scale-down schedules ENABLED · log retention 30d
on all four groups · ECR lifecycle policy applied to all four repos.
