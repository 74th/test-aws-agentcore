"""Register a hidden-input API key in AgentCore Identity, outside Terraform state."""

import argparse
import getpass
import json
import os

import boto3


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-west-2"))
    parser.add_argument("--name", default="anthropic-claude")
    args = parser.parse_args()
    api_key = getpass.getpass(f"API key for {args.name} (input hidden): ").strip()
    if not api_key:
        raise SystemExit("A non-empty API key is required")
    client = boto3.client("bedrock-agentcore-control", region_name=args.region)
    response = client.create_api_key_credential_provider(name=args.name, apiKey=api_key)
    arn = response.get("credentialProviderArn")
    secret_arn = response.get("apiKeySecretArn", {}).get("secretArn")
    if not arn:
        raise SystemExit("Provider was created but the response did not contain its ARN")
    print(json.dumps({"name": args.name, "credentialProviderArn": arn,
                      "secretArn": secret_arn}, indent=2))


if __name__ == "__main__":
    main()
