# ---------------------------------------------------------------------------
# Stage 1: build the React/Vite frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY vite.config.js ./
COPY frontend ./frontend
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime; FastAPI serves the API and the built frontend
# ---------------------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY --from=frontend /app/dist ./dist

EXPOSE 10000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
