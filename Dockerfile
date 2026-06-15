FROM python:3.11-slim AS backend-base
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY backend/ ./backend/
COPY data/ ./data/
COPY assets/resume.example.tex ./assets/resume.example.tex
COPY assets/target_companies.json ./assets/target_companies.json
RUN mkdir -p data assets \
    && cp assets/resume.example.tex assets/resume.tex \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
ENV PYTHONPATH=/app
EXPOSE 8000
USER appuser

FROM backend-base AS api
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM backend-base AS worker
USER root
# TeX is only required by campaign PDF resume generation
# (backend/services/resume_latex.py shells out to pdflatex).
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*
USER appuser
CMD ["celery", "-A", "backend.celery_app:celery_app", "worker", "--loglevel=info"]

FROM backend-base AS beat
CMD ["celery", "-A", "backend.celery_app:celery_app", "beat", "--loglevel=info"]
