FROM python:3.11-slim AS backend-base
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
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

FROM backend-base AS backend-tex
USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R appuser:appuser /app
USER appuser

FROM backend-tex AS api
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM backend-tex AS worker
CMD ["celery", "-A", "backend.celery_app:celery_app", "worker", "--loglevel=info"]

FROM backend-base AS beat
CMD ["celery", "-A", "backend.celery_app:celery_app", "beat", "--loglevel=info"]
