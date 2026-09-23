# Design

## Context

リポジトリには依頼文、OpenSpec 設定以外のアプリ実装がない。既存の Claude Code 分析エージェントの資産もこのリポジトリにはないため、まず同梱の最小 skill で移植の技術経路を検証する。実際の分析資産の移植は、その内容を受け取ってから扱う。

AWS の [Runtime HTTP 契約](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html) は ARM64、`0.0.0.0:8080`、`GET /ping`、`POST /invocations` を要求する。[Runtime セッション](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html) はセッション ID ごとに microVM を分離し、停止後の再呼び出しでは新しい実行環境を作る。従って「各セッションで別コンテナ」という要求は、同一イメージのエージェントをセッション専用 microVM で実行することとして検証する。リクエストごとにコンテナが生成される仕様とはしない。

## Goals / Non-Goals

**Goals:**

- AWS 公式文書と Anthropic・GitHub の一次資料から成立しそうな構成を選び、実 AWS 環境で成否を再現可能な形で記録する。
- Runtime、Claude Agent SDK、Gateway、Memory、セッションストレージ、VPC 送信制御を一つの検証フローで扱う。
- セッション ID、Claude SDK の会話 ID、Memory の actor/session ID の対応を明示する。

**Non-Goals:**

- 既存の分析エージェントと完全に同じ振る舞いの保証。元の設定・skills・ツール定義は未提供である。
- URL パス単位の送信制御や、Gateway サービス自身の外向き通信への Runtime 用 Firewall ポリシー適用。
- Preview のセッションストレージの本番運用保証。
- Docker Sandbox 内での ARM64 image ビルド。

## Decisions

### 1. Python の Claude Agent SDK を Runtime の HTTP コンテナに入れる

`agent/` は Python の Claude Agent SDK と Claude Code 実行バイナリを ARM64 イメージへ組み込み、HTTP 契約を実装する。`/invocations` は Runtime が渡すセッション ID を受け、プロンプトと診断コマンドを処理する。CLI は boto3 の `InvokeAgentRuntime` を使い、初回 ID を表示、次回に同じ ID を受け取る。`/ping` は実行状態を反映する。これは AWS の [独自コンテナ契約](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html) に一致する。AgentCore 専用フレームワークへ置き換える案は、Claude Agent SDK 自体の成立を確かめる目的に合わない。

開発中のコードと HTTP 契約はコンテナを起動せずに確認する。配備用 image は Docker Sandbox 外の ARM64 対応 Docker 環境で人が `docker buildx build --platform linux/arm64` を実行して ECR に push する。`agent/` にその再現可能なコマンドと image の architecture を確認する手順を置き、Terraform には push 済み image URI を入力する。Docker Sandbox 内でのコンテナ実行、および EC2 Instances 型への変更は計画に含めない。[AWS の compute type 比較](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-instances-how-it-works.html)では microVM は `arm64`、Instances は `x86_64` も使えるが、今回重視する microVM の実行特性を確認するためである。

Claude Code の Bedrock モードを `CLAUDE_CODE_USE_BEDROCK=1`、主モデルを `us.anthropic.claude-haiku-4-5-20251001-v1:0`（リージョンに応じて設定可能）で固定し、SDK の `model` にも同じ ID を渡す。[Anthropic の Bedrock 設定](https://code.claude.com/docs/en/amazon-bedrock)と[AWS の Haiku 4.5 モデルカード](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html)に従う。`bedrock-runtime` のこのモデルは bare model ID ではなく geo/global inference profile を使う。リージョンは既定で `us-west-2` とし、モデル利用権限・推論先リージョンの IAM を事前確認する。モデル alias に任せる案は別モデルへの暗黙の切り替えがあり得るため採らない。

検証用 skill は `/opt/agent/.claude/skills/` に置き、SDK の `cwd=/opt/agent`、`setting_sources=["project"]`、Skill ツールを有効にする。[Anthropic の skill 手順](https://code.claude.com/docs/en/agent-sdk/skills)どおり、初期化メッセージの `skills` と明示呼び出しの出力で二段階確認する。分析用の実資産が渡されたら同じ配置規則で置き換える。

### 2. GitHub MCP は Gateway の MCP target にする

Gateway の inbound は IAM SigV4 とし、GitHub MCP target の outbound には AgentCore Identity の API key credential provider に登録した読み取り専用 GitHub token を使う。target の credential location を `HEADER`、parameter name を `Authorization`、prefix を `Bearer ` とする。[AWS の Gateway target 認証](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-building-adding-targets-authorization.html)はこの構成を表現できる。[GitHub の remote MCP](https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md) は `https://api.githubcopilot.com/mcp/readonly` と bearer token を受ける。Gateway で同期したツールを `tools/list` と読み取り呼び出しで確認する。OAuth 三者認可も AWS はサポートするが、検証の初期設定と consent の手間を避けるため token 方式を選ぶ。

Claude Agent SDK の HTTP MCP 設定は静的 header を受けるが、SigV4 はリクエスト本文ごとの署名が必要なので、Runtime 内にローカルの署名付き MCP bridge を置く。Claude SDK は localhost の HTTP MCP endpoint に接続し、bridge が実行ロールの AWS 認証情報で Gateway 宛ての各要求を署名・中継する。ブリッジは MCP の request/response と必要な stream/header を透過的に扱う。コンテナには GitHub token を渡さない。Gateway を無認証にする案は、公開エンドポイントを作るため採らない。

### 3. 会話とファイルは別の永続化経路で扱う

AgentCore Memory にはユーザー・アシスタントの会話ターンを `actorId` と Runtime `sessionId` で記録・取得する。一方、Claude Agent SDK の `resume` が読むのは SDK の transcript であり、Memory にターンを書くだけでは SDK の内部状態を再開できない。[Anthropic の sessions](https://code.claude.com/docs/en/agent-sdk/sessions)は transcript ファイルまたは SessionStore を要求する。今回の最小構成では `CLAUDE_CONFIG_DIR` を `/mnt/workspace/.claude-config` に置き、SDK session ID を同じマウント内の対応表へ保存する。再呼び出し時にその ID を `resume` へ渡す。`cwd` は固定する。別の SessionStore 実装を用いる案は追加の保存基盤と実装量が必要なので採らない。

`/mnt/workspace` には [AgentCore の managed session storage](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-filesystem-configurations.html)を設定する。これは microVM ごとの分離と stop/resume 後の復元を AWS が文書化しているが Preview で、14 日間の非使用や Runtime version 更新で消える。Memory と作業ファイルを長期保存する要件には使わない。停止 API の完了後に再開し、会話とファイルの両方を確認する。EFS を使う案は永続期間が長い一方、セッション分離用のディレクトリ制御を自前で持つ必要がある。

### 4. VPC の外部通信を Network Firewall へ通す

Runtime は private subnet に置き、外向きの既定経路を同じ AZ の Network Firewall endpoint、次に NAT gateway と Internet Gateway へ通す。戻り経路も対称にする。Firewall の TLS SNI / HTTP Host allowlist と既定拒否を組み合わせ、`github.com` を許可し `www.tohoho-web.com` を拒否する。Security Group だけではドメイン名を判定できない。[Network Firewall のドメイン規則](https://docs.aws.amazon.com/network-firewall/latest/developerguide/stateful-rule-groups-domain-names.html)と[評価順序](https://docs.aws.amazon.com/network-firewall/latest/developerguide/suricata-rule-evaluation-order.html)に従い、TLS ハンドシェイクが通る状態で SNI を判定する。直接 IP、UDP/443、名前を識別できない TLS は拒否する。許可範囲は FQDN 単位で、`/74th` だけを許可する機能ではない。

Bedrock 推論には `bedrock-runtime`、AgentCore Memory には data-plane、Gateway には gateway の interface VPC endpoint と private DNS を設ける。[Bedrock PrivateLink](https://docs.aws.amazon.com/bedrock/latest/userguide/vpc-interface-endpoints.html)と[AgentCore PrivateLink](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-interface-endpoints.html)を使用し、ECR API/DKR、CloudWatch Logs の interface endpoint と S3 gateway endpoint を加える。VPC モードのセッションストレージ同期にも [S3 への経路](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-filesystem-configurations.html)が必要。AWS サービスの通信を単純な公開 FQDN allowlist に混ぜる案は、必要ホストが増えやすく検証しにくいため採らない。

Gateway から GitHub MCP への outbound は Gateway サービス側の経路であり、Runtime の Network Firewall では制御されない。`https://github.com/74th` の取得検証は必ず Runtime コンテナ内から行い、MCP 経由の GitHub 取得とは別に結果を記録する。

### 5. Terraform と検証結果

`terraform/` に必要なリソースと出力（Runtime ARN、Gateway URL、Memory ID）をまとめ、AWS provider は session storage を持つ版へ固定する。[Terraform AWS provider の Runtime resource](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagentcore_agent_runtime)には `filesystem_configuration` と VPC 設定がある。配備は人が Docker Sandbox 外で ARM64 image を build/push した後、その image URI を Terraform へ渡す順序にする。GitHub token を Terraform state に保存しないよう、credential provider を安全な別手順で作成し、その ARN を Terraform 入力として受ける。Terraform が認証情報そのものを管理する案は state への残留を招くため採らない。

検証 CLI/手順は各要求の成否、セッション ID、SDK 会話 ID、実行環境識別子、Memory 取得結果、Firewall ログ参照を残す。モデル出力の文面だけで「通信拒否」や「環境再生成」を判定しない。

## Risks / Trade-offs

- [Session storage が Preview、リージョン・アカウントで使えない] → 初期の capability check で明確に失敗させ、検証結果を未達とする。EFS への自動切替は仕様の比較条件を変えるため行わない。
- [SNI によるドメイン許可は TLS ECH や直接 IP を識別できない] → 識別不能な通信と UDP/443 を遮断し、許可・拒否・迂回の実測を揃える。
- [Docker Sandbox で ARM64 image をビルドできない] → 配備時は対応 Docker 環境で手動 build/push し、image manifest の architecture を確認してから Terraform を適用する。
- [Firewall/NAT/PrivateLink に継続課金がある] → 検証用の小さな構成と `terraform destroy` 手順を設ける。
- [GitHub MCP のツール名・認可条件が変わる] → 名前を固定せず、読み取り tool が列挙・実行できる条件で判定する。
- [Claude Agent SDK の session transcript と AgentCore Memory の整合が崩れる] → セッション ID の対応を記録し、Memory 書き込み失敗を成功扱いしない。停止後の `resume` を別ケースで試す。
- [セッション ID の再利用と Runtime version 更新でストレージが消える] → version 固定で検証し、更新時消去を結果に明記する。

## Migration Plan

1. AWS アカウントの権限、利用リージョン、Bedrock モデル利用、Session storage の対応を確認する。
2. 読み取り専用 GitHub token を Gateway credential provider に登録し、ARN を得る。人が Docker Sandbox 外の対応環境で `linux/arm64` image をビルドし、architecture を確認して ECR へ push する。
3. Terraform で VPC、endpoints、Firewall、Memory、Gateway、Runtime を作成し、Gateway target の同期完了を待つ。
4. CLI から基本対話、skill、MCP、同一・別セッション、stop/resume、HTTPS 許可・拒否・迂回を実行し、観測結果を記録する。
5. 検証後は token credential と Terraform 管理リソースを削除できるようにする。途中失敗時も同じ手順でロールバックする。
