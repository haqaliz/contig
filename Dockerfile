# The contig CLI as a container image (published to GHCR on release).
#
# This image contains the contig CLI and its Python dependencies. The
# self-contained commands (plan, show, verify, benchmark, eval-detector, clusters,
# coverage, methods, export, cost, keygen) work out of the box. A real pipeline run
# (contig run) additionally needs Nextflow, a Java runtime, and a container runtime
# reachable from this container; mount your runs directory and provide those, or run
# contig on a host that has them. The dashboard has its own image (dashboard/Dockerfile).

FROM python:3.12-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim
LABEL org.opencontainers.image.title="contig" \
      org.opencontainers.image.description="Agentic bioinformatics analyst: the Layer-2 run, self-heal, verify, reproduce engine" \
      org.opencontainers.image.source="https://github.com/haqaliz/contig"
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
# A non-root user; mount your runs directory at /work.
RUN useradd -m contig
USER contig
WORKDIR /work
ENTRYPOINT ["contig"]
CMD ["--help"]
