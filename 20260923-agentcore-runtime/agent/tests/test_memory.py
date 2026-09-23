from dataclasses import replace

import pytest

from app.config import load_settings
from app.memory import build_memory_context
from app.runtime import RuntimeAgent


def test_build_memory_context_preserves_chronological_turns():
    events = [
        {
            "eventTimestamp": "2026-09-23T10:02:00+00:00",
            "payload": [
                {"conversational": {"role": "ASSISTANT", "content": {"text": "Saved."}}}
            ],
        },
        {
            "eventTimestamp": "2026-09-23T10:01:00+00:00",
            "payload": [
                {"conversational": {"role": "USER", "content": {"text": "CODE-123"}}}
            ],
        },
    ]

    prompt = build_memory_context(events, "What code did I give you?")

    assert prompt.index("CODE-123") < prompt.index("Saved.")
    assert prompt.index("Saved.") < prompt.index("What code did I give you?")


@pytest.mark.asyncio
async def test_memory_continuity_reads_events_without_sdk_resume(tmp_path, monkeypatch):
    settings = replace(
        load_settings(),
        memory_id="test-memory",
        actor_id="test-actor",
        memory_continuity=True,
        workspace=tmp_path,
        claude_config=tmp_path / "claude-config",
    )
    runtime = RuntimeAgent(settings)
    runtime.sessions.put("runtime-session", "old-sdk-session")
    events = [{
        "eventTimestamp": "2026-09-23T10:01:00+00:00",
        "payload": [{
            "conversational": {
                "role": "USER",
                "content": {"text": "The test phrase is MAPLE-42."},
            }
        }],
    }]

    class FakeMemory:
        def __init__(self, memory_id, region):
            assert memory_id == "test-memory"

        def list_events(self, actor_id, session_id):
            assert actor_id == "test-actor"
            assert session_id == "runtime-session"
            return events

    observed = {}

    async def fake_run_agent_query(prompt, model, claude_config, resume, mcp_servers):
        observed.update(prompt=prompt, resume=resume)
        return "MAPLE-42", "new-sdk-session", []

    monkeypatch.setattr("app.runtime.AgentMemory", FakeMemory)
    monkeypatch.setattr(runtime, "run_agent_query", fake_run_agent_query)

    result = await runtime.invoke(
        {"prompt": "What was the test phrase?"}, "runtime-session"
    )

    assert "MAPLE-42" in observed["prompt"]
    assert "What was the test phrase?" in observed["prompt"]
    assert observed["resume"] is None
    assert result["response"] == "MAPLE-42"
    assert result["sdk_session_id"] is None
    assert result["memory_context_event_count"] == 1
    assert runtime.sessions.get("runtime-session") == "old-sdk-session"
