# CLAUDE.md — nwp_chart_web

## 概要
正式名称: **数値モデル天気図ビューア**（2026-11-06 に旧「ECMWF/GFS/AIFS天気図ビューア」から変更。リポジトリ名は nwp_chart_web のまま）。モデル表示名は ECMWF / GFS / AIFS / JMA GSM。画面の時刻表示はUTCのみ（JST併記なし）。通常版には画像の表示サイズ選択（既定「画面に収める」）と「同期」ボタンがある。
ECMWF（IFS・AIFS）オープンデータ・NOAA GFS（0.25°）・**気象庁GSM（ローカル専用）**から気象庁ビューア風の天気図PNGを作り、ブラウザ/公開サイトで閲覧する。GSM版 `gsm_chart_web` の多モデル・公開対応版。詳しくは [nwp-chart-web.md](nwp-chart-web.md)、方式は [DESIGN.md](DESIGN.md)、公開は [PUBLISH.md](PUBLISH.md)。

## 実行環境
- Python: `/opt/anaconda3/envs/met_env_310/bin/python`（pygrib/cartopy/metpy/scipy/requests/pillow）。`python -I` は使わない。
- 作成: `python update_latest.py` / 閲覧: `python server.py`（http://127.0.0.1:8790/）/ 公開用: `python build_site.py` → `_site/`

## 規約
- コメント・UIは日本語。インデント: Python 4、JS/HTML/CSS 2。f-string内で同じ種類の引用符を入れ子にしない（Python 3.10）。
- **gsm_chart_web と共通部品化しない**（`nwp_charts.py` は `gsm_charts.py` のコピーを調整したもの）。
- 図種は `nwp_charts.py` の `CHARTS`、地域は `REGIONS`。モデルは `nwp_data.py` の `MODELS`。追加したら README・マニュアル・pc_docs も更新。
- `data/`（取得GRIB2の一時置き場）、`output/`、`_site/` はgit除外。

## GSM（ローカル専用モデル）
- **GSM の画像・データは公開しない**。`nwp_data.MODELS["gsm"]` の `local_only` が基準。`publish.py`（`--model gsm` も `--pull` も拒否）、公開用manifest（`write_manifest(public_only=True)`）、`build_site.py`、CIの対象一覧で除外している。**これらを外さない**。新しいローカル専用モデルを足すなら `local_only` を付ける。
- GSMはRISHからファイル全体を取得し、`data/gsm/` に**残す**（作図のたびには削除しない。3日超は自動取得の `--keep-days` が消す。取得済みの `gsm_chart_web/data/gsm` は `--data-dir` で再利用）。既定のFT間隔は3（日本域0.125°が3時間毎）。地域 `japan3`/`okinawa3` はGSM専用（`REGIONS` の `models`/`src`）。
- GSM は launchd（`launchd/*.plist`、`~/Library/LaunchAgents/`）で 00/12UTC のみ自動取得。`--init-hours 0 12 --keep-days 3` で3日より古い PNG/GRIB2 を削除（実測 初回13分42秒）。
- `gsm_source.py` は `gsm_chart_web/gsm_data.py` のコピー（共通部品化しない）。
- **GSMの過去の初期値**は画面の「GSM過去分」ボタン（`past_gsm.py`・`/api/past/*`）で手動取得。取得分は `output/gsm/<初期値>/.keep` の目印で自動削除（`--keep-days`/`--keep`）から除外される。GRIB2・画像は画面の一覧から手動で削除する（2回押し）。APIは `_local_only`・同一Originのみ・`no-cache`（外さない）。

## 取得時刻の実測
- `check_availability.py`（10分おき・launchd、登録はユーザーが行う）が各初期値の配信時刻を `logs/availability.csv` に記録。`--report` で集計。cron を決める根拠にする（2026-11-10 に実測から決定: UTC 1/4/6/7/9/18/20/22/23時）。

## 定期起動（cron-job.org）とトークン期限通知
- GitHub の `schedule` は遅れる・間引かれるため（2026-11-09 に約10時間停止）、**cron-job.org が上記の各時の :30 と :55（1日18回）に `workflow_dispatch` で起動**する。`schedule`（1日9回）は予備。設定・更新手順は [CRON_JOB_ORG.md](CRON_JOB_ORG.md)。
- 専用トークン `nwp-chart-web-dispatch`（Actionsのみ・このリポジトリのみ）の**期限は 2027-02-08 01:45:40 UTC**。期限の14日前から Slack DM で通知（`ops/token_expiry_notify.py`＋launchd `com.masahiro.nwp_chart_web_token_notify` 毎日9:05、導入済み）。**更新したら `~/.config/nwp_chart_web/token_expiry` を書き換える**（忘れると期限切れ通知が毎日届く）。トークンの値は書かない・貼らない。
- `ops/token_expiry_notify.py` は taiwan_radar_frames のコピー（共通部品化しない）。

## 公開分のローカル取り込み
- CIが作った初期値は手元に無いので、`sync_public.py`（画面の「公開分を同期」ボタン／launchd 30分おき `launchd/com.masahiro.nwp_chart_web_sync.plist`）で取り込む。GSMには触れない。取り込みのたびに、初期時刻が3日より古い手元の初期値（ECMWF/GFS/AIFS）を自動削除する（`--keep-days`、確認は `--prune-only --dry-run`）。

## 公開の仕組み（gh-pages ブランチ方式）
- **図種の並びは高層→地上**。`nwp_charts.CHARTS` の定義順と、`web/app.js` の `CHART_ORDER`、`web/board/board.js` の `ORDER`（と `SHORT`）に同じ順を持つ。jet100 は GSM のみ（`levels=[100]` で他モデルは作らない）（公開側の manifest は次の `update-model` まで古い順のままなので、画面側でも並べる）。図種を足すときは3か所に入れる。
- 配信元は gh-pages ブランチ。`publish.py` が必要な部分だけ入れ替えて単一の孤立コミットで push する（`--web-only` は画像に触れない／`--model M` はそのモデルだけ）。
- 画面だけ直したら `web/**` を push すれば `deploy-web.yml` が画像なしで反映する（全量の作図をしない）。
- モデルは `update-model.yml` の matrix で別ジョブ並行。`make_charts.py` は取得と作図を重ねる（全取得完了を待たない）。
- gh-pages を直接編集しない（`publish.py` 経由）。ローカル検証は空の bare リポジトリを `--remote` に指定。

## 落とし穴
- 取得は **索引(.index/.idx)のバイト範囲だけ**。全体（ECMWF約100MB・GFS約540MB/ステップ）を取らない。
- 最新の初期値は「FT72hまで揃っているもの」だけ採る（公開途中を避ける）。ECMWF 06/18UTC は90hまで。
- ECMWFの降水は積算[m]なので前ステップとの差分、GFSは窓付き積算（APCP）で最短窓を採る。
- 975hPa は GFS のみ（ECMWF/AIFSオープンデータに無い）。
- **AIFS**: 相対湿度 `r` が無く比湿 `q` から計算（`_rh_from_q`）。降水 `tp` の単位は kg/m²（IFSは m）→ `TP_TO_MM`。6時間刻みのみ。図種の `levels` で無い面は自動スキップ。
- 湿数 `T−Td` は飽和付近で `-1e-6` 程度の負値になり、`contourf` のハッチが全面塗り/逆転する。`_chart_tdep` で `np.maximum(…, 0)` して levels を `[-0.1, 1.5, 3]` にしている（外さない）。
- **cartopy 0.26 の `contourf(transform=PC)` は帯の領域が地図全面に広がる**（CIは依存が最新版で0.26、手元met_env_310は0.25のため手元では再現しない）。等値線・ハッチ・塗りは `ax.contour(*V.xy(ax), …)` で自前投影した座標で描く（`transform=PC` を付けない）。外さない。CIと同じ環境の再現は `uv venv --python 3.11` ＋ `uv pip install -r requirements.txt`。
- モデル名表示は「ECMWF」（IFSは付けない。AIFSと紛らわしい）。画面側でラベルを分割して使わない（全文を使う）。
- numpy のスレッド競合で並列描画が桁違いに遅くなる → `nwp_charts.py` 冒頭でスレッド数1に固定済み（外さない）。
- 通常版（`web/app.js`）にも2モデル比較モードがある（左が基準、右は `resolve()` で有効時刻を合わせる。URLに `cmp=1&model2=`）。
- 画用紙版はモデルの初期値が違っても**予報有効時刻で合わせる**（`resolve()` / `panelFts()`）。全体の初期値が無いモデルは `ft = 全体の有効時刻 − そのモデルの初期値` の画像を探す。
- Web は**相対パス**（`output/`、`../output/`）。GitHub Pages のサブパスで動くように絶対パスにしない。更新API(`api/`)は無ければボタンを隠す。
- 更新APIはローカル限定（`_local_only`）。外せない。
- 公開（Pages・public化）は勝手にしない。ユーザー確認を取る。
- **出典・ライセンス・免責・改変の表示は外さない**（ECMWF CC BY 4.0 の要件）。文言は `nwp_data.legal_text()`、manifest経由で表示。規約の根拠は PUBLISH.md。
