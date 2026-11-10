# nwp_chart_web — 数値モデル天気図ビューア（ECMWF / GFS / AIFS / GSM。公開サーバー対応）

詳しくは [nwp-chart-web.md](nwp-chart-web.md) を参照。公開サーバーの方式・手順は [PUBLISH.md](PUBLISH.md)、設計・調査結果は [DESIGN.md](DESIGN.md)。

ECMWF（IFS）・ECMWF AIFS（AI予報モデル）・NOAA GFS（いずれも 0.25°）、およびローカル専用で気象庁GSM から、気象庁ビューア風の天気図PNGを作り、ブラウザで閲覧する。
[gsm_chart_web](https://github.com/masauehr/gsm_chart_web)（GSM版・旧版）と同じ機能を、複数モデルで・公開サーバーに置ける形で作ったものです。

> **関連リポジトリ**: [gsm_chart_web](https://github.com/masauehr/gsm_chart_web) は GSM（気象庁）だけを扱う**旧版（ローカル専用・調査用）**です。こちら（nwp_chart_web）が**後継**で、GSM もローカル専用モデルとして含み、ECMWF・GFS・AIFS と比較できます。GSM だけを単独で動かしたい場合は旧版も使えます（ポートが違うので同時に起動できます）。

## モデルを比較する

ECMWF（IFS）・AIFS・GFS（ローカルでは GSM も）の**同じ図を並べて**比べられます。方法は2通りです。公開サイトでもローカルでも同じ操作です。

### 方法1: 通常版の「2モデル比較」（2つのモデルを左右に並べる）
1つの図を大きく、2モデルで左右に見比べたいときに使います。

1. 通常版を開く（公開サイト: <https://masauehr.github.io/nwp_chart_web/>、ローカル: <http://127.0.0.1:8790/>）。
2. ヘッダーの **「2モデル比較」にチェック**を入れる（またはキーボードの **C**）。
3. **「左のモデル」**と**「右のモデル」**を選ぶ。左右を入れ替えるには「⇄ 入替」（予報有効時刻は保たれる）。
4. 地域ボタン・図種ボタンを選ぶと、**同じ図種・地域・予報有効時刻**の図が左右に並ぶ。
5. ←→ キー・スライダー・再生で時刻を動かすと、**左右が同時に動く**。
6. 元の1枚表示に戻すには、チェックを外す（または C）。

- 画面が狭いときは、左右ではなく上下に並びます。
- 各画像の上の見出しに「モデル名 ｜ 初期値 ＋予報時間」が出ます。
- URL に `cmp=1&model2=…` が入るので、比較画面をそのまま共有・再現できます。

### 方法2: 画用紙版の「モデル違い」（複数の図を並べて、モデルだけ変える）
いくつもの図を画面に並べたまま、あるものだけ別のモデルでも見たいときに使います。

1. 画用紙版を開く（公開サイト: <https://masauehr.github.io/nwp_chart_web/board/>、ローカル: <http://127.0.0.1:8790/board/>）。
2. **比較したい図（画像）をクリックして選択**する（選択した図は青い枠で強調されます）。
3. 上部メニュー2段目の **「モデル違い」ボタンを押す**。
4. 選択した図が、**他のモデルでも同じ範囲で**追加され、画面に並ぶ（見出しに `GFS`・`AIFS` などのモデル名が付く）。
5. ↑↓ キーで予報時間を動かすと、**全ての図が同じ予報有効時刻のまま**進む。

- **先に図を選択しないと「先に図を選択（クリック）してください」と表示され、何も追加されません。**
- 図ごとにモデルを変えたいときは、各図の見出しにある「モデル」欄でも選べます（既定は「モデル:全体」）。上部の「モデル(全体)」を変えると、全体のモデルが変わります。
- 図は重ねたり大きさを変えたりできます（操作は画面右上の「使い方」）。

### 初期値が違うモデルを比較するとき（共通のしくみ）
ECMWF・GFS・AIFS などは、**最新の初期値がモデルごとに違う**ことがあります（例: ECMWF は 18UTC、GFS は 00UTC）。そのため、初期値が違うモデルは **予報有効時刻（実際の時刻）が同じ図**を自動で探して表示します。

- 見出しに `GFS [11/04 00Z +0h]`（画用紙版）や「別の初期値・予報時刻を合わせて表示」（通常版）と出ます。
- 相手のモデルにその時刻の画像が無い（初期値より前の時刻など）ときは、「画像なし」と出ます。**←→（通常版）・↑（画用紙版）で時刻を進める**と出てきます。

## ローカルでの起動方法

### 前提
- Python は conda 環境 `met_env_310`（pygrib・cartopy・metpy・scipy・requests・pillow が入っている環境）を使います。
- **`python3` と打つと別の環境（`~/projects/.venv`）になることがあり、その場合は `ModuleNotFoundError` になります。** 下の例のように `/opt/anaconda3/envs/met_env_310/bin/python` を直接指定するのが確実です（`conda activate met_env_310` した後の `python` でも同じです）。

### 手順（初回）
```bash
cd ~/projects/nwp_chart_web

# 1) 天気図を作る（初回だけ必要）。ECMWF・GFS・AIFS・GSM の最新の揃った初期値を取得・作図（4モデルを並行）
/opt/anaconda3/envs/met_env_310/bin/python update_latest.py

# 2) サーバーを起動する（このターミナルは起動したままにする。止めるときは Ctrl+C）
/opt/anaconda3/envs/met_env_310/bin/python server.py

# 3) ブラウザで開く
#    通常版   : http://127.0.0.1:8790/
#    画用紙版（並べて比較）: http://127.0.0.1:8790/board/
```

- 1) は FT0〜72h で、モデルごとに数十分かかります（ECMWF/AIFS は約20MB、GFS は約38MB、GSM はファイル全体のため約600MB を取得）。まず試すだけなら FT を絞れます: `python update_latest.py --max-ft 12`
- 特定のモデルだけ作る場合: `python update_latest.py --models gfs aifs`
- **GSM を含めて比較したい場合**: GSM は気象庁データ（京大RISH配信）で**ローカル専用**です（公開サイトには載りません）。`update_latest.py` に含まれます。旧版 [gsm_chart_web](https://github.com/masauehr/gsm_chart_web) で取得済みのデータがあれば、再取得せずに使えます:
  ```bash
  /opt/anaconda3/envs/met_env_310/bin/python make_charts.py gsm 2026110312 --data-dir ../gsm_chart_web/data/gsm
  ```
  （日付は取得済みの初期値 YYYYMMDDHH に変える。FT3h 毎の日本域 0.125° も作られる）

### GSM の自動取得（00/12UTC のみ・ローカル）
GSM は **00UTC と 12UTC の初期値だけ**を、launchd で自動取得・作図します（06/18UTC は手動）。ECMWF・GFS・AIFS は公開サイト側（GitHub Actions）が更新するので、この自動取得の対象は GSM だけです。

- 設定: [launchd/com.masahiro.nwp_chart_web_gsm.plist](launchd/com.masahiro.nwp_chart_web_gsm.plist)（`~/Library/LaunchAgents/` に置いて登録）。1時間おきに確認し、揃っていれば取得・作図、作成済みなら数秒で終わります。
- 実行内容: `update_latest.py --models gsm --init-hours 0 12 --keep-days 3 --jobs 4 --dl-jobs 6`
- **所要時間（実測）**: 初期値1つで約14分（13分42秒）。取得 約590MB（FT72h まで）、PNG 851枚（約130MB）。1日2回で約27分。
- **保管**: 初期値が **3日より古い PNG と GRIB2 を自動で削除**します（`--keep-days 3`）。3日分（約6初期値）で約4.3GB。削除対象は `--dry-run` を付けると確認できます。
- ログ: `logs/gsm_auto.log`
- 手動で 06/18UTC を取る: `python make_charts.py gsm 2026110406`（YYYYMMDDHH、UTC）。
- 登録・停止:
  ```bash
  cp launchd/com.masahiro.nwp_chart_web_gsm.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.masahiro.nwp_chart_web_gsm.plist     # 登録（自動取得を開始）
  launchctl unload ~/Library/LaunchAgents/com.masahiro.nwp_chart_web_gsm.plist   # 停止
  ```

### 2回目以降（作成済みの画像を見るだけ）
手順の 2) と 3) だけです。**表示するだけならダウンロードは発生しません**（作成済みの画像を読むだけ。オフラインでも見られます）。

### 最新データに更新する
- 画面ヘッダーの **「最新を取得」** ボタン（サーバーが全モデルを並行して更新し、完了すると自動で切り替わります）。
- またはコマンド: `python update_latest.py`（作成済みの初期値は飛ばし、新しい初期値だけ作ります。`--dry-run` で何をするか確認できます）。

### モデルを比較したいとき

比較のしかたは、上の節 **[モデルを比較する](#モデルを比較する)** を参照してください（通常版の「2モデル比較」と、画用紙版の「図を選んで『モデル違い』」の2通りがあります）。

### バックグラウンドで起動・停止する場合
```bash
nohup /opt/anaconda3/envs/met_env_310/bin/python server.py > /tmp/nwp_server.log 2>&1 &   # 起動
kill $(lsof -ti :8790)                                                                      # 停止
```

### うまくいかないとき
| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError`（pygrib など） | `python3` ではなく `/opt/anaconda3/envs/met_env_310/bin/python` を使う |
| `Address already in use`（ポートが使用中） | `python server.py --port 8791` のように別のポートにする（URLのポートも変える） |
| 「manifest.json を読めません」「天気図がまだありません」 | 手順 1) の `update_latest.py` を先に実行する |
| モデル選択に GSM が出ない | GSM を作っていない。`make_charts.py gsm ...` か `update_latest.py` で作る |
| 比較したいモデルが「画像なし」 | 予報有効時刻が重ならない（相手の初期値より前の時刻など）。↑キーで時刻を進める |
| 画像が古い・初期値が増えない | 「最新を取得」を押す。配信元に新しい初期値がまだ無い場合は作られない |

- サーバーは `127.0.0.1`（自分のPCだけ）で待ち受けます。**他の端末・インターネットには公開されません。** 「最新を取得」ボタンもローカルからだけ使えます。
- 旧版 [gsm_chart_web](https://github.com/masauehr/gsm_chart_web)（GSM のみ、ポート 8780）とは**ポートが違うので同時に起動できます**。
- 公開サイト（GitHub Pages）にはローカルのデータは影響しません。公開側は GitHub Actions が別に更新します（下記）。

## 公開サイト（Web）

- **通常版: <https://masauehr.github.io/nwp_chart_web/>**
- **画用紙版（複数図の並べ表示・モデル比較）: <https://masauehr.github.io/nwp_chart_web/board/>**
- 通常版は **「2モデル比較」**、画用紙版は **「図を選んで『モデル違い』」** でモデルを比較できます（[モデルを比較する](#モデルを比較する)）。

公開は **gh-pages ブランチ**方式（詳細は [PUBLISH.md](PUBLISH.md)）。
- **画面だけの修正**は、push すると `deploy-web.yml` が**画像を作らず**画面ファイルだけを数十秒で反映する。
- **データの更新**は `update-model.yml` が 1日8回（UTC 1:30 / 4:30 / 7:30 / 9:30 / 18:30 / 20:30 / 22:30 / 23:30。配信実測に合わせた時刻）、**モデルごとに別ジョブで並行**して作図し、できたモデルから公開する（取得完了を待たずステップごとに作図）。GitHub の `schedule` は遅れるため、同じ時（UTC）の :30 と :55 に **cron-job.org から `workflow_dispatch` でも起動**する（1日16回）（2026-11-10〜。設定・トークン期限は [CRON_JOB_ORG.md](CRON_JOB_ORG.md)）。
- 公開物は PNG と manifest だけで、元データ（GRIB2）は公開サーバーにも保存されない。約2日分を載せる（ECMWF は 00/12/18UTC の6初期値、GFS・AIFS は 00/12UTC の4初期値。合計約0.9GB）。

出典・ライセンス・免責・改変の表示は画面に常時出している。

**GSM はローカル専用**です。ローカルで `python update_latest.py` や画面の「最新を取得」を使うと、GSM も含めて4モデルを比較できます（公開サイトには GSM を載せません。詳細は [nwp-chart-web.md](nwp-chart-web.md)）。

**モデル比較**: 通常版の「2モデル比較」（左右に並べる）と、画用紙版の「モデル違い」（図を選んで他のモデルを追加）の2通りで、ECMWF（IFS）・AIFS・GFS を比べられます（IFS と AI モデルの差が見どころ）。使い方は上の「[モデルを比較する](#モデルを比較する)」を参照。最新の初期値がモデルで違っても、**予報有効時刻を合わせて**表示する（見出しに `GFS [11/04 00Z +6h]` のように初期値と予報時間が出る）。

## 図種・地域

- 図種: 地上（降水）/ 地上（天気・SSI）/ 500hPa 高度・渦度 / 500hPa 気温・湿数 / 300 / 850 / 700 / 925 / 975hPa（GFSのみ）/ 850hPa EPT・SSI
- モデル: ECMWF（IFS）/ ECMWF AIFS（AI。6時間刻み）/ NOAA GFS（以上は公開サイトにも載る）、**JMA GSM（ローカル専用・公開しない。日本域0.125°・3時間毎も）**
- 地域: 日本周辺 / 沖縄周辺 / 東アジア広域

## データ出典

- ECMWF（IFS・AIFS）: ECMWF Open Data（CC BY 4.0）。Contains ECMWF open data.
- NOAA/NCEP GFS（NOMADS / AWS Open Data）。
- 気象庁 GSM（京都大学生存圏研究所 RISH 配信）— ローカル専用。データは含めず、利用条件は配信元で確認すること。


## 公開分をローカルへ取り込む
CI が作った画像は公開側にしか無いので、`python sync_public.py` か画面の「公開分を同期」ボタンで手元へ取り込む（launchd 雛形 `launchd/com.masahiro.nwp_chart_web_sync.plist` で30分おきの自動実行も可）。
