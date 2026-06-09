FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ .
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini .
COPY alembic/ ./alembic/
COPY backend/ ./backend/
COPY data/ ./data/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN mkdir -p data
ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
