# Local Kubernetes

This directory contains a practical local Kubernetes deployment for JobFit Agent.
It is intended for `kind` or `minikube`, uses plain manifests, and does not use
Helm, cloud Kubernetes, managed Postgres, or managed Redis.

The first version uses `kubectl port-forward` for local access. Ingress is not
required.

## Prerequisites

- Docker
- kubectl
- kind or minikube

## Create a kind Cluster

```bash
kind create cluster --name jobfit
```

If the cluster already exists:

```bash
kind get clusters
kubectl cluster-info --context kind-jobfit
```

## Build Local Images

```bash
docker build --target api -t jobfit-api:local .
docker build --target worker -t jobfit-worker:local .
docker build --target beat -t jobfit-beat:local .
docker build -t jobfit-frontend:local ./frontend
```

## Load Images Into kind

```bash
kind load docker-image jobfit-api:local --name jobfit
kind load docker-image jobfit-worker:local --name jobfit
kind load docker-image jobfit-beat:local --name jobfit
kind load docker-image jobfit-frontend:local --name jobfit
```

For minikube, either build inside the minikube Docker environment or load images
with `minikube image load`.

## Secrets

`k8s/secret.example.yaml` contains placeholders only. For local demos it can be
applied as-is, but do not put real API keys, OAuth tokens, or resumes into a
committed manifest.

For real local testing with Anthropic or external integrations, create your own
untracked secret manifest or use `kubectl create secret`.

## Apply Manifests

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

## Check Status

```bash
kubectl -n jobfit get pods
kubectl -n jobfit get svc
kubectl -n jobfit get pvc
kubectl -n jobfit logs deploy/api
kubectl -n jobfit logs deploy/worker
```

## Local Access

Frontend:

```bash
kubectl -n jobfit port-forward svc/frontend 8080:80
```

Open:

```text
http://127.0.0.1:8080
```

API:

```bash
kubectl -n jobfit port-forward svc/api 8000:8000
curl -i http://127.0.0.1:8000/health
```

The frontend nginx image proxies `/api/*` to the Kubernetes Service named `api`,
matching the Docker Compose service-name assumption.

## Validation

```bash
kubectl -n jobfit exec deploy/redis -- redis-cli ping
kubectl -n jobfit exec statefulset/postgres -- pg_isready -U jobfit -d jobfit
kubectl -n jobfit exec statefulset/postgres -- psql -U jobfit -d jobfit -c '\dt'
kubectl -n jobfit exec deploy/worker -- celery -A backend.celery_app:celery_app inspect ping --timeout=10
kubectl -n jobfit exec deploy/api -- sh -lc 'command -v pdflatex || echo "pdflatex absent from api"'
kubectl -n jobfit exec deploy/worker -- sh -lc 'command -v pdflatex'
kubectl -n jobfit exec deploy/beat -- sh -lc 'command -v pdflatex || echo "pdflatex absent from beat"'
```

Or run the smoke script:

```bash
scripts/k8s_smoke.sh
```

## Cleanup

Delete app resources:

```bash
kubectl delete -f k8s/
```

Delete the kind cluster:

```bash
kind delete cluster --name jobfit
```

## Known Limitations

- This is a local Kubernetes deployment, not a production cluster design.
- Postgres uses an in-cluster StatefulSet and PVC for local persistence only.
- Redis is a single Deployment without persistence.
- Celery beat must stay at one replica to avoid duplicate scheduled work.
- Real `assets/resume.tex` is not mounted into Kubernetes yet. The image uses
  the non-PII fallback generated from `assets/resume.example.tex`.
- Ingress is intentionally omitted from the first version; use port-forward.
