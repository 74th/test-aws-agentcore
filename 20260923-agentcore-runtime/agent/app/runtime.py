import os
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, query
from bedrock_agentcore.identity.auth import requires_api_key

from .config import Settings
from .memory import AgentMemory, build_memory_context
from .sessions import SessionStore


async def _run_agent_query(prompt: str, model: str, claude_config: Path,
                          resume: str | None, mcp_servers: dict[str, Any], *,
                          api_key: str) -> tuple[str, str | None, list[str]]:
    env = dict(os.environ)
    env.pop("CLAUDE_CODE_USE_BEDROCK", None)
    env["ANTHROPIC_API_KEY"] = api_key
    env["ANTHROPIC_MODEL"] = model
    env["CLAUDE_CONFIG_DIR"] = str(claude_config)
    options = ClaudeAgentOptions(
        model=model,
        cwd="/opt/agent",
        setting_sources=["project"],
        allowed_tools=["Skill", "Read", "Write", "Bash"],
        resume=resume,
        env=env,
        mcp_servers=mcp_servers,
    )
    chunks: list[str] = []
    skills: list[str] = []
    session_id = resume
    async for message in query(prompt=prompt, options=options):
        if getattr(message, "subtype", None) == "init":
            data = getattr(message, "data", {}) or {}
            skills = list(data.get("skills", []) or [])
            session_id = getattr(message, "session_id", None) or session_id
        if getattr(message, "session_id", None):
            session_id = message.session_id
        content = getattr(message, "content", None)
        if content:
            for block in content:
                if getattr(block, "text", None):
                    chunks.append(block.text)
    return "\n".join(chunks).strip(), session_id, skills


class RuntimeAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions = SessionStore(settings.workspace)
        self.run_agent_query = requires_api_key(provider_name=settings.api_key_provider)(_run_agent_query)
        self.busy = False
        self.instance_id = str(uuid.uuid4())
        self.started_at = int(time.time())

    async def invoke(self, payload: dict[str, Any], runtime_session_id: str) -> dict[str, Any]:
        command = payload.get("diagnostic")
        if command:
            if command == "gateway_tools":
                from .mcp_bridge import call_gateway_mcp
                if not self.settings.gateway_url:
                    raise RuntimeError("AGENTCORE_GATEWAY_URL is not configured")
                result = await call_gateway_mcp(
                    self.settings.gateway_url, self.settings.region,
                    payload.get("tool_name"), payload.get("arguments", {}))
                return {"diagnostic": command, "result": result}
            return self.diagnostic(command, payload)
        prompt = payload["prompt"]

        self.busy = True
        try:
            memory_events: list[dict] = []
            if self.settings.memory_continuity:
                if not self.settings.memory_id:
                    raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
                memory_events = AgentMemory(
                    self.settings.memory_id, self.settings.region
                ).list_events(self.settings.actor_id, runtime_session_id)
                prompt = build_memory_context(memory_events, prompt)
                sdk_session_id = None
            else:
                sdk_session_id = self.sessions.get(runtime_session_id)
            response, new_session_id, skills = await self.run_agent_query(
                prompt, self.settings.model, self.settings.claude_config,
                sdk_session_id, self._mcp_servers(),
            )
            if new_session_id and not self.settings.memory_continuity:
                self.sessions.put(runtime_session_id, new_session_id)
            if not response:
                raise RuntimeError("Claude Agent SDK returned no text response")
            return {"response": response, "runtime_session_id": runtime_session_id,
                    "sdk_session_id": None if self.settings.memory_continuity else new_session_id,
                    "memory_context_event_count": len(memory_events), "skills": skills}
        finally:
            self.busy = False

    def _mcp_servers(self) -> dict[str, Any]:
        if not self.settings.gateway_url:
            return {}
        return {"github": {"type": "http", "url": "http://127.0.0.1:8080/mcp"}}

    def diagnostic(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.settings.workspace.mkdir(parents=True, exist_ok=True)
        if command == "write_file":
            name = _safe_name(payload.get("name", "feasibility.txt"))
            path = self.settings.workspace / name
            path.write_text(str(payload.get("content", "")))
            result: Any = {"path": str(path), "written": True}
        elif command == "read_file":
            name = _safe_name(payload.get("name", "feasibility.txt"))
            result = (self.settings.workspace / name).read_text()
        elif command == "identity":
            result = {"hostname": socket.gethostname(), "pid": os.getpid(),
                      "instance_id": self.instance_id, "started_at": self.started_at}
        elif command == "memory_events":
            if not self.settings.memory_id:
                raise RuntimeError("AGENTCORE_MEMORY_ID is not configured")
            result = AgentMemory(self.settings.memory_id, self.settings.region).list_events(
                self.settings.actor_id, payload.get("session_id", "")
            )
        else:
            raise ValueError(f"Unknown diagnostic command: {command}")
        return {"diagnostic": command, "result": result}


def _safe_name(name: str) -> str:
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or candidate.name in {".", ".."}:
        raise ValueError("name must be a single filename")
    return candidate.name
