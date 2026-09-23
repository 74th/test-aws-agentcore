from urllib.parse import urlparse
import json

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


async def forward_signed_request(url: str, body: bytes, headers: dict[str, str], region: str) -> httpx.Response:
    """Forward one MCP HTTP request using the task role's SigV4 credentials."""
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS credentials are available to sign the Gateway request")
    frozen = credentials.get_frozen_credentials()
    request_headers = {
        "content-type": headers.get("content-type", "application/json"),
        "accept": headers.get("accept", "application/json, text/event-stream"),
    }
    session_id = headers.get("mcp-session-id")
    if session_id:
        request_headers["mcp-session-id"] = session_id
    for name in ("mcp-protocol-version", "last-event-id"):
        if name in headers:
            request_headers[name] = headers[name]
    aws_request = AWSRequest(method="POST", url=url, data=body, headers=request_headers)
    SigV4Auth(frozen, "bedrock-agentcore", region).add_auth(aws_request)
    async with httpx.AsyncClient(timeout=90) as client:
        return await client.post(url, content=body, headers=dict(aws_request.headers.items()))


async def call_gateway_mcp(url: str, region: str, tool_name: str | None = None,
                           arguments: dict | None = None) -> dict:
    async def send(message: dict, session_id: str | None = None) -> httpx.Response:
        headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
                   "mcp-protocol-version": "2025-03-26"}
        if session_id:
            headers["mcp-session-id"] = session_id
        return await forward_signed_request(url, json.dumps(message).encode(), headers, region)

    init = await send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "agentcore-feasibility-bridge", "version": "0.1.0"}}})
    init.raise_for_status()
    session_id = init.headers.get("mcp-session-id")
    if session_id:
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id)
    listed = await send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, session_id)
    listed.raise_for_status()
    listing = listed.json()
    if tool_name is None:
        return {"tools": listing.get("result", {}).get("tools", []),
                "gateway_session_id": session_id}
    called = await send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": tool_name, "arguments": arguments or {}}}, session_id)
    called.raise_for_status()
    return {"tools": listing.get("result", {}).get("tools", []),
            "call": called.json().get("result"), "gateway_session_id": session_id}


def gateway_host(url: str) -> str:
    return urlparse(url).netloc
