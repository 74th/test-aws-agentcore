from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from bedrock_agentcore.runtime import BedrockAgentCoreContext

from .config import load_settings
from .mcp_bridge import forward_signed_request
from .memory import AgentMemory
from .runtime import RuntimeAgent

settings = load_settings()
agent = RuntimeAgent(settings)
app = FastAPI(title="AgentCore Claude Agent SDK feasibility runtime")


@app.get("/ping")
async def ping():
    return {"status": "HealthyBusy" if agent.busy else "Healthy"}


@app.post("/invocations")
async def invocations(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="body must be valid JSON") from exc
    if not isinstance(payload, dict) or (
        not isinstance(payload.get("prompt"), str)
        and not isinstance(payload.get("diagnostic"), str)
    ):
        raise HTTPException(status_code=400, detail="provide a string prompt or a diagnostic command")
    session_id = request.headers.get("x-amzn-bedrock-agentcore-runtime-session-id") or payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Runtime session ID is required")
    workload_access_token = (
        request.headers.get("x-amz-bedrock-agentcore-identity-wat")
        or request.headers.get("workloadaccesstoken")
    )
    if workload_access_token:
        BedrockAgentCoreContext.set_workload_access_token(workload_access_token)
    BedrockAgentCoreContext.set_request_context("agentcore-http", session_id)
    try:
        result = await agent.invoke(payload, session_id)
        if not payload.get("diagnostic") and settings.memory_id:
            AgentMemory(settings.memory_id, settings.region).record_turn(
                settings.actor_id, session_id, payload["prompt"], result["response"]
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Avoid returning credentials or internal exception detail to callers.
        raise HTTPException(status_code=500, detail=f"agent invocation failed: {type(exc).__name__}") from exc


@app.post("/mcp")
async def mcp_bridge(request: Request):
    if not settings.gateway_url:
        raise HTTPException(status_code=503, detail="AGENTCORE_GATEWAY_URL is not configured")
    response = await forward_signed_request(
        settings.gateway_url,
        await request.body(),
        dict(request.headers),
        settings.region,
    )
    headers = {k: v for k, v in response.headers.items()
               if k.lower() in {"content-type", "mcp-session-id", "last-event-id"}}
    return Response(content=response.content, status_code=response.status_code, headers=headers)
