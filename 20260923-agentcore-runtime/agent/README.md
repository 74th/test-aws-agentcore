# Claude Agent SDK Runtime

## Local setup

Install the Python 3.11+ dependencies from this directory with `uv sync --extra dev`. Copy `.env.example` to `.env` and adjust the settings. `uv run uvicorn app.main:app --host 0.0.0.0 --port 8080` starts the HTTP runtime. In AgentCore Runtime, Claude requests obtain the Anthropic API key from AgentCore Identity; `GET /ping` and workspace diagnostics work without inference credentials.

The fixed default model is Anthropic API model `claude-haiku-4-5-20251001`. The key is retrieved from the Identity provider named by `ANTHROPIC_API_KEY_PROVIDER`, never from a Terraform variable or Runtime environment value. The project settings enable project skill discovery and the bundled `feasibility-check` skill. Invoke it explicitly by asking Claude to use `feasibility-check`.

## Container image

The Dockerfile installs the Claude Code executable, Python SDK, and project settings/skill. Build and push from a Docker environment outside the restricted Docker Sandbox:

```sh
docker buildx build --platform linux/arm64 --provenance=false -t "$ECR_URI:$IMAGE_TAG" --push agent/
docker buildx imagetools inspect "$ECR_URI:$IMAGE_TAG"
```

Confirm the manifest reports `linux/arm64` before setting `agent_image_uri` for Terraform. The Runtime HTTP process binds `0.0.0.0:8080`.
