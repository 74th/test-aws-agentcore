# AgentCore Claude feasibility verification record

Record actual observations here after running the commands in this document. Do not infer success from model text alone.

## Preconditions

1. Run `AWS_REGION=us-west-2 bash terraform/preflight.sh`; resolve missing AWS identity, AgentCore Identity provider, permissions, or service availability before continuing. No Bedrock model entitlement is needed. Session storage is Preview and the provider schema check is not proof of account eligibility.
2. Create an Anthropic API key and a GitHub token restricted to public repository read access. From `cli/`, run `uv sync`, then `uv run python register_identity_api_key.py --region us-west-2 --name anthropic-claude` and repeat with `--name github-readonly`. Copy the provider and Secrets Manager ARNs from each response into Terraform variables; never place either key in Terraform.
3. The IAM principal used by the CLI must have `bedrock-agentcore:InvokeAgentRuntime` and `bedrock-agentcore:InvokeAgentRuntimeForUser` scoped to this Runtime because the Identity credential flow uses `runtimeUserId=feasibility-user`.
4. From `agent/`, run `uv sync --extra dev`, then build and push from a Docker environment outside Docker Sandbox:

   ```sh
   docker buildx build --platform linux/arm64 --provenance=false -t "$ECR_URI:$IMAGE_TAG" --push .
   docker buildx imagetools inspect "$ECR_URI:$IMAGE_TAG"
   ```

   Record the manifest platform as `linux/arm64`; set the full image URI in Terraform variables.

## Infrastructure and runtime

The verification was run in a personal AWS account in region `us-west-2` (account identifier and profile name intentionally omitted). ECR repository `claude-feasibility` contains the ARM64 image used by the current Runtime: tag `memory-continuity-verify`, digest `sha256:64a57fb0804993ae6e99ffc68e25b8c681f2e299af002862d6d5ea056e75c83a` (`linux/arm64`). Runtime version 6 is `READY`, with managed session storage restored and idle timeout set to 60 seconds.

Terraform created the VPC, two-AZ private Runtime subnets, Network Firewall, NAT gateways, interface/gateway endpoints, AgentCore Memory, Gateway, and Runtime. The Runtime's two subnet route-table associations and same-AZ routes through Network Firewall are applied. UDP/443 is forwarded to the stateful engine and explicitly dropped there with an ALERT rule so blocked datagrams appear in logs. The Runtime reached `READY` (version 3) with the ARM64 image. Runtime logging is enabled. These resources incur ongoing charges, especially NAT gateways and Network Firewall endpoints; destroy them when verification is finished.

Run `terraform init`, `terraform fmt -check -recursive`, `terraform validate`, and `terraform plan` from `terraform/`. Review both same-AZ directions through Network Firewall, endpoint routes, firewall allowlist/default drop, and session-storage mount before applying. Do not apply a plan that proposes unrelated route changes. The failed GitHub Gateway target replacement remains pending; the Runtime lifecycle timeout update was applied separately with a target-only plan.

Set the CLI environment:

```sh
export AWS_REGION=us-west-2
export AGENTCORE_RUNTIME_USER_ID=feasibility-user
export AGENTCORE_RUNTIME_ARN="$(terraform -chdir=terraform output -raw agent_runtime_arn)"
```

Start two independent CLI processes with the same session ID. First send a unique fact, then ask for it from a second process. Run `identity`, `write-file`, `read-file`, and `memory-events` with the same and a different session ID. Stop the session with `stop`, wait for stop completion, then call the same ID again and repeat identity/file/memory diagnostics.

To test automatic idle termination with managed session storage, set `idle_runtime_session_timeout = 60`, send a unique fact, and record `identity`. Leave the session unused for at least 70 seconds, call `identity` again with the same Runtime session ID, and verify `instance_id` changed. Ask for the fact in a normal chat turn with that same ID; the default mode should resume the Claude Agent SDK session from `/mnt/workspace`.

To isolate Memory continuity, build/push the updated ARM64 image and apply the Runtime with `enable_session_storage=false`. This removes the persistent mount, switches `WORKSPACE_DIR` and `CLAUDE_CONFIG_DIR` to ephemeral `/tmp` paths, and enables Memory event retrieval as chat context. Send a unique fact and verify the response reports `sdk_session_id: null`; after at least 70 seconds idle, verify a new `instance_id`, ask for the fact again, and check the response reports a positive `memory_context_event_count`. Then run `memory-events` for the same actor/session and another session ID to check persistence and isolation. Restore `enable_session_storage=true` after the experiment. This validates short-term raw-event recovery, not long-term semantic memory extraction.

For Gateway tool enumeration, run `cli/`'s `gateway-tools` command. Select one listed read-only tool and call it with its required read-only parameters. Keep the tool name, redacted result summary, and call success/failure. The model prompt that asks the agent to use GitHub is an additional check, not a substitute for a direct tool call.

For egress, use Runtime-side diagnostics or a test-only command that opens HTTPS to `https://github.com/74th`, `https://www.tohoho-web.com/`, a direct IP, and UDP/443. Record HTTP outcome and the matching Network Firewall FLOW/ALERT log event. The provided app exposes only workspace/session and Gateway diagnostics; the HTTP egress probe must be run from the container during the deployed verification session.

## Results (complete after real AWS runs)

| Requirement | Observation | Evidence / timestamp |
| --- | --- | --- |
| ARM64 image built, pushed, and smoke-tested | Confirmed | `memory-continuity-verify` resolves to `linux/arm64`, digest `sha256:64a57fb0804993ae6e99ffc68e25b8c681f2e299af002862d6d5ea056e75c83a`; Memory-only Runtime invocation succeeded, 2026-09-23 |
| Runtime READY, Anthropic API Haiku 4.5 | Confirmed | Runtime version 6 reached `READY`; the updated image returned Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) during version 5 Memory-only testing, 2026-09-23 |
| Project skill discovered and invoked | Confirmed | SDK initialization listed the verification skill and explicit invocation returned `FEASIBILITY_SKILL_OK`, 2026-09-23 |
| Gateway `tools/list` and read-only call | Not confirmed | Gateway target `github-readonly` remains `FAILED`; Gateway reports HTTP 400 during the GitHub MCP initialize handshake after retrying with raw token + `credential_prefix = "Bearer "`, then with an equivalent Bearer value stored in a temporary test provider. AgentCore requires `credential_prefix` to be at least one character, so an empty prefix is invalid. The temporary provider was deleted afterward and Terraform was restored to the canonical raw-token-plus-Bearer-prefix configuration. No Gateway tool listing/read call is claimed. Using the same Identity-stored token directly against GitHub's MCP endpoint returned initialize 200, initialized 202, and `tools/list` 200 with 28 read-only tools. The GitHub endpoint is reachable and the raw PAT works outside Gateway; the remaining failure is specific to Gateway-to-target handshake behavior/configuration. A direct `get_file_contents` call returned GitHub 409 because `74th/test-aws-agentcore` is currently an empty repository. |
| Memory user/assistant events | Confirmed | Memory diagnostic showed user and assistant events under actor `feasibility-user` and the Runtime session ID after two turns, 2026-09-23 |
| Same-session SDK, file, and stop/resume continuity | Confirmed | Two independent CLI invocations resumed SDK conversation; session workspace file was read after stop/restart; `instance_id` remained stable within a running environment and changed after restart, 2026-09-23 |
| Idle timeout followed by conversation resume | Confirmed | Set `idleRuntimeSessionTimeout` to 60 seconds (minimum); after about 70 seconds idle, the same Runtime session ID produced a different `instance_id`. A second chat invocation correctly returned a unique fact from before idle termination; the same SDK session ID resumed. Memory event listing returned the two chat-turn events. The app does not inject Memory results into the prompt, so this confirms SDK conversation state resumed from managed session storage, not semantic recall from AgentCore Memory, 2026-09-23 |
| Memory-only conversation recovery | Confirmed | Runtime version 5 was `READY` with `filesystemConfigurations` absent, `/tmp` paths, and Memory continuity enabled. First chat had `sdk_session_id: null` and 0 prior events. After about 70 seconds idle, `instance_id` changed; the same session retrieved 1 Memory event and correctly answered the unique fact with `sdk_session_id: null`. `memory-events` then returned 2 USER/ASSISTANT turn events; a different session ID returned 0. Managed session storage was restored in version 6 after the test. 2026-09-23 |
| Different-session isolation | Confirmed | Different session ID produced another Runtime `instance_id`; it could not read the first session's workspace file, 2026-09-23 |
| GitHub and Anthropic API HTTPS allowed; other host blocked | Confirmed | Runtime HTTPS GET to `https://github.com/74th` returned 200; Anthropic inference succeeded; `https://www.tohoho-web.com/` timed out, and Firewall ALERT logged TLS SNI `www.tohoho-web.com` with verdict `drop` at 2026-09-23T07:50:59Z. |
| Direct IP and UDP/443 blocked | Confirmed | Direct HTTPS to GitHub IP `140.82.116.3:443` timed out and Firewall ALERT recorded `drop` at 2026-09-23T07:51:38Z. After changing UDP/443 to a logged stateful drop, the Runtime probe to `1.1.1.1:443` timed out and the Firewall ALERT logged `Block UDP/443`, protocol UDP, verdict `drop` at 2026-09-23T08:05:16Z. |

## Cleanup

Stop Runtime sessions, remove the Anthropic and GitHub Identity API-key credential providers in the same account/region, then run `terraform destroy` from the initialized `terraform/` directory. The credential providers are created outside Terraform and must be deleted separately. For the registered names in this verification:

```sh
aws bedrock-agentcore-control delete-api-key-credential-provider --name anthropic-claude --region us-west-2
aws bedrock-agentcore-control delete-api-key-credential-provider --name github-readonly --region us-west-2
terraform -chdir=terraform destroy
```

Confirm no Runtime, Gateway, Memory, NAT, Firewall, endpoint, or ECR repository resources remain; retain or delete the firewall log group according to the evidence retention decision. Cleanup has not yet been run; resources remain billable.
