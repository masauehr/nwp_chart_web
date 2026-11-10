# cron-job.org 設定ガイド — 公開データの定期起動（nwp_chart_web）

作成: 2026-11-10

## 1. なぜ使うか
`update-model.yml` の `schedule`（GitHub側のcron）は遅れたり間引かれたりする。2026-11-09 は 14:08 UTC を最後に約10時間動かず、11/9 12Z 分の公開が遅れた。そこで taiwan_radar_frames と同じく、**cron-job.org から GitHub API で `workflow_dispatch` を呼んで起動**する。`schedule` は予備として残す（同時実行は `concurrency` でモデルごとに1つずつ処理される）。

```
cron-job.org（1日16回）
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
| 実行時刻（UTC） | 時は 1 / 4 / 7 / 9 / 18 / 20 / 22 / 23 の各時の **:30 と :55**（計16回。JST は +9 時間）。GitHub側の `schedule`（予備）は各時の :30 のみの8回 |
| 正常な応答 | `204 No Content` |

時刻の根拠は配信時刻の実測（`check_availability.py --report`）。初期値から72時間分が揃うまで、GFS 約4〜6時間、AIFS 約5.5〜7時間、ECMWF 約7〜11時間。揃っていない回は何も作らず終わる（空振りは安い）。

| 時（UTC・各時の :30 と :55） | 狙い |
|---|---|
| 1 / 4 | ECMWF 18Z |
| 7 / 9 | 00Z（GFS・AIFS は7時台、ECMWF は9時台） |
| 18 / 20 / 22 / 23 | 12Z（ECMWF の遅い回は23時台） |

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
