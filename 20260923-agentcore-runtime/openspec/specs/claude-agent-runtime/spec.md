# Claude Agent Runtime

## Purpose

Claude Agent SDK を独自コンテナで AgentCore Runtime に載せ、Anthropic API の Claude Haiku 4.5、コンテナ内 skill、検証 CLI を使って分析エージェントの基本動作を確認する。

## Requirements

### Requirement: Runtime 呼び出し
システムは AgentCore Runtime の HTTP 契約に適合する `linux/arm64` コンテナを microVM compute type で実行し、CLI から `InvokeAgentRuntime` に送られた入力に対する応答を返さなければならない (SHALL)。

#### Scenario: 基本対話
- **WHEN** CLI が新しい Runtime セッション ID とプロンプトを指定して呼び出す
- **THEN** エージェントは Claude Agent SDK を通じて応答し、CLI は応答と再利用可能なセッション ID を表示する

#### Scenario: ARM64 image の配備
- **WHEN** 開発者が Docker Sandbox 外の対応環境で image をビルドして配備する
- **THEN** image は `linux/arm64` であり、microVM 型 Runtime がその image を起動できる

### Requirement: Anthropic API モデル利用
エージェントは AgentCore Identity の API key provider から取得した API key を使って、Claude Haiku 4.5 を Anthropic API 経由で呼び出さなければならない (SHALL)。AWS の Bedrock モデル利用権限に依存してはならない (MUST NOT)。認証または API 利用に失敗した場合は成功した対話として記録してはならない (MUST NOT)。

#### Scenario: モデル応答
- **WHEN** Anthropic API key provider が登録された Runtime で基本対話を行う
- **THEN** 応答が返り、呼び出し先が指定した Anthropic モデルであることを設定と実行記録から確認できる

#### Scenario: モデル権限不足
- **WHEN** Anthropic API key が無効または未登録である
- **THEN** 呼び出しは失敗として報告され、API key の値は応答やログに表示されない

### Requirement: コンテナ内 skill
エージェントはコンテナに同梱した検証用 skill を発見し、明示呼び出しで利用できなければならない (SHALL)。

#### Scenario: skill の読み込み
- **WHEN** CLI が検証用 skill を呼び出す
- **THEN** SDK の初期化情報にその skill が現れ、応答に skill 固有の検証結果が含まれる
