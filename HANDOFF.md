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
over a minute ruled out IAM propagation lag. Corrected policy is live and accepted by
`create-schedule`.

## Next Action

Read `/private/tmp/claude-501/-Users-divyanshu-Desktop-All-Projects-Job-Ready-Agent/6c8138f6-38c1-48f3-a9f6-4f57c300e686/tasks/bn8bjd24m.output`
for `AWS/Scheduler` invocation metrics (`InvocationAttemptCount`, `TargetErrorCount`,
`InvocationDroppedCount`, window 08:30–08:50Z on 2026-08-02).

- If an invocation was attempted and `TargetErrorCount` is 0:
  `aws scheduler delete-schedule --name jobfit-trustpolicy-verify --region eu-west-2`
- If it errored: restore the original trust policy from
  `scratchpad/trust-policy.backup.json` with
  `aws iam update-assume-role-policy --role-name jobfit-scheduler-scaledown --policy-document file://<path>`,
  then delete the temporary schedule.

If the scratchpad is gone, the backup policy is simply the same document with the
entire `Condition` block removed.

## Why It Stopped

Awaiting a timed AWS verification. Temporary no-op schedule `jobfit-trustpolicy-verify`
was created to fire at 08:38:27 UTC (sets api desired count to 0, already 0); metrics
queried at ~08:41:30 UTC. Creation-time validation already passed, but that only proves
the role is assumable, not that an invocation succeeds.

## In-Flight

- `.gitignore` — added `infra/aws/RUNBOOK.md` (committed alongside this handoff)
- `infra/aws/RUNBOOK.md` — gitignored, intentionally untracked, lives only on this machine
- AWS: temporary schedule `jobfit-trustpolicy-verify` exists and **must be deleted**

## Open Questions

- **Budget threshold.** $50/month against a ~$2/month idle run rate. Lowering to $15
  was recommended (trips at ~2 days of the rebuilt stack running) but not applied.
- **Next real scale-down is 2026-08-03 02:00 UTC.** Even if the temporary verify passes,
  spot-check `TargetErrorCount` after it to confirm the production schedules fire under
  the new trust policy.
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
