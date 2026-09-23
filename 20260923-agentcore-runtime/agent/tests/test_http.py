from dataclasses import replace
import asyncio

import httpx

from app.main import app, agent


def make_client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_ping_is_healthy_when_idle():
    async with make_client() as client:
        assert (await client.get("/ping")).json() == {"status": "Healthy"}


async def test_invocation_requires_json_prompt_or_diagnostic():
    async with make_client() as client:
        response = await client.post("/invocations", json={"prompt": "hello"})
        assert response.status_code == 400
        assert "session ID" in response.json()["detail"]


async def test_invocation_rejects_missing_prompt():
    async with make_client() as client:
        response = await client.post("/invocations", json={"session_id": "abc"})
        assert response.status_code == 400


async def test_ping_reports_busy_during_invocation(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_invoke(payload, runtime_session_id):
        agent.busy = True
        started.set()
        await release.wait()
        agent.busy = False
        return {"response": "done"}

    monkeypatch.setattr(agent, "invoke", slow_invoke)
    async with make_client() as async_client:
        pending = asyncio.create_task(async_client.post(
            "/invocations",
            headers={"x-amzn-bedrock-agentcore-runtime-session-id": "busy-check"},
            json={"prompt": "wait"},
        ))
        await asyncio.wait_for(started.wait(), timeout=2)
        assert (await async_client.get("/ping")).json() == {"status": "HealthyBusy"}
        release.set()
        finished = await asyncio.wait_for(pending, timeout=2)
        assert finished.status_code == 200
        assert finished.json()["response"] == "done"


async def test_diagnostic_write_and_read(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "settings", replace(agent.settings, workspace=tmp_path))
    async with make_client() as client:
        write = await client.post("/invocations", headers={"x-amzn-bedrock-agentcore-runtime-session-id": "s1"},
                                  json={"diagnostic": "write_file", "name": "x.txt", "content": "hello"})
        assert write.status_code == 200
        read = await client.post("/invocations", headers={"x-amzn-bedrock-agentcore-runtime-session-id": "s1"},
                                 json={"diagnostic": "read_file", "name": "x.txt"})
        assert read.json()["result"] == "hello"


def test_identity_has_stable_instance_id_and_start_time(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "settings", replace(agent.settings, workspace=tmp_path))
    first = agent.diagnostic("identity", {})["result"]
    second = agent.diagnostic("identity", {})["result"]
    other_runtime = type(agent)(agent.settings).diagnostic("identity", {})["result"]

    assert first["instance_id"] == second["instance_id"]
    assert first["started_at"] == second["started_at"]
    assert first["instance_id"] != other_runtime["instance_id"]
