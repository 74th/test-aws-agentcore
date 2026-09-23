# AgentCore Runtime 検証

AWS Bedrock のモデル利用可否に依存せず、カスタムコンテナを Amazon Bedrock AgentCore Runtime で動かしたときの実行環境、セッション、Memory、ネットワーク制御を確認する検証プロジェクトです。推論には Anthropic API を使っています。Claude Agent SDK は Runtime 上で動作させるワークロードであり、このプロジェクトの主な検証対象は AgentCore です。

## 検証環境

- AWS アカウント: 個人環境の情報保護のため非掲載
- リージョン: `us-west-2`
- コンテナ: ECR の `linux/arm64` イメージ (`memory-continuity-verify`)
- Runtime: AgentCore Runtime version 6 が `READY`。プライベートサブネットに配置し、実行ログを有効化
- 周辺サービス: AgentCore Memory、Identity の API キー credential provider、Gateway（GitHub MCP target は未接続確認）
- ネットワーク: 2 AZ の VPC、Network Firewall、NAT Gateway、AgentCore/ECR/Logs 等の VPC endpoint

## 分かったこと・確認できたこと

| 項目 | 結果 |
| --- | --- |
| ARM64 カスタムイメージの配置 | ECR の `memory-continuity-verify` (`linux/arm64`) で Runtime version 6 が `READY`。Memory-only モードの実対話は version 5 で成功し、その後 version 6 で session storage を復元。 |
| Bedrock 以外の推論 API | Runtime から Identity credential provider 経由で Anthropic API を呼び出し、Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) の応答を確認。Bedrock のモデル利用権限がなくても、この構成で推論を実行できた。 |
| Runtime 上のアプリ実行 | SDK がプロジェクト内の検証用 skill を検出し、明示的な実行結果 `FEASIBILITY_SKILL_OK` を返した。これは Runtime コンテナ上でアプリが動くことのスモークテスト。 |
| AgentCore Memory | `feasibility-user` と Runtime session ID に対応する user / assistant イベントを確認。 |
| session storageによる継続 | 別々のCLI呼び出し間でSDK会話を継続し、60秒アイドル終了後もmanaged session storage (`/mnt/workspace`) 上のファイルとSDK状態を読み戻せた。 |
| Memoryだけによる継続 | session storageを無効にした状態で約70秒待ち、`instance_id`の変化後もAgentCore Memoryから1件の会話イベントを取得。以前のSDK session IDを使わず、固有の確認語に正答。結果イベントは2件、別session IDからの取得は0件。 |
| セッション分離 | 別 session ID では別の Runtime `instance_id` となり、元セッションの workspace ファイルを読めなかった。 |
| ドメインベースの送信制御 | Runtime から `github.com` と `api.anthropic.com` への通信を許可し、許可外ドメイン `www.tohoho-web.com` は遮断。Network Firewall の TLS SNI drop ログも確認。 |
| IP / UDP 送信制御 | GitHub の IP への直接 HTTPS と UDP/443 を遮断。Network Firewall の drop ログを確認。 |
| Terraform 構成 | `terraform validate` と plan を実施。preflight はリポジトリルートと `terraform/` の両方から実行できる。 |

## セッションのアイドル待機と再開

Runtime は呼び出しごとにコンテナを終了するのではなく、session ID ごとの実行環境をアイドル状態で保持し、同じIDへの次の呼び出しをその環境に届けます。AWSの既定アイドルタイムアウトは15分で、アイドル時間は同じセッションへの呼び出しごとにリセットされます。タイムアウトまたは最大寿命（既定8時間）に達すると実行環境は終了し、同じIDで再度呼び出すと新しい環境が起動します。

この検証では再起動後の確認をしやすくするため、アイドルタイムアウトを最小値の60秒に設定しています。通常モードはmanaged session storageを`/mnt/workspace`にマウントし、SDKのsession ID対応表・設定・会話状態を保存して`resume`します。一方、Memory-only検証では`enable_session_storage=false`にしてこのmountを外し、SDKの古いsession IDを使わず、AgentCore Memoryの短期イベントを新しいSDK会話に明示的に渡しました。約70秒後に`instance_id`が変わった後も固有の確認語に答え、Memoryイベントも取得できました。つまり、この構成ではMemoryから会話を復元するには、イベントを取得してモデルの入力に含めるアプリ側の処理が必要です。

AWSの仕様: [Runtime lifecycle settings](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-lifecycle-settings.html)、[Runtime filesystem configurations](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-filesystem-configurations.html)。

## 未確認: Gateway と GitHub MCP

GitHub MCP を AgentCore Gateway の target として同期するところで失敗しています。Gateway は `https://api.githubcopilot.com/mcp/readonly` の initialize handshake に対する HTTP 400 を報告しました。これは Claude Agent SDK が GitHub MCP を呼び出して返した 400 ではありません。Gateway の `tools/list` と、その tool 経由の read-only 呼び出しは未確認です。

切り分けとして、Identity に登録した同じ GitHub token を使い Gateway を介さずに MCP endpoint を呼んだ場合は initialize と `tools/list` が成功しました（28 tools）。ただし対象の `74th/test-aws-agentcore` リポジトリは空で、ファイル読み出しは GitHub 409 になりました。この直接呼び出しは原因の切り分け材料であり、AgentCore Gateway の成功実績ではありません。token はコンテナイメージや Terraform state に入れていません。

OpenSpec の実装タスクは 22 項目中 19 項目が完了。残る3項目はいずれもGatewayのtarget同期、RuntimeからのGateway呼び出し、Gateway経由のMCP tool列挙・読み出しです。したがって、Gatewayを今回のAgentCore検証範囲に含めるかを決めれば、次に何を試すかを絞れます。Claude Agent SDK内にGitHub認証情報を持ち込む経路は、このREADMEでは未実施項目として扱っていません。

## レビュー時に決めたいこと

1. 今回の目的に Gateway の検証も含めるか。それとも Runtime、Memory、セッション、ネットワーク制御の確認をもって AgentCore 検証を区切るか。
2. Gateway を継続する場合、GitHub MCP 接続失敗を未解決事項として記録して閉じるか、Gateway に絞った追加調査を次の検証にするか。
3. Gateway 以外に、今回の目的に照らして追加したい AgentCore の機能・運用観点があるか。

## 実行記録・注意事項

詳細なコマンド、観測時刻、credential 登録と後片付け手順は [`docs/verification.md`](docs/verification.md) を参照してください。Terraform の AWS リソースはまだ削除していません。VPC、NAT Gateway、Network Firewall、endpoint、Memory、Gateway、Runtime、ECR などが残っており、特に NAT Gateway と Network Firewall は継続課金の対象です。検証を終える際は同記録の cleanup 手順を確認してください。
