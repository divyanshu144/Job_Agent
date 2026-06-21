# TODO

> Snapshot reset 2026-06-21. The FDE-readiness goal (5 tasks) and the multi-tenant
> campaign feature are complete and shipped (history through `87117f2`); the prior
> detailed checklist is preserved in git history. Deployment/infra work since then
> is also shipped (see HANDOFF.md for the commit-by-commit breakdown).

## Done (shipped on main)

- [x] FDE readiness: health/metrics, agent retry+breaker, campaign UI, consistency evals, rate limiting
- [x] Multi-tenant campaign system (backend units 1–6 + frontend) + two review rounds + cleanup pass
- [x] Docker (multi-stage) + docker-compose + prod override + local Kubernetes manifests
- [x] CI: `make check` + Docker image build/smoke workflows
- [x] AWS ECS Fargate deployment (`deploy-aws.yml`, `aws-migrate.yml`, `infra/aws/` task defs); RDS + ElastiCache
- [x] OpenAI semantic embeddings + pgvector with keyword fallback (`services/memory.py`)
- [x] Resume PDF tooling: dedicated `backend-tex` Docker stage (api+worker only)
- [x] Docs sync (CLAUDE.md / README.md / HANDOFF.md / todo.md) to current architecture

## Open / candidate (not committed to)

- [ ] Dockerfile cache regression: move texlive install above `COPY backend/` so backend
      code edits don't re-install TeX for the api/worker images (from /code-review of `eacd3d7`)
- [ ] Drop redundant `chown -R appuser:appuser /app` in the `backend-tex` stage
- [ ] Decide/commit the `infra/aws/task-definitions/*` CORS change for the `app.jobfitapp.uk` cutover
- [ ] `GET/PATCH /api/campaign/settings` route pair (enabled toggle + caps display)
- [ ] Per-run cost on `CampaignRunResponse`
- [ ] Redis `storage_uri` for the rate limiter when going multi-worker
