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

Trust policy verified end-to-end; temporary schedule deleted. Budget lowered to $15.
Nothing outstanding on the AWS work.

**Decision needed:** whether `infra/aws/RUNBOOK.md` should stay gitignored (current
state) or be committed. The repo is PUBLIC and the doc contains account, VPC, snapshot
and security-group identifiers. A redacted copy under `docs/` is the third option.

## Why It Stopped

Awaiting the user's call on tracking the runbook. All requested AWS changes are applied
and verified.

## In-Flight

- `infra/aws/RUNBOOK.md` — gitignored, intentionally untracked, lives only on this machine
- No uncommitted tracked files

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
