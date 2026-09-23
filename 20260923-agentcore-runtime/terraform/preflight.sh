#!/usr/bin/env bash
set -euo pipefail

region="${AWS_REGION:-us-west-2}"
provider_name="${ANTHROPIC_API_KEY_PROVIDER:-anthropic-claude}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "Checking AWS identity in ${region}..."
if ! aws sts get-caller-identity --region "$region" --output json >/dev/null; then
  echo "FAIL: STS identity check failed. Check AWS credentials/session expiry and network or DNS access to STS." >&2
  exit 1
fi

echo "Checking AgentCore control-plane endpoint and permissions..."
if ! aws bedrock-agentcore-control list-memories --region "$region" --output json >/dev/null; then
  echo "FAIL: AgentCore Memory control plane is unavailable or this identity lacks list-memories access in ${region}." >&2
  exit 1
fi

echo "Checking AgentCore Identity API-key provider (${provider_name})..."
if ! aws bedrock-agentcore-control get-api-key-credential-provider --region "$region" --name "$provider_name" --output json >/dev/null; then
  echo "FAIL: Identity provider '${provider_name}' is missing or this identity cannot describe it in ${region}. Register it with cli/register_identity_api_key.py." >&2
  exit 1
fi

echo "Checking Terraform version and pinned AWS provider..."
terraform version | head -n 1
if ! rg -q 'version\s*=\s*"= 6\.62\.0"' "${script_dir}/versions.tf"; then
  echo "FAIL: terraform/versions.tf does not pin AWS provider 6.62.0, which contains the session_storage schema." >&2
  exit 1
fi

cat <<'EOF'
PASS: AWS credentials, AgentCore control plane, and Identity credential API are reachable.
Anthropic API inference uses the `anthropic-claude` Identity provider; no Bedrock model entitlement is required.
Session storage remains a Preview capability and is account/region gated. The provider pin confirms schema support only;
the definitive availability check is a plan/apply of filesystem_configuration.session_storage in this account.
EOF
