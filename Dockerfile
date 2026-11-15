# LatentHealth: website + model API in a single process (FastAPI + uvicorn).
# Built for Hugging Face Spaces (Docker SDK, port 7860) and Render (render.yaml; Render sets $PORT).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PORT=7860

RUN pip install --no-cache-dir uv \
    && useradd -m -u 1000 user

WORKDIR /app
RUN chown user:user /app
COPY --chown=user . /app
USER user

# Same environment as development: locked model dependencies + the web server's requirements.
RUN uv sync --frozen --no-dev \
    && uv pip install --no-cache -r web/server/requirements.txt

EXPOSE 7860
# The chat assistant uses Claude only if ANTHROPIC_API_KEY is set (as a secret); otherwise it runs in guided mode.
CMD ["sh", "-c", ".venv/bin/uvicorn server.main:app --app-dir web --host 0.0.0.0 --port ${PORT}"]
