# Spec Delta

## Purpose

Claude Agent SDK を独自コンテナで AgentCore Runtime に載せ、Bedrock の Claude Haiku 4.5、コンテナ内 skill、検証 CLI を使って分析エージェントの基本動作を確認する。

## ADDED Requirements

### Requirement: Runtime 呼び出し
システムは AgentCore Runtime の HTTP 契約に適合する `linux/arm64` コンテナを microVM compute type で実行し、CLI から `InvokeAgentRuntime` に送られた入力に対する応答を返さなければならない (SHALL)。

#### Scenario: 基本対話
- **WHEN** CLI が新しい Runtime セッション ID とプロンプトを指定して呼び出す
- **THEN** エージェントは Claude Agent SDK を通じて応答し、CLI は応答と再利用可能なセッション ID を表示する

#### Scenario: ARM64 image の配備
- **WHEN** 開発者が Docker Sandbox 外の対応環境で image をビルドして配備する
- **THEN** image は `linux/arm64` であり、microVM 型 Runtime がその image を起動できる

### Requirement: Bedrock モデル利用
エージェントは Claude Haiku 4.5 を Amazon Bedrock 経由で呼び出さなければならない (SHALL)。モデル利用権限がない場合は原因を判別できるエラーを返さなければならない (SHALL)。

#### Scenario: モデル応答
- **WHEN** Bedrock のモデル利用権限がある環境で基本対話を行う
- **THEN** 応答が返り、呼び出し先が指定した Bedrock モデルであることを設定と実行記録から確認できる

#### Scenario: モデル権限不足
- **WHEN** Bedrock モデルへの権限がない
- **THEN** 呼び出しは失敗として報告され、成功した対話として記録されない

### Requirement: コンテナ内 skill
エージェントはコンテナに同梱した検証用 skill を発見し、明示呼び出しで利用できなければならない (SHALL)。

#### Scenario: skill の読み込み
- **WHEN** CLI が検証用 skill を呼び出す
- **THEN** SDK の初期化情報にその skill が現れ、応答に skill 固有の検証結果が含まれる
