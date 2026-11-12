# CLAUDE.md — nwp_chart_web

## 概要
正式名称: **数値モデル天気図ビューア**（2026-11-06 に旧「ECMWF/GFS/AIFS天気図ビューア」から変更。リポジトリ名は nwp_chart_web のまま）。モデル表示名は ECMWF / GFS / AIFS / JMA GSM / JRA-55（GSM・JRA-55 はローカル専用）。画面の時刻表示はUTCのみ（JST併記なし）。通常版には画像の表示サイズ選択（既定「画面に収める」）と「同期」ボタンがある。
ECMWF（IFS・AIFS）オープンデータ・NOAA GFS（0.25°）・**気象庁GSM（ローカル専用）**から気象庁ビューア風の天気図PNGを作り、ブラウザ/公開サイトで閲覧する。GSM版 `gsm_chart_web` の多モデル・公開対応版。詳しくは [nwp-chart-web.md](nwp-chart-web.md)、方式は [DESIGN.md](DESIGN.md)、公開は [PUBLISH.md](PUBLISH.md)。

## 実行環境
- 画面を直して確認するとき: **古いサーバーが残っていると、新しいサーバーはポート使用中で起動に失敗し、新機能が効かないように見える**。`lsof -nP -iTCP:8790 -sTCP:LISTEN` で待ち受けているプロセスを確認してから起動する。URL の `#` 以降だけを変えても再読み込みされない。テストは `python -m pytest tests`（pytest は met_env_310 に pip で入れてある）。
- Python: `/opt/anaconda3/envs/met_env_310/bin/python`（pygrib/cartopy/metpy/scipy/requests/pillow）。`python -I` は使わない。
- 作成: `python update_latest.py` / 閲覧: `python server.py`（http://127.0.0.1:8790/）/ 公開用: `python build_site.py` → `_site/`

## 規約
- コメント・UIは日本語。インデント: Python 4、JS/HTML/CSS 2。f-string内で同じ種類の引用符を入れ子にしない（Python 3.10）。
- **gsm_chart_web と共通部品化しない**（`nwp_charts.py` は `gsm_charts.py` のコピーを調整したもの）。
- 図種は `nwp_charts.py` の `CHARTS`、地域は `REGIONS`。モデルは `nwp_data.py` の `MODELS`。追加したら README・マニュアル・pc_docs も更新。
- `data/`（取得GRIB2の一時置き場）、`output/`、`_site/` はgit除外。

## 断面図・エマグラム作成（旧称「自由選択」）と公開掲載（tenkizu_web から移植）
- `custom.py`（検証・作図・一覧）・`xsection.py`・`emagram.py`・`disk_guard.py`・`web/custom.html`/`custom.js`。**tenkizu_web とは共通部品化しない**（コピーして調整。両方を直すときは別々に直す）。API: `/api/custom`・`/api/custom/list`・`/api/custom/publish`・`/api/disk`（`_local_only`・POST は同一Origin。外さない）。
- 取得は `nwp_data.CUSTOM_PLEVELS`（13層）を `data/custom/` へ。**自動更新（`PLEVELS` の7層）の取得量・保存先は変えない**。対象モデルは ECMWF・GFS・AIFS・GSM（再解析 JRA-55 は不可）。地点・断面は `nwp_data.CROP`（東経50〜185度・北緯−15〜82度）の中だけ。
- 「最近の作図」は `output/custom/` の画像と同名の `.json`（条件）から `/api/custom/list` が作る（ブラウザの localStorage に履歴を持たせない）。画像を消す処理は `.json` も一緒に消すこと。
- 公開掲載は `publish.py --custom`（gh-pages の `output/custom/` の `list.json` と画像だけを書き換える。最大20件）。**画面で2回押して確定した画像だけ**公開する（自動では載せない）。公開した名前は手元の `output/custom/published.json` に記録する。`sync_web`・`sync_model` が `output/custom/` に触れないこと。公開サイトで新しく作るのは、Render の API（下の節）。API の URL が空の公開版は閲覧専用。
- 通常版の「別の図を並べる」（`web/app.js`。右に別の地域の図／断面図・エマグラムの図（ローカルは直近10件・公開サイトは公開分の20件まで）。公開サイトは `output/custom/list.json` の公開分）。2モデル比較とは同時に使えない。tenkizu_web とは別々にコピーしてあるので、直すときは両方を見る。
- 自由選択の GRIB2（`data/custom/`）と画像（`output/custom/`）は `disk_guard.py` が上限を超えた分を古い順に削除する。GSM・作図済み画像は警告のみ。launchd `com.masahiro.nwp_chart_web_disk`（6時間おき・2026-11-11 登録済み・ログ `logs/disk_guard.log`）が定期的に実行して通知する。

## 公開サイトからの断面図（Render の API・2026-11-12 有効化。API 側は別リポジトリ nwp_xsection_api）
- `web/config.js` の `window.NWP_XSECTION_API`（Render の URL）が**空なら従来どおり**（公開版は閲覧専用）。URL を入れて push すると `web/custom.js` が `REMOTE_MODE` になり、公開サイトで断面図を作れる（作図は認証なし・公開サイトへの掲載だけ合言葉）。API の応答形式（`/api/xsection`・`/api/emagram`・`/api/job/<id>`・`/api/publish`）を変えたら nwp_xsection_api と一緒に直す。
- **表記**: 作れるとき（ローカル、または `config.js` に API の URL がある公開サイト）は「断面図・エマグラム作成」。作れない公開サイトだけ、以前の「保存された断面図・エマグラム」（`app.js` の `canMake`・`CUSTOM_NAME`）。「自由選択」は画面には出さない（文書の機能名としては残る）。
- 画面（`custom.js` の `goRemote`）は、ジョブIDを別の変数（`jid`）に持つ（状態確認の応答にはIDが無い場合があるため。過去に `/api/job/undefined` で失敗した）。サーバー停止中（接続不可・502/503）は待ち、記録が消えた（404）ときは同じ条件を自動で再送する（最大3回）。
- ローカルサーバー（`LOCAL=true`）の挙動は変えない（`REMOTE_MODE` は `!LOCAL && REMOTE` のときだけ）。断面図・エマグラムの両方が API の対象（`/api/xsection`・`/api/emagram`）。
- API が gh-pages の `output/custom/`（画像と `list.json`）を Contents API で書く。`list.json` の形式は `publish.py --custom` と同じ（`by` は追加項目）。`sync_web` は `config.js` も反映する（公開に URL が載るが秘密ではない）。**2026-11-12 に Render の URL（`https://nwp-xsection-api.onrender.com`）を設定済み**（API 側は実機で作図・`publish: true` を確認済み）。無効に戻すときは `NWP_XSECTION_API` を空にして push。

## GSM（ローカル専用モデル）
- **GSM の画像・データは公開しない**。`nwp_data.MODELS["gsm"]` の `local_only` が基準。`publish.py`（`--model gsm` も `--pull` も拒否）、公開用manifest（`write_manifest(public_only=True)`）、`build_site.py`、CIの対象一覧で除外している。**これらを外さない**。新しいローカル専用モデルを足すなら `local_only` を付ける。**ただし例外（2026-11-12 ユーザー決定）**: 自由選択（断面図・エマグラム）で作った GSM の図は、画面で2回押して手動で載せたものに限り公開してよい（定期更新・自動の公開は引き続き GSM を除外。配信元の再配布条件は未確認のまま、ユーザーが認めた）。
- GSMはRISHからファイル全体を取得し、`data/gsm/` に**残す**（作図のたびには削除しない。3日超は自動取得の `--keep-days` が消す。取得済みの `gsm_chart_web/data/gsm` は `--data-dir` で再利用）。既定のFT間隔は3（日本域0.125°が3時間毎）。地域 `japan3`/`okinawa3` はGSM専用（`REGIONS` の `models`/`src`）。
- GSM は launchd（`launchd/*.plist`、`~/Library/LaunchAgents/`）で 00/12UTC のみ自動取得。`--init-hours 0 12 --keep-days 3` で3日より古い PNG/GRIB2 を削除（実測 初回13分42秒）。
- `gsm_source.py` は `gsm_chart_web/gsm_data.py` のコピー（共通部品化しない）。
- **GSMの過去の初期値**は画面の「過去分取得」ボタン（`past_gsm.py`・`/api/past/*`）で手動取得。取得分は `output/gsm/<初期値>/.keep` の目印で自動削除（`--keep-days`/`--keep`）から除外される。GRIB2・画像は画面の一覧から手動で削除する（2回押し）。APIは `_local_only`・同一Originのみ・`no-cache`（外さない）。

## JRA-55（ローカル専用・再解析）
- `nwp_data.MODELS["jra55"]`（`local_only`・`auto=False`）。公開しない（`publish.py`・`sync_public.py`・`build_site.py` の除外は GSM と同じ仕組み）。**自動更新（`update_latest.py`）の対象外**（`nwp_data.auto_models()`）。
- **系列**: 開始時刻から N 日分（6時間毎）を1つの系列にし、「初期値」＝開始時刻・FT＝開始からの経過時間[h]（FT=0,6,12,…。予報モデルと同じ形なので画面のスライダー・再生で動かせる・2モデル比較は解析時刻で合う）。manifest の `analysis:true` で画面の文言を「解析 開始／解析時刻」に変える。取得は `jra55_source.py`（RISHの月ファイルを `#mode=bytes` で必要な時刻・気圧面だけ範囲読み込み→`data/jra55/<開始時刻>/YYYYMMDDHH.npz`。旧形式のフラットなキャッシュは `migrate_flat()` が移す）。**認証は不要**（2026-11-10確認）。取得・一覧・削除は画面の「過去分取得」（モデル=JRA-55）と `past_jra55.py`。
- 地域は **アジア・日本のみ**（`REGIONS` の `exclude`。沖縄域は作らない）。雲量が無いので `tenki`（`cloud=True`）は作らない。降水が無いので地上図は気圧・風のみ。キャプションは年も出す（`ANAL:`）。
- 地面下は外挿値で埋まっているので、`sp`（地表気圧 PRES）でマスクする。`w` は VVEL（無ければ0）。月ファイルの時間チャンクは20時刻（5日）で、同じ日の取得はほぼ追加コストなし。
- `JRA55_RAW_DIR`（任意）に月ファイルのコピーがあれば優先して読む（読み取りのみ。削除しない）。

## 取得時刻の実測
- **画面にも同じ表がある**（通常版のフッターの折りたたみ・画用紙版の使い方パネル）。値を変えるときは README と両方の画面を直す。
- **自動取得する初期値**: ECMWF は 00/12/**18**Z、GFS・AIFS は 00/12Z（06Z は取らない。容量の都合）。GSM（ローカル）は 00/12Z。揃うまでの目安は GFS 約4〜6h・AIFS 約5.3〜9h・ECMWF 約6.6〜11.4h。表は README の「各モデルの自動取得の初期値と、取得（公開）時刻の目安」。
- `check_availability.py`（10分おき・launchd、登録はユーザーが行う）が各初期値の配信時刻を `logs/availability.csv` に記録。`--report` で集計。cron を決める根拠にする（2026-11-10 に実測から決定: UTC 1/4/6/7/9/10/17/18/20/22/23時）。

## 定期起動（cron-job.org）とトークン期限通知
- GitHub の `schedule` は遅れる・間引かれるため（2026-11-09 に約10時間停止）、**cron-job.org が上記の各時の :30 と :55（1日22回。**cron-job.org の画面は JST で設定している**＝UTCの時に+9）に `workflow_dispatch` で起動**する。`schedule`（1日11回）は予備。設定・更新手順は [CRON_JOB_ORG.md](CRON_JOB_ORG.md)。
- 専用トークン `nwp-chart-web-dispatch`（Actionsのみ・このリポジトリのみ）の**期限は 2027-02-08 01:45:40 UTC**。期限の14日前から Slack DM で通知（`ops/token_expiry_notify.py`＋launchd `com.masahiro.nwp_chart_web_token_notify` 毎日9:05、導入済み）。**更新したら `~/.config/nwp_chart_web/token_expiry` を書き換える**（忘れると期限切れ通知が毎日届く）。トークンの値は書かない・貼らない。
- `ops/token_expiry_notify.py` は taiwan_radar_frames のコピー（共通部品化しない）。

## 公開分のローカル取り込み
- CIが作った初期値は手元に無いので、`sync_public.py`（画面の「公開分を同期」ボタン／launchd 30分おき `launchd/com.masahiro.nwp_chart_web_sync.plist`）で取り込む。GSMには触れない。取り込みのたびに、初期時刻が3日より古い手元の初期値（ECMWF/GFS/AIFS）を自動削除する（`--keep-days`、確認は `--prune-only --dry-run`）。

## 公開の仕組み（gh-pages ブランチ方式）
- **図種の並びは高層→地上**。`nwp_charts.CHARTS` の定義順と、`web/app.js` の `CHART_ORDER`、`web/board/board.js` の `ORDER`（と `SHORT`）に同じ順を持つ。jet100 は GSM と JRA-55 のみ（`levels=[100]` で、100hPaを持たない ECMWF/GFS/AIFS は作らない）（公開側の manifest は次の `update-model` まで古い順のままなので、画面側でも並べる）。図種を足すときは3か所に入れる。
- 配信元は gh-pages ブランチ。`publish.py` が必要な部分だけ入れ替えて単一の孤立コミットで push する（`--web-only` は画像に触れない／`--model M` はそのモデルだけ）。
- 画面だけ直したら `web/**` を push すれば `deploy-web.yml` が画像なしで反映する（全量の作図をしない）。
- モデルは `update-model.yml` の matrix で別ジョブ並行。`make_charts.py` は取得と作図を重ねる（全取得完了を待たない）。
- gh-pages を直接編集しない（`publish.py` 経由）。ローカル検証は空の bare リポジトリを `--remote` に指定。

## 落とし穴
- ローカルからの公開（`publish.sync_custom`）の一覧項目は、API 経由（nwp_xsection_api の `ghpub`）と同じ形にしてある: `ts`＝作図した時刻（`created`。画像の最終使用時刻ではない）・`pub`＝公開した時刻。どちらかの形を変えたら両方そろえる（`tests/test_publish_custom.py`）。
- **高度設定 `ptop`**（表示する高度の範囲の上端[hPa]。`xsection.PTOPS`・既定100）は、`custom.py`・`xsection.py`・`emagram.py` と、nwp_xsection_api（`opts.py`・`engine.py`・`xsection.py`・`emagram.py`）の**両方に別々のコピーがある**。直すときは両方。既定（100）のときは条件 `p` に入れない（画像名が従来と同じ）。画面は `web/custom.js` の `q.set("ptop", …)`（ローカルと公開サイトの2か所）。
- **モデルの公開（`publish.py --model`）は画面ファイル（web/）を上書きしない**（`should_sync_web`。画面の反映は deploy-web だけ。公開ブランチが無い初回だけ例外）。起動時の古い `web/` を持つジョブが、画面を直して push した後に終わって古い画面で上書きし、修正が公開サイトに出なかった（2026-11-12）。画面を直して push したら、公開サイト（gh-pages）の該当ファイルが新しいか確認する。
- 公開サイトの**公開の上限は20件**（`publish.py` の `CUSTOM_MAX` と nwp_xsection_api の `ghpub.MAX_ITEMS` を同じにする。片方が小さいと、もう一方が公開した分を切り詰める）。
- **公開サイトの容量（Pages 1GB・サイト＝リポジトリ単位）は約0.88GBでほぼ上限**。図種・地域・公開個数を増やす前に見積もる（`gh api repos/masauehr/nwp_chart_web --jq .size`）。方針と選択肢は PUBLISH.md の「容量の制約と対応方針」。WebPは効果が小さく見送り。
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
