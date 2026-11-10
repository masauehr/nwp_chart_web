# cron-job.org 設定ガイド — 公開データの定期起動（nwp_chart_web）

作成: 2026-11-10

## 0. 概要 — cron-job.org とは・使う意味・仕組み

### 0-1. cron-job.org とは（ひとことで）
**「決めた時刻になったら、指定したURLにアクセスしてくれる」無料のWebサービス**。目覚まし時計のようなもので、自分のパソコンを起動しておかなくても、インターネット上で時刻どおりに動く。

- もとになっている **cron（クーロン）** は、Linux/Mac にある「毎日9時にこの処理を実行する」といった**定期実行**の仕組み。cron-job.org は、それを**Web上で借りられる**サービス。
- できること: 時刻（毎時・毎日・「各時の30分と55分」など）を決める → その時刻にURLへHTTPリクエスト（GET/POST）を送る → 結果（成功・失敗・応答時間）を履歴に残す。
- アカウント登録（無料）とブラウザの設定画面だけで使え、サーバーやプログラムは要らない。
- 自分ではデータを処理しない。**「時刻になったら合図を送る」だけ**。実際の作図・公開は、合図を受けた側（このプロジェクトでは GitHub Actions）が行う。

### 0-2. なぜ使うのか（使う意味）
このプロジェクトの公開データ（天気図）は、**GitHub Actions の `update-model` が自動で作って公開**している。これを決まった時刻に動かす手段が必要になる。

| 手段 | 問題 |
|------|------|
| GitHub Actions 自身の定期実行（`schedule`） | **時刻が保証されない**。GitHub が混んでいると、数十分〜数時間遅れたり、実行が間引かれたりする（GitHub の仕様）。実際に 2026-11-09 は約10時間動かず、12Z 分の公開が遅れた |
| 手元のMacの launchd | Mac が起動・スリープ解除・ネット接続している間しか動かない。**Mac に頼らない方針**（公開は GitHub 側で完結させたい） |
| **cron-job.org** | 時刻どおりに合図を送ってくれる。無料。Mac不要 |

つまり、**「時刻の正確さ」だけを cron-job.org に任せ、「処理」は GitHub Actions に任せる**という役割分担にしている。GitHub の `schedule` は、cron-job.org が止まったときの**予備**として残してある。

### 0-3. 技術的な仕組み
```
cron-job.org（時刻になったら）
   │  HTTPS で POST を1回送る
   ▼
GitHub の REST API  ─ 「workflow_dispatch（手動実行）」を要求する窓口
   │  認証: 専用トークン（Authorization ヘッダー）
   ▼
GitHub Actions の update-model が起動
   │  最新の初期値を取得 → 作図 → gh-pages ブランチへ公開
   ▼
GitHub Pages（公開サイト）が更新される
```

- **`workflow_dispatch`** は、GitHub Actions に「人が手動で実行する」ためのきっかけ。ボタンを押す代わりに、**APIで同じことをプログラムから行える**。cron-job.org はこのAPIを時刻どおりに叩くだけ。
- **リクエストの中身**: 宛先 `POST https://api.github.com/repos/<所有者>/<リポジトリ>/actions/workflows/update-model.yml/dispatches`、本文 `{"ref":"main","inputs":{"model":"all"}}`（どのブランチで、どのモデルを更新するか）。成功すると **204 No Content**（本文なし）が返る。
- **認証（トークン）**: GitHub に「このリクエストは本人のもの」と伝える**合言葉**。`Authorization: Bearer <トークン>` のヘッダーで送る。このトークンは、**このリポジトリのActionsを動かす権限だけ**（Fine-grained トークン）で、**期限付き**（90日）。コードの書き換えはできない。万一漏れても被害が小さいようにするため。
- **重複実行の防止**: 合図が重なっても、`update-model.yml` の `concurrency`（同じモデルは同時に1つだけ）で順番に処理される。
- **何度呼んでも安全（冪等）**: `update-model` は「新しい初期値が揃っていなければ**何も作らず終わる**」。そのため、合図を多めに送っても無駄な作図や二重公開は起きない。**:30 の回に揃っていなくても、:55 の回に拾える**のはこの性質のおかげ。
- **時刻の基準**: GitHub の cron と同じ UTC で揃えて設定する（cron-job.org の画面は既定が日本時間なので、時刻の入力に注意）。

### 0-4. 気をつけること
- **トークンに期限がある**（このリポジトリは **2027-02-08 01:45:40 UTC**）。切れると 401 で起動に失敗する。期限の14日前から Slack DM で通知する（3-2節）。
- 外部サービスに**トークンを預ける**ことになる。権限を最小（このリポジトリのActionsだけ）・期限付きにして、リスクを抑えている。トークンの値は、チャットやファイル、リポジトリに**書かない**。
- cron-job.org のジョブは、**失敗が続くと自動で無効化**されることがある。止まっていないか、ときどき確認する（4節）。
- 無料プランには、実行間隔や回数などの制限がある（詳細は cron-job.org の公式ページで確認）。現在の1日22回は範囲内で動いている。
- cron-job.org 自体が止まっても、予備の `schedule`（1日11回）が動く。ただし遅れやすいので、公開が古くなることはある。

## 1. なぜ使うか（このプロジェクトでの経緯）
`update-model.yml` の `schedule`（GitHub側のcron）は遅れたり間引かれたりする。2026-11-09 は 14:08 UTC を最後に約10時間動かず、11/9 12Z 分の公開が遅れた。そこで taiwan_radar_frames と同じく、**cron-job.org から GitHub API で `workflow_dispatch` を呼んで起動**する。`schedule` は予備として残す（同時実行は `concurrency` でモデルごとに1つずつ処理される）。

```
cron-job.org（1日22回）
  → POST https://api.github.com/repos/masauehr/nwp_chart_web/actions/workflows/update-model.yml/dispatches
       （専用トークンで認証）
  → GitHub Actions: update-model が起動 → 揃った初期値だけ作図 → gh-pages へ公開
```

## 2. 設定内容
| 項目 | 設定 |
|------|------|
| トークン名 | `nwp-chart-web-dispatch`（Fine-grained・Actions: Read and write・`nwp_chart_web` のみ） |
| **トークン期限** | **2027-02-08 01:45:40 UTC**（cron-job.orgのテスト応答ヘッダー `github-authentication-token-expiration` で確認） |
| URL | `https://api.github.com/repos/masauehr/nwp_chart_web/actions/workflows/update-model.yml/dispatches` |
| 方式・本文 | POST、`{"ref":"main","inputs":{"model":"all"}}` |
| ヘッダー | `Authorization: Bearer <トークン>`、`Accept: application/vnd.github+json`、`X-GitHub-Api-Version: 2022-11-28`、`Content-Type: application/json` |
| 実行時刻（UTC） | 時は 1 / 4 / 6 / 7 / 9 / 10 / 17 / 18 / 20 / 22 / 23 の各時の **:30 と :55**（計22回。6・10・17時台は 2026-11-10 に追加）。GitHub側の `schedule`（予備）は各時の :30 のみの11回 |
| **cron-job.org の入力（JST）** | **cron-job.org の画面は JST で設定している**ので、UTCの時に9を足して入れる: **10 / 13 / 15 / 16 / 18 / 19 / 2 / 3 / 5 / 7 / 8 時**（それぞれ UTC の 1 / 4 / 6 / 7 / 9 / 10 / 17 / 18 / 20 / 22 / 23 時）。分は :30 と :55。**UTC と JST を取り違えると別の時刻になる**（2026-11-10 に6時台が動かなかった原因の疑い）ので、時刻を足すときは必ず変換する |
| 正常な応答 | `204 No Content` |

時刻の根拠は配信時刻の実測（`check_availability.py --report`）。初期値から72時間分が揃うまで、GFS 約4〜6時間、AIFS 約5.5〜7時間、ECMWF 約7〜11時間。揃っていない回は何も作らず終わる（空振りは安い）。

| 時（UTC・各時の :30 と :55） | 狙い |
|---|---|
| 1 / 4 | ECMWF 18Z |
| 6 / 7 / 9 / 10 | 00Z（GFS は6〜7時台、AIFS は6〜7時台、ECMWF は9〜10時台）。**6時台は、AIFS の 00Z が 5:57 UTC に揃ったのに次の 7:30 まで待った（2026-11-10）ため追加。10時台は、ECMWF の 00Z が 10:21 UTC に揃った回があり、次の 18:30 まで約8時間の空白があったため追加** |
| 17 / 18 / 20 / 22 / 23 | 12Z（GFS は16〜18時台なので17時台を追加。ECMWF の遅い回は23時台） |

:55 を足したのは、:30 の回に揃っていなかった場合の取りこぼしを25分後に拾うため（揃っていれば何も作らず終わる）。

## 3. トークンの更新（期限 2027-02-08 の前に）
1. GitHub → Settings → Developer settings → Fine-grained tokens で、`nwp-chart-web-dispatch` を **Regenerate** するか、同じ設定で新規作成する。
2. cron-job.org のジョブのヘッダー `Authorization` を新しいトークンに書き換える（チャットやファイルには貼らない）。
3. **Test run** で `204` を確認し、応答ヘッダーの新しい期限を、この文書の「トークン期限」に書き換える。

期限が切れると401で起動が失敗し、`schedule` の予備だけになる（更新が遅れ、公開が古くなる）。

## 3-2. トークン期限の Slack 通知（2026-11-10〜・Bluesky自動投稿／taiwan_radar_frames と同じ方式）
Macのlaunchd が毎日スクリプトを起動し、`openclaw message send` 経由で Slack DM に送る。

| 項目 | 内容 |
|------|------|
| スクリプト | `ops/token_expiry_notify.py`（taiwan_radar_frames のコピー。部品は共有しない）。テスト `tests/test_token_expiry_notify.py`（11件） |
| 起動 | `launchd/com.masahiro.nwp_chart_web_token_notify.plist`（毎日 9:05 JST。スリープ中だった日は復帰後に1回） |
| 通知する段階 | 期限の14/7/3/2/1日前。期限切れ後は毎日。同じ段階は1回だけ |
| 設定（`~/.config/nwp_chart_web/`・git管理外） | `token_expiry`（期限1行。現在 `2027-02-08T01:45:40Z`）、`slack_to`（通知先）、`notify_state.json`（自動）、`notify.log` |
| 注意 | OpenClaw Gateway が止まっている・Macが起動していない日は届かない |

動作確認: `python3 ops/token_expiry_notify.py --test`（テスト通知）／`--dry-run --now 2027-02-05T00:00:00Z`（通知文だけ表示）。
止める: `launchctl bootout gui/$(id -u)/com.masahiro.nwp_chart_web_token_notify` と `~/Library/LaunchAgents/` の plist を削除。

**トークンを更新したら（3節の最後に必ず）**: `echo '新しい期限' > ~/.config/nwp_chart_web/token_expiry`。書き換えを忘れると、古い期限で「期限切れ」の通知が毎日届く。

## 4. 確認・トラブル対応
- 起動の確認: `gh run list --workflow update-model --limit 8` の `event` が `workflow_dispatch` なら cron-job.org 経由。
- 公開された初期値: `gh api "repos/masauehr/nwp_chart_web/git/trees/gh-pages?recursive=1"` から `output/<モデル>/<初期値>/` を集計する（ECMWF 6・GFS 4・AIFS 4 が目標）。
- 手動で今すぐ更新: `gh workflow run update-model -f model=all`（モデル指定も可）。
- cron-job.org のジョブは連続失敗で自動停止されることがある。止まったら再開する。
- 401: トークン期限切れ／権限不足。403/404: リポジトリ名・ワークフロー名の誤り。422: `ref` や `inputs` の誤り。
