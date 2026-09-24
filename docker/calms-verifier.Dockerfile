FROM python:3.12-slim
RUN useradd --uid 65534 --non-unique --no-create-home verifier
USER 65534:65534
WORKDIR /work
CMD ["python", "--version"]
