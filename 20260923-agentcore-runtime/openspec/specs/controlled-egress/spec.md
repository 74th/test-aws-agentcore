# Controlled Egress

## Purpose

Runtime の VPC 経由の外部 HTTPS 通信を許可先のホスト (`github.com` と推論用 `api.anthropic.com`) に絞り、許可先の GitHub ページは取得でき、拒否先のページは取得できないことを検証する。

## Requirements

### Requirement: 外部 HTTPS のホスト許可リスト
Runtime コンテナからの外部 HTTPS 通信は、明示した許可ホストだけを通さなければならない (SHALL)。許可判定の対象はホスト名であり、URL パス単位の制御を保証してはならない (MUST NOT)。

#### Scenario: GitHub ページの取得
- **WHEN** Runtime コンテナから `https://github.com/74th` を取得する
- **THEN** HTTPS 接続が成立し、ページの応答を取得できる

#### Scenario: 許可されていないサイト
- **WHEN** Runtime コンテナから `https://www.tohoho-web.com/` を取得する
- **THEN** ページ本文は取得できず、送信制御による拒否として記録される

### Requirement: 経路の強制
Runtime の外部宛て通信は送信制御を通過し、直接 IP 接続や代替プロトコルで許可リストを迂回できてはならない (SHALL)。AWS サービスへの必要な通信経路は明示しなければならない (SHALL)。

#### Scenario: 迂回の検証
- **WHEN** 許可していない宛先へ直接 IP または UDP/443 で接続を試みる
- **THEN** 外部コンテンツを取得できず、拒否または経路遮断を検証記録で確認できる

#### Scenario: AWS サービスの継続利用
- **WHEN** 送信制御を有効にしてエージェントを呼び出す
- **THEN** Anthropic API 推論、Memory、Gateway 接続とセッションストレージ同期が利用できる
