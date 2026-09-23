data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(var.tags, { Name = "${var.name_prefix}-vpc" })
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = merge(var.tags, { Name = "${var.name_prefix}-igw" })
}

resource "aws_subnet" "public_nat" {
  for_each                = toset(local.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, index(local.azs, each.key))
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name_prefix}-nat-${each.key}" })
}

resource "aws_subnet" "firewall" {
  for_each          = toset(local.azs)
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 4 + index(local.azs, each.key))
  tags              = merge(var.tags, { Name = "${var.name_prefix}-firewall-${each.key}" })
}

resource "aws_subnet" "runtime" {
  for_each          = toset(local.azs)
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, 8 + index(local.azs, each.key))
  tags              = merge(var.tags, { Name = "${var.name_prefix}-runtime-${each.key}" })
}

resource "aws_eip" "nat" {
  for_each = toset(local.azs)
  domain   = "vpc"
  tags     = merge(var.tags, { Name = "${var.name_prefix}-nat-${each.key}" })
}

resource "aws_nat_gateway" "main" {
  for_each      = toset(local.azs)
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public_nat[each.key].id
  depends_on    = [aws_internet_gateway.main]
  tags          = merge(var.tags, { Name = "${var.name_prefix}-nat-${each.key}" })
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  # Per-AZ NAT return routes are managed by aws_route.nat_return_to_firewall.
  # Keep the inline default route without removing those independent routes.
  lifecycle { ignore_changes = [route] }
  tags = merge(var.tags, { Name = "${var.name_prefix}-public" })
}

resource "aws_route_table_association" "public" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.public_nat[each.key].id
  route_table_id = aws_route_table.public.id
}

# NAT gateway return packets are steered back through the same-AZ firewall endpoint.
resource "aws_route" "nat_return_to_firewall" {
  for_each               = toset(local.azs)
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = cidrsubnet(var.vpc_cidr, 4, 8 + index(local.azs, each.key))
  vpc_endpoint_id        = one([for sync in aws_networkfirewall_firewall.egress.firewall_status[0].sync_states : sync.attachment[0].endpoint_id if sync.availability_zone == each.key])
  depends_on             = [aws_networkfirewall_firewall.egress]
}

resource "aws_route_table" "firewall" {
  for_each = toset(local.azs)
  vpc_id   = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[each.key].id
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-firewall-${each.key}" })
}

resource "aws_route_table_association" "firewall" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.firewall[each.key].id
  route_table_id = aws_route_table.firewall[each.key].id
}

resource "aws_cloudwatch_log_group" "firewall" {
  name              = "/aws/network-firewall/${var.name_prefix}"
  retention_in_days = 14
  tags              = var.tags
}

resource "aws_networkfirewall_rule_group" "github_allowlist" {
  capacity = 100
  name     = "${var.name_prefix}-github-https"
  type     = "STATEFUL"
  rule_group {
    stateful_rule_options { rule_order = "STRICT_ORDER" }
    rules_source {
      rules_source_list {
        generated_rules_type = "ALLOWLIST"
        target_types         = ["TLS_SNI"]
        targets              = [".github.com", "api.anthropic.com"]
      }
    }
  }
  tags = var.tags
}

resource "aws_networkfirewall_rule_group" "block_quic" {
  capacity = 10
  name     = "${var.name_prefix}-block-udp443"
  type     = "STATELESS"
  rule_group {
    rules_source {
      stateless_rules_and_custom_actions {
        stateless_rule {
          priority = 1
          rule_definition {
            # Forward UDP/443 to the stateful engine so the explicit drop rule
            # can produce an ALERT log instead of silently dropping here.
            actions = ["aws:forward_to_sfe"]
            match_attributes {
              protocols = [17]
              source {
                address_definition = "0.0.0.0/0"
              }
              destination {
                address_definition = "0.0.0.0/0"
              }
              destination_port {
                from_port = 443
                to_port   = 443
              }
            }
          }
        }
      }
    }
  }
  tags = var.tags
}

resource "aws_networkfirewall_rule_group" "drop_udp443" {
  capacity = 10
  name     = "${var.name_prefix}-drop-udp443"
  type     = "STATEFUL"
  rule_group {
    stateful_rule_options { rule_order = "STRICT_ORDER" }
    rules_source {
      rules_string = <<-EOT
        drop udp any any -> any 443 (msg:"Block UDP/443"; sid:1000001; rev:1; alert;)
      EOT
    }
  }
  tags = var.tags
}

resource "aws_networkfirewall_firewall_policy" "egress" {
  name = "${var.name_prefix}-egress-policy"
  firewall_policy {
    stateless_default_actions          = ["aws:forward_to_sfe"]
    stateless_fragment_default_actions = ["aws:forward_to_sfe"]
    stateful_engine_options { rule_order = "STRICT_ORDER" }
    stateless_rule_group_reference {
      priority     = 1
      resource_arn = aws_networkfirewall_rule_group.block_quic.arn
    }
    stateful_rule_group_reference {
      priority     = 5
      resource_arn = aws_networkfirewall_rule_group.drop_udp443.arn
    }
    stateful_rule_group_reference {
      priority     = 10
      resource_arn = aws_networkfirewall_rule_group.github_allowlist.arn
    }
    stateful_default_actions = ["aws:drop_established", "aws:alert_established"]
  }
  tags = var.tags
}

resource "aws_networkfirewall_firewall" "egress" {
  name                = "${var.name_prefix}-egress"
  firewall_policy_arn = aws_networkfirewall_firewall_policy.egress.arn
  vpc_id              = aws_vpc.main.id
  dynamic "subnet_mapping" {
    for_each = aws_subnet.firewall
    content { subnet_id = subnet_mapping.value.id }
  }
  tags = var.tags
}

resource "aws_networkfirewall_logging_configuration" "egress" {
  firewall_arn = aws_networkfirewall_firewall.egress.arn
  logging_configuration {
    log_destination_config {
      log_type             = "FLOW"
      log_destination_type = "CloudWatchLogs"
      log_destination      = { logGroup = aws_cloudwatch_log_group.firewall.name }
    }
    log_destination_config {
      log_type             = "ALERT"
      log_destination_type = "CloudWatchLogs"
      log_destination      = { logGroup = aws_cloudwatch_log_group.firewall.name }
    }
  }
}

resource "aws_route_table" "runtime" {
  for_each = toset(local.azs)
  vpc_id   = aws_vpc.main.id
  route {
    cidr_block      = "0.0.0.0/0"
    vpc_endpoint_id = one([for sync in aws_networkfirewall_firewall.egress.firewall_status[0].sync_states : sync.attachment[0].endpoint_id if sync.availability_zone == each.key])
  }
  tags = merge(var.tags, { Name = "${var.name_prefix}-runtime-${each.key}" })
}

resource "aws_route_table_association" "runtime" {
  for_each       = toset(local.azs)
  subnet_id      = aws_subnet.runtime[each.key].id
  route_table_id = aws_route_table.runtime[each.key].id
}

resource "aws_security_group" "runtime" {
  name        = "${var.name_prefix}-runtime"
  description = "AgentCore runtime egress is inspected by Network Firewall"
  vpc_id      = aws_vpc.main.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_security_group" "endpoints" {
  name        = "${var.name_prefix}-endpoints"
  description = "HTTPS from the AgentCore runtime to private service endpoints"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.runtime.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset([
    "bedrock-agentcore", "bedrock-agentcore-control",
    "ecr.api", "ecr.dkr", "logs"
  ])
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for az in local.azs : aws_subnet.runtime[az].id]
  security_group_ids  = [aws_security_group.endpoints.id]
  tags                = merge(var.tags, { Name = "${var.name_prefix}-${replace(each.key, ".", "-")}" })
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for az in local.azs : aws_route_table.runtime[az].id]
  tags              = merge(var.tags, { Name = "${var.name_prefix}-s3" })
}

resource "aws_ecr_repository" "agent" {
  name                 = var.name_prefix
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration { scan_on_push = true }
  tags = var.tags
}

data "aws_iam_policy_document" "runtime_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "runtime" {
  name               = "${var.name_prefix}-runtime"
  assume_role_policy = data.aws_iam_policy_document.runtime_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "runtime" {
  statement {
    actions = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    ]
  }
  statement {
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }
  statement {
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
    ]
  }
  statement {
    actions = ["logs:PutResourcePolicy"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    ]
  }
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
  statement {
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
    resources = [aws_ecr_repository.agent.arn]
  }
  statement {
    actions   = ["bedrock-agentcore:CreateEvent", "bedrock-agentcore:ListEvents"]
    resources = [aws_bedrockagentcore_memory.main.arn]
  }
  statement {
    actions = ["bedrock-agentcore:GetResourceApiKey"]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${replace("${var.name_prefix}-runtime", "-", "_")}-*",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:token-vault/default",
      var.anthropic_api_key_provider_arn
    ]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.anthropic_api_key_secret_arn]
  }
  statement {
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [aws_bedrockagentcore_gateway.github.gateway_arn]
  }
}

resource "aws_iam_role_policy" "runtime" {
  name   = "${var.name_prefix}-runtime"
  role   = aws_iam_role.runtime.id
  policy = data.aws_iam_policy_document.runtime.json
}

data "aws_iam_policy_document" "gateway_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "${var.name_prefix}-gateway"
  assume_role_policy = data.aws_iam_policy_document.gateway_trust.json
  tags               = var.tags
}

data "aws_iam_policy_document" "gateway" {
  statement {
    actions = ["bedrock-agentcore:GetWorkloadAccessToken"]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${var.name_prefix}-github-*"
    ]
  }
  statement {
    actions   = ["bedrock-agentcore:GetResourceApiKey"]
    resources = [var.github_credential_provider_arn]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.github_api_key_secret_arn]
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "${var.name_prefix}-gateway-identity"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway.json
}

resource "aws_bedrockagentcore_memory" "main" {
  name                  = replace("${var.name_prefix}-memory", "-", "_")
  description           = "Short-term session conversation events for feasibility checks"
  event_expiry_duration = 30
  tags                  = var.tags
}

resource "aws_bedrockagentcore_gateway" "github" {
  name            = "${var.name_prefix}-github"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"
  tags            = var.tags
}

resource "aws_bedrockagentcore_gateway_target" "github" {
  name               = "github-readonly"
  gateway_identifier = aws_bedrockagentcore_gateway.github.gateway_id
  credential_provider_configuration {
    api_key {
      provider_arn              = var.github_credential_provider_arn
      credential_location       = "HEADER"
      credential_parameter_name = "Authorization"
      credential_prefix         = "Bearer "
    }
  }
  target_configuration {
    mcp {
      mcp_server {
        endpoint = "https://api.githubcopilot.com/mcp/readonly"
      }
    }
  }
}

resource "aws_bedrockagentcore_agent_runtime" "main" {
  agent_runtime_name = replace("${var.name_prefix}-runtime", "-", "_")
  description        = "Claude Agent SDK feasibility runtime"
  role_arn           = aws_iam_role.runtime.arn

  agent_runtime_artifact {
    container_configuration { container_uri = var.agent_image_uri }
  }
  environment_variables = {
    AWS_REGION                  = var.aws_region
    ANTHROPIC_MODEL             = "claude-haiku-4-5-20251001"
    ANTHROPIC_API_KEY_PROVIDER  = var.anthropic_api_key_provider_name
    DISABLE_TELEMETRY           = "1"
    DISABLE_ERROR_REPORTING     = "1"
    AGENTCORE_GATEWAY_URL       = aws_bedrockagentcore_gateway.github.gateway_url
    AGENTCORE_MEMORY_ID         = aws_bedrockagentcore_memory.main.id
    AGENTCORE_ACTOR_ID          = "feasibility-user"
    AGENTCORE_MEMORY_CONTINUITY = var.enable_session_storage ? "false" : "true"
    WORKSPACE_DIR               = var.enable_session_storage ? "/mnt/workspace" : "/tmp/workspace"
    CLAUDE_CONFIG_DIR           = var.enable_session_storage ? "/mnt/workspace/.claude-config" : "/tmp/claude-config"
  }
  network_configuration {
    network_mode = "VPC"
    network_mode_config {
      subnets         = [for az in local.azs : aws_subnet.runtime[az].id]
      security_groups = [aws_security_group.runtime.id]
    }
  }
  dynamic "filesystem_configuration" {
    for_each = var.enable_session_storage ? [true] : []
    content {
      session_storage { mount_path = "/mnt/workspace" }
    }
  }
  lifecycle_configuration {
    idle_runtime_session_timeout = 60
    max_lifetime                 = 28800
  }
  tags       = var.tags
  depends_on = [aws_bedrockagentcore_gateway.github, aws_networkfirewall_logging_configuration.egress]
  lifecycle {
    precondition {
      condition     = var.agent_image_uri != ""
      error_message = "Set agent_image_uri to a pushed linux/arm64 image before applying."
    }
    precondition {
      condition     = var.github_credential_provider_arn != "" && var.github_api_key_secret_arn != ""
      error_message = "Register the GitHub API key in AgentCore Identity and set its provider and secret ARNs."
    }
    precondition {
      condition     = var.anthropic_api_key_provider_arn != "" && var.anthropic_api_key_secret_arn != ""
      error_message = "Register the Anthropic API key in AgentCore Identity and set its provider and secret ARNs."
    }
  }
}
