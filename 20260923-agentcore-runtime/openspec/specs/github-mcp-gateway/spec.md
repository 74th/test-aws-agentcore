# GitHub MCP Gateway

## Purpose

AgentCore Gateway に GitHub MCP を接続し、Runtime 内の Claude Agent SDK が認証情報を直接保持せずに GitHub の読み取りツールを発見・利用できることを確認する。

## Requirements

### Requirement: GitHub MCP ツールの公開
Gateway は GitHub MCP target の読み取りツールを公開し、エージェントは Gateway 経由で `tools/list` 相当の結果を取得できなければならない (SHALL)。

#### Scenario: ツール一覧の取得
- **WHEN** 有効な GitHub 認証情報と Gateway 呼び出し権限でエージェントが GitHub MCP に接続する
- **THEN** GitHub の読み取りツールが 1 件以上列挙され、そのツール名と接続結果を確認できる

### Requirement: 認証情報の分離
GitHub への認証は Gateway の target 側で付与し、Runtime コンテナと CLI の通常の入出力に GitHub 認証情報を含めてはならない (SHALL)。

#### Scenario: 認証失敗
- **WHEN** GitHub 認証情報が無効である
- **THEN** ツール一覧取得は失敗として報告され、認証情報の値は応答やログに表示されない

### Requirement: GitHub 読み取りの確認
エージェントは Gateway 経由の GitHub MCP 読み取りツールで公開リポジトリの情報を取得できなければならない (SHALL)。

#### Scenario: 公開リポジトリの参照
- **WHEN** エージェントに `74th` の公開 GitHub リポジトリの情報取得を依頼する
- **THEN** GitHub MCP ツールを利用した結果が返り、呼び出したツールを検証記録から識別できる
