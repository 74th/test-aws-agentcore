# Tasks

## 1. 前提とコンテナ

- [x] 1.1 `agent/` と `cli/` の依存関係、設定値、起動方法を定義し、ローカルで依存関係のインストールと設定チェックが成功することを確認する。
- [x] 1.2 Claude Agent SDK コンテナの Dockerfile に Claude Code 実行バイナリと検証用 skill を入れ、ファイル構成と依存関係を確認する。Docker Sandbox 外で実行する ARM64 image の手動 build/push コマンドも用意する。
- [x] 1.3 Runtime の `GET /ping` と `POST /invocations` を実装し、コンテナを起動しない HTTP テストで正常系・入力エラー・処理中の health 応答を確認する。
- [x] 1.4 AgentCore Identity の API key provider から Anthropic API key を取得し、Claude Haiku 4.5 の Anthropic API 基本応答で利用モデルを確認する。
- [x] 1.5 SDK の project settings と Skill ツールを設定し、初期化メッセージに検証用 skill が現れ、明示呼び出しでその結果が返ることを確認する。

## 2. Terraform と AWS ネットワーク

- [x] 2.1 対象リージョン、AgentCore Identity、session storage Preview、Terraform AWS provider の対応を確認する preflight と手順を作り、未対応時に理由が分かることを確認する。
- [x] 2.2 `terraform/` に VPC、Runtime 用 private subnet、Firewall・NAT 用 subnet と対称な経路を定義し、`terraform validate` と route table の計画内容で経路を確認する。
- [x] 2.3 Network Firewall に `github.com` と `api.anthropic.com` の HTTPS allowlist、その他の外部宛て拒否、直接 IP・UDP/443 の迂回防止とログを定義し、`terraform validate` と firewall policy の計画内容で確認する。
- [x] 2.4 AgentCore data plane・Identity、ECR API/DKR、CloudWatch Logs の interface endpoint と S3 gateway endpoint を定義し、Anthropic API の許可経路とセッションストレージ用 S3 通信を含む `terraform plan` を確認する。
- [x] 2.5 ECR image、最小権限 IAM、AgentCore Memory、Gateway、GitHub MCP target、Runtime の VPC・session storage 設定を Terraform に定義し、出力と `terraform validate` を確認する。
- [ ] 2.6 GitHub 読み取り専用 token を Terraform state に入れずに AgentCore credential provider へ登録する手順を用意し、Gateway target の設定と同期後に読み取り tool が列挙されることを確認する。

## 3. MCP とセッション継続

- [ ] 3.1 Runtime 内のローカル MCP bridge で Gateway 向け SigV4 署名と HTTP 中継を実装し、`tools/list` と読み取り tool 呼び出しが成功し GitHub token がコンテナへ渡らないことを確認する。
- [x] 3.2 `CLAUDE_CONFIG_DIR` と SDK session ID 対応表を `/mnt/workspace` に保存し、同一 Runtime セッション ID の 2 回目の呼び出しで SDK `resume` が前の会話を参照することを確認する。
- [x] 3.3 会話ターンを AgentCore Memory に保存・取得し、2 回目の呼び出し後に actor/session ID ごとのユーザー・アシスタントの記録を確認する。
- [x] 3.4 ワークスペースの書き込み・読み取りと実行環境識別子の診断を実装し、同じセッションと別セッションでファイル・環境の共有条件が仕様どおりか確認する。
- [x] 3.5 session storage を無効にしてアイドル終了後に新しい実行環境を起動し、AgentCore Memory の短期イベントだけを取得・コンテキスト化して固有事実への回答を再開できることを確認する。SDK の以前の session ID と workspace 永続データを使わず、`instance_id` の変更と Memory 取得結果を記録する。

## 4. CLI と実環境検証

- [x] 4.1 `cli/` に対話、セッション ID 指定、診断、Runtime 停止の操作を実装し、2 つの別プロセスから同じ ID で `InvokeAgentRuntime` を呼べることを確認する。
- [x] 4.2 人が Docker Sandbox 外の対応 Docker 環境で `linux/arm64` image を build/push し、ECR image manifest の architecture を確認する。その image URI で Terraform を適用し、microVM 型 Runtime が READY になり、基本対話と skill 呼び出しが成功することを確認する。
- [ ] 4.3 GitHub MCP の `tools/list` と `74th` の公開リポジトリ読み取りを実行し、Gateway 経由の tool 名と結果を記録する。
- [x] 4.4 同一 ID での会話・ファイル再利用、別 ID の分離、StopRuntimeSession 完了後の再開を試し、Memory 記録・ファイル内容・実行環境識別子を記録する。
- [x] 4.5 Runtime コンテナ内から `https://github.com/74th` の成功、`https://www.tohoho-web.com/` の拒否、直接 IP と UDP/443 の拒否を試し、Firewall ログを合わせて記録する。
- [x] 4.6 実測結果と未達項目を仕様ごとに記録し、再実行・credential 削除・`terraform destroy` の手順を確認する。
