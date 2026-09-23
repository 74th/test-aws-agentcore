FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    ANTHROPIC_MODEL=claude-haiku-4-5-20251001 \
    CLAUDE_CONFIG_DIR=/mnt/workspace/.claude-config \
    WORKSPACE_DIR=/mnt/workspace \
    AGENT_HOME=/opt/agent \
    DOCKER_CONTAINER=1 \
    PATH=/opt/venv/bin:$PATH

WORKDIR /opt/agent
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates python3 python3-venv \
    && python3 -m venv /opt/venv \
    && npm install --global @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./pyproject.toml
COPY app ./app
RUN pip install --no-cache-dir .
COPY .claude ./.claude
RUN mkdir -p /mnt/workspace && chmod -R a+rX /opt/agent

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
