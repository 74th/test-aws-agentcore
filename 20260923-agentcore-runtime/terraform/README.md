# AgentCore infrastructure

This configuration builds a two-AZ VPC with private Runtime subnets, same-AZ Network Firewall endpoints, and per-AZ NAT gateways. Runtime default routes pass through the firewall. A strict domain allowlist permits HTTPS TLS SNI for `.github.com` and `api.anthropic.com`; stateful default actions drop other established flows, and stateless rules drop UDP/443. VPC endpoints carry AgentCore Identity/data/control planes, ECR, CloudWatch Logs, and session-storage S3 traffic. No Bedrock model endpoint or model entitlement is required.

## Preflight and plan

Run `AWS_REGION=us-west-2 bash preflight.sh`, then copy `terraform.tfvars.example` to `terraform.tfvars` and set the pushed image plus provider and secret ARNs returned by the Identity helper. Register the Anthropic API key provider as `anthropic-claude`. `terraform init`, `terraform validate`, and `terraform plan` are read-only with respect to AWS resources. The preflight distinguishes AWS identity/network, AgentCore control-plane, Identity provider, and Terraform schema failures. Session storage is Preview; a plan cannot prove service-side account eligibility.

## Register GitHub token outside Terraform state

Use the separate `../cli/register_identity_api_key.py` helper twice: `uv run python register_identity_api_key.py --name anthropic-claude` for the Anthropic key and repeat with `--name github-readonly` for the GitHub token. It reads each key from a hidden prompt and calls AgentCore Identity directly. The keys never enter Terraform configuration or state. Copy the returned provider ARN and Secrets Manager ARN into their matching Terraform variables. These ARNs grant the Runtime and Gateway role access to retrieve their specific credentials.

After the image and credential provider are ready, run `terraform plan` and review its VPC, NAT, Firewall, and endpoint resources. Applying provisions billable infrastructure. The resulting outputs provide the runtime ARN, gateway URL, and memory ID for the CLI. Runtime instances use the managed microVM compute type (no capacity provider is configured).

`enable_session_storage` defaults to `true` and mounts managed session storage at `/mnt/workspace`. For the separate Memory-only continuity experiment, set it to `false`: Terraform omits the mount, uses ephemeral `/tmp` paths, and enables Memory event retrieval as the conversation context. Restore it to `true` after the experiment if you want the normal workspace-persistence configuration.

After verification, run `terraform destroy` and delete the AgentCore Identity credential provider separately. Preserve `terraform destroy` output and the firewall log group contents needed for the result record.
