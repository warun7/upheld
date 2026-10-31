# One container for the website, the playground and the API.
# Built for a Hugging Face Docker Space (port 7860, free CPU tier), but runs anywhere.

FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /bin/uv
ENV UV_SYSTEM_PYTHON=1 HF_HOME=/models PYTHONUNBUFFERED=1
WORKDIR /app

# CPU-only torch first, so pip never pulls the multi-GB CUDA wheels from PyPI.
RUN uv pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN uv pip install ".[minicheck,lettuce,dense]"

# Bake the ~4 GB of models into the image so a cold start doesn't download them.
RUN python -c "from upheld.evidence import make_embedder; from upheld.verify import make_verifier; make_verifier('ensemble'); make_embedder('auto')" \
    && chmod -R a+rX /models

COPY --from=web /web/dist ./web/dist
ENV UPHELD_SITE_DIR=/app/web/dist HF_HUB_OFFLINE=1 UPHELD_MAX_CONCURRENT=1
EXPOSE 7860
CMD ["uvicorn", "upheld.api:app", "--host", "0.0.0.0", "--port", "7860"]
