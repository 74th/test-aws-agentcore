variable "aws_region" {
  description = "AWS region for AgentCore and supporting resources."
  type        = string
  default     = "us-west-2"
}

variable "name_prefix" {
  type        = string
  description = "Short lowercase prefix used for resource names."
  default     = "claude-feasibility"
}

variable "agent_image_uri" {
  type        = string
  description = "Previously pushed linux/arm64 ECR image URI, including tag or digest."
  default     = ""
}

variable "github_credential_provider_arn" {
  type        = string
  description = "AgentCore Identity API key credential provider ARN, created outside Terraform."
  default     = ""
}

variable "github_api_key_secret_arn" {
  type        = string
  description = "Secrets Manager ARN backing the GitHub AgentCore Identity API key provider."
  default     = ""
}

variable "anthropic_api_key_provider_name" {
  type        = string
  description = "AgentCore Identity API key provider name used by the Runtime for Anthropic API access."
  default     = "anthropic-claude"
}

variable "anthropic_api_key_provider_arn" {
  type        = string
  description = "AgentCore Identity API key provider ARN for the Anthropic key."
  default     = ""
}

variable "anthropic_api_key_secret_arn" {
  type        = string
  description = "Secrets Manager ARN backing the Anthropic AgentCore Identity API key provider."
  default     = ""
}

variable "vpc_cidr" {
  type    = string
  default = "10.42.0.0/16"
}

variable "enable_session_storage" {
  type        = bool
  description = "Attach managed session storage; disable only for the AgentCore Memory continuity test."
  default     = true
}

variable "tags" {
  type    = map(string)
  default = { Project = "agentcore-claude-feasibility" }
}
