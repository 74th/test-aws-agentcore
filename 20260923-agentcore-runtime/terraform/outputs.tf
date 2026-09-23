output "agent_runtime_arn" {
  value = aws_bedrockagentcore_agent_runtime.main.agent_runtime_arn
}

output "gateway_url" {
  value = aws_bedrockagentcore_gateway.github.gateway_url
}

output "gateway_id" {
  value = aws_bedrockagentcore_gateway.github.gateway_id
}

output "memory_id" {
  value = aws_bedrockagentcore_memory.main.id
}

output "ecr_repository_url" {
  value = aws_ecr_repository.agent.repository_url
}

output "firewall_log_group" {
  value = aws_cloudwatch_log_group.firewall.name
}
