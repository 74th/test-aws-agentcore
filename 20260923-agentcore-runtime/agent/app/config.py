from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    region: str
    model: str
    api_key_provider: str
    gateway_url: str | None
    memory_id: str | None
    actor_id: str
    memory_continuity: bool
    workspace: Path
    claude_config: Path


def load_settings() -> Settings:
    workspace = Path(os.getenv("WORKSPACE_DIR", "/mnt/workspace"))
    return Settings(
        region=os.getenv("AWS_REGION", "us-west-2"),
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        api_key_provider=os.getenv("ANTHROPIC_API_KEY_PROVIDER", "anthropic-claude"),
        gateway_url=os.getenv("AGENTCORE_GATEWAY_URL") or None,
        memory_id=os.getenv("AGENTCORE_MEMORY_ID") or None,
        actor_id=os.getenv("AGENTCORE_ACTOR_ID", "feasibility-user"),
        memory_continuity=os.getenv("AGENTCORE_MEMORY_CONTINUITY", "false").lower()
        in {"1", "true", "yes"},
        workspace=workspace,
        claude_config=Path(os.getenv("CLAUDE_CONFIG_DIR", str(workspace / ".claude-config"))),
    )
