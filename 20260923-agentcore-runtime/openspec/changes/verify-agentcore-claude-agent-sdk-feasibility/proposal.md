# Proposal

## Why

既存の Claude Code 分析エージェントを AWS AgentCore Runtime に移せるかを、AWS の公開仕様に沿った最小構成で確かめたい。現時点のリポジトリには実装がなく、Runtime、Gateway、Memory、永続ワークスペース、VPC 送信制御を組み合わせたときの成立条件と実測結果を残す必要がある。

## What Changes

- `agent/` に Claude Agent SDK を起動するコンテナと、コンテナ内の検証用 skill を用意する。Claude Haiku 4.5 は Amazon Bedrock 経由で呼び出す。
- `agent/` の image を `linux/arm64` でビルドし、AgentCore Runtime の microVM compute type で実行する。ARM64 ビルドは Docker Sandbox 外の対応する Docker 環境で行う。
- `terraform/` に AgentCore Runtime、Gateway と GitHub MCP target、Memory、セッションストレージ、VPC と送信制御、必要な IAM・エンドポイントを定義する。
- `cli/` に `InvokeAgentRuntime` でセッション ID を指定して対話・検証できる CLI を用意する。
- 同一セッションの会話とファイルの再利用、異なるセッションの分離、停止後の再開、GitHub MCP の `tools/list`、許可先と拒否先への HTTP 通信を実環境で検証できるようにする。
- 公開仕様から説明できる構成と、AWS アカウント上でしか確認できない動作を区別して記録する。

## Capabilities

### New Capabilities

- `claude-agent-runtime`: AgentCore Runtime 上で動く Claude Agent SDK コンテナ、Bedrock モデル、skill と呼び出し CLI。
- `github-mcp-gateway`: Gateway が GitHub MCP の認証を付与し、エージェントへツールを公開する機能。
- `session-continuity`: AgentCore Memory とセッションストレージを用いた会話履歴・ワークスペースの継続とセッション分離。
- `controlled-egress`: Runtime からの外部 HTTPS 通信を許可ドメインへ制限する VPC 構成と検証。

### Modified Capabilities

なし。既存の capability はない。

## Impact

新規の `agent/`、`terraform/`、`cli/`、AWS アカウントの AgentCore・Bedrock・VPC・Network Firewall・ECR・IAM リソースに影響する。GitHub MCP の認証情報と、Bedrock の Claude Haiku 4.5 利用権限が必要。Runtime のセッションストレージは AWS 文書上 Preview であり、リージョンと Terraform AWS provider の対応を実装時に確認する。ARM64 image のビルドには Docker Sandbox 外の対応環境が必要。
