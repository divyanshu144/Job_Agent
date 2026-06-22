# Python + pip deps only — no source, no TeX. Shared parent for every backend image.
FROM python:3.11-slim AS python-deps
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source assembly with NO TeX. This is the beat image, and the source layer the
# api/worker TeX image copies from.
FROM python-deps AS backend-base
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY backend/ ./backend/
COPY data/ ./data/
COPY assets/resume.example.tex ./assets/resume.example.tex
COPY assets/latex-format.tex ./assets/latex-format.tex
COPY assets/target_companies.json ./assets/target_companies.json
RUN mkdir -p data assets \
    && cp assets/resume.example.tex assets/resume.tex \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
ENV PYTHONPATH=/app
EXPOSE 8000
USER appuser

# TeX image for api/worker. texlive is installed on python-deps BEFORE any source,
# so changing backend code never reinstalls it — only the final source COPY layer
# rebuilds. The assembled app is copied from backend-base (single source of truth).
FROM python-deps AS backend-tex
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --shell /usr/sbin/nologin appuser
COPY --from=backend-base --chown=appuser:appuser /app /app
ENV PYTHONPATH=/app
EXPOSE 8000
USER appuser

FROM backend-tex AS api
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM backend-tex AS worker
CMD ["celery", "-A", "backend.celery_app:celery_app", "worker", "--loglevel=info"]

FROM backend-base AS beat
CMD ["celery", "-A", "backend.celery_app:celery_app", "beat", "--loglevel=info"]
