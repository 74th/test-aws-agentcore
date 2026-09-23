import json
import os
from pathlib import Path
from threading import Lock


class SessionStore:
    """Small persistent mapping from AgentCore session IDs to SDK session IDs."""

    def __init__(self, workspace: Path):
        self.path = workspace / ".agentcore-sessions.json"
        self.lock = Lock()

    def _read(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}

    def get(self, runtime_session_id: str) -> str | None:
        with self.lock:
            return self._read().get(runtime_session_id)

    def put(self, runtime_session_id: str, sdk_session_id: str) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = self._read()
            data[runtime_session_id] = sdk_session_id
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
            os.replace(tmp, self.path)
