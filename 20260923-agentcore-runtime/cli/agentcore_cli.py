import argparse
import base64
import json
import os
import sys
import uuid

import boto3


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoke the Claude Agent SDK feasibility runtime")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-west-2"))
    parser.add_argument("--runtime-arn", default=os.getenv("AGENTCORE_RUNTIME_ARN"))
    parser.add_argument("--session-id", default=os.getenv("AGENTCORE_SESSION_ID"))
    parser.add_argument("--runtime-user-id", default=os.getenv("AGENTCORE_RUNTIME_USER_ID", "feasibility-user"))
    sub = parser.add_subparsers(dest="command", required=True)
    invoke = sub.add_parser("chat", help="send a prompt")
    invoke.add_argument("prompt")
    for name in ("write-file", "read-file", "identity", "memory-events", "gateway-tools"):
        diagnostic = sub.add_parser(name)
        if name in ("write-file", "read-file"):
            diagnostic.add_argument("name", default="feasibility.txt", nargs="?")
        if name == "write-file":
            diagnostic.add_argument("content")
        if name == "gateway-tools":
            diagnostic.add_argument("--tool-name")
            diagnostic.add_argument("--arguments", default="{}")
    sub.add_parser("stop", help="stop this Runtime session")
    return parser


def main() -> None:
    args = make_parser().parse_args()
    if not args.runtime_arn:
        raise SystemExit("Set AGENTCORE_RUNTIME_ARN or pass --runtime-arn")
    session_id = args.session_id or str(uuid.uuid4())
    print(f"session_id={session_id}", file=sys.stderr)
    client = boto3.client("bedrock-agentcore", region_name=args.region)
    if args.command == "stop":
        client.stop_runtime_session(agentRuntimeArn=args.runtime_arn, runtimeSessionId=session_id)
        print(json.dumps({"stopped": True, "session_id": session_id}))
        return
    if args.command == "chat":
        payload = {"prompt": args.prompt}
    else:
        diagnostic = {"write-file": "write_file", "read-file": "read_file",
                      "identity": "identity", "memory-events": "memory_events",
                      "gateway-tools": "gateway_tools"}[args.command]
        payload = {"diagnostic": diagnostic, "session_id": session_id}
        if args.command in ("write-file", "read-file"):
            payload["name"] = args.name
        if args.command == "write-file":
            payload["content"] = args.content
        if args.command == "gateway-tools":
            payload["tool_name"] = args.tool_name
            payload["arguments"] = json.loads(args.arguments)
    response = client.invoke_agent_runtime(
        agentRuntimeArn=args.runtime_arn,
        runtimeSessionId=session_id,
        runtimeUserId=args.runtime_user_id,
        payload=json.dumps(payload).encode(),
        qualifier=os.getenv("AGENTCORE_RUNTIME_QUALIFIER", "DEFAULT"),
    )
    body = response.get("response") or response.get("body")
    if hasattr(body, "read"):
        body = body.read()
    if isinstance(body, bytes):
        body = body.decode()
    print(body if isinstance(body, str) else json.dumps(body, default=str))


if __name__ == "__main__":
    main()
