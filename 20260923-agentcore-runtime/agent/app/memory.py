from datetime import datetime, timezone
import json

import boto3


def build_memory_context(events: list[dict], current_prompt: str) -> str:
    """Build an explicit prior-conversation context from short-term Memory events."""
    history: list[dict[str, str]] = []
    for event in sorted(events, key=_event_sort_key):
        for item in event.get("payload", []):
            conversational = item.get("conversational", {})
            role = str(conversational.get("role", "")).upper()
            content = conversational.get("content", {})
            text = content.get("text") if isinstance(content, dict) else None
            if role in {"USER", "ASSISTANT"} and isinstance(text, str) and text:
                history.append({"role": role.lower(), "content": text})

    if not history:
        return current_prompt

    serialized_history = json.dumps(history[-40:], ensure_ascii=False)
    return (
        "The following JSON is prior conversation history retrieved from AgentCore Memory. "
        "Use it as conversational context for the current request.\n"
        f"<prior_conversation>{serialized_history}</prior_conversation>\n"
        f"Current user message:\n{current_prompt}"
    )


def _event_sort_key(event: dict) -> str:
    timestamp = event.get("eventTimestamp")
    if hasattr(timestamp, "isoformat"):
        return timestamp.isoformat()
    return str(timestamp or "")


class AgentMemory:
    def __init__(self, memory_id: str, region: str):
        self.memory_id = memory_id
        self.client = boto3.client("bedrock-agentcore", region_name=region)

    def record_turn(self, actor_id: str, session_id: str, prompt: str, response: str) -> None:
        self.client.create_event(
            memoryId=self.memory_id,
            actorId=actor_id,
            sessionId=session_id,
            eventTimestamp=datetime.now(timezone.utc),
            payload=[
                {"conversational": {"content": {"text": prompt}, "role": "USER"}},
                {"conversational": {"content": {"text": response}, "role": "ASSISTANT"}},
            ],
        )

    def list_events(self, actor_id: str, session_id: str) -> list[dict]:
        response = self.client.list_events(
            memoryId=self.memory_id, actorId=actor_id, sessionId=session_id
        )
        return response.get("events", [])
