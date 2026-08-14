# Multi-stage build (OPS_PLAN §2.2): node builds the UI template once,
# the runtime image is python-slim with the engine, reference data, sample
# corpus, and the pre-inlined explorer template. Non-root throughout.

FROM node:20-slim AS ui
WORKDIR /build/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim
LABEL org.opencontainers.image.title="candidate-transformer" \
      org.opencontainers.image.description="Multi-source candidate data transformer: deterministic merge with provenance, confidence, and a glass-box explorer" \
      org.opencontainers.image.source="https://github.com/MohanKrishnaGR/NorthStar"

WORKDIR /app
COPY pyproject.toml README.md ./
COPY transformer/ transformer/
RUN pip install --no-cache-dir .[resume]

COPY data/ data/
COPY configs/ configs/
COPY samples/ samples/
COPY goldens/ goldens/
COPY tools/build_ui.py tools/
COPY ui/index.html ui/index.html
COPY --from=ui /build/ui/dist/ ui/dist/
RUN python tools/build_ui.py --inline-only

RUN useradd --create-home runner && chown -R runner:runner /app
USER runner

EXPOSE 8765
# Healthcheck is meaningful when the container runs the default `serve`
# command; one-shot `run` invocations exit before it ever fires.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)" || exit 1

ENTRYPOINT ["python", "-m", "transformer"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
