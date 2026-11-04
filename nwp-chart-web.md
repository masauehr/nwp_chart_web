# nwp_chart_web — ECMWF / GFS 天気図ビューア マニュアル

ECMWF（IFS オープンデータ）と NOAA GFS（ともに 0.25°）から、気象庁ビューア風の天気図PNGを作り、ブラウザで閲覧するアプリ。`gsm_chart_web`（GSM版）と同じ機能を、2モデル・公開サーバー対応で作ったもの。
作成日: 2026-11-04（v0.1）。公開方式の検討と手順は PUBLISH.md、設計は DESIGN.md。

## できること

- 配信元から**必要な変数だけ**を部分取得（ECMWF 約19MB・GFS 約38MB/ステップ）して作図。GRIB2は作図後に削除し、残るのはPNGだけ。
- 図種 10 × 地域 3 × 予報時間（既定 FT0〜72h、6時間毎。`--interval 3` で3時間毎）。
- 通常版（1枚ずつ）と画用紙版（複数を並べる）。**モデル切替**と、**ECMWF と GFS の同時比較**（画用紙版の「モデル違い」）。
- 公開用の静的サイトを `build_site.py` で組み立て可能（GitHub Pages 等）。

| 図種 | 内容 | 備考 |
|---|---|---|
| `surf` | 地上: 海面気圧・H/L・降水(mm/h)・10m風 | 降水: ECMWFは積算の差分、GFSは窓付き積算 |
| `tenki` | 地上: 天気（雲量で晴/薄曇/曇、降水で雨）・SSI(700-850)・風 | |
| `z500` | 500hPa 高度・渦度 | |
| `t500` | 500hPa 気温・湿数・風 | |
| `jet300` | 300hPa 高度・気温・等風速・風 | |
| `t850` / `t700` / `t925` | 気温・湿数（700は上昇流）・風 | |
| `t975` | 975hPa 気温・湿数・風 | **GFSのみ**（ECMWFオープンデータに無い） |
| `ept850` | 850hPa 相当温位・SSI(500-850)・風 | |

地域: `japan` 日本周辺 / `okinawa` 沖縄周辺 / `asia` 東アジア広域。

## 追加予定

- **ECMWF AIFS（AI予報モデル `aifs-single`）を3つ目のモデルとして追加する予定（未実装）**。IFS・GFS と並べて比較できるようにする。取得方式は IFS と同じ（索引のバイト範囲、必要変数で約22MB/ステップ）、予報時間は6時間毎。相対湿度が無いため比湿から湿数を計算する必要がある。AIモデルとしての出典表記の要否は規約を再確認してから追加する。詳細・調査結果は DESIGN.md の「追加予定: ECMWF AIFS」。

## 使い方（ローカル）

```bash
cd ~/projects/nwp_chart_web
conda activate met_env_310      # または /opt/anaconda3/envs/met_env_310/bin/python を直接指定

python update_latest.py                     # 両モデルの「FT72hまで揃った最新の初期値」を取得・作図
python update_latest.py --dry-run           # 何をするかだけ表示
python update_latest.py --models gfs --jobs 3
python make_charts.py ecmwf 2026110312 --max-ft 24     # 初期値・範囲を指定して1モデルだけ
python make_charts.py gfs --latest --charts surf z500 --regions japan
python server.py                            # → http://127.0.0.1:8790/  （画用紙版 /board/）
python build_site.py                        # 公開用の静的サイト → _site/
python make_charts.py ?                     # ヘルプ
```

画面ヘッダーの「**最新を取得**」ボタンは、ローカルサーバーが `update_latest.py` を裏で実行する（公開サイトでは自動的に隠れる）。

## 画面操作

- 通常版: ←→ 予報時間 / ↑↓ 図種 / Space 再生。ヘッダーでモデル・初期値・地域を選ぶ。
- 画用紙版（`board/`）: GSM版と同じ操作（↑↓ 予報時間、←→ 初期値、ホイール拡大縮小、ドラッグ移動、図ごとの範囲選択、広さ違い、配置の登録）に加え、
  - 各図の**モデル欄**で図ごとにモデルを選べる（既定は「モデル:全体」）。
  - 上部の「**モデル違い**」で、選択中の図を他のモデルでも同じ範囲で並べて整列（ECMWF と GFS の比較）。
  - 初期値は両モデルの和集合で、どのモデルにあるかが併記される（モデルで最新の初期値が違うため）。

## ファイル構成

| パス | 役割 |
|---|---|
| `nwp_data.py` | ECMWF/GFS の最新判定・索引からの部分取得・読み込み（`MODELS` にモデル定義） |
| `nwp_charts.py` | 描画（`gsm_charts.py` のコピーを調整。PNGは256色に減色） |
| `make_charts.py` | 1モデル・1初期値の 取得（並列）→ 作図（並列）→ 一時データ削除 → manifest |
| `update_latest.py` | 各モデルの最新の揃った初期値を判定して `make_charts.py` を呼ぶ（画面ボタン・CI用）。`--keep N` で古いPNGを整理 |
| `build_site.py` | 公開用 `_site/`（web/ + output/）を組み立てる |
| `server.py` | ローカルサーバー（`/`=web/、`/output/`、更新API）。既定ポート8790 |
| `web/` | 通常版 / `web/board/` 画用紙版（相対パスなので静的サイトのサブパスでも動く） |
| `.github/workflows/update.yml` | GitHub Actions: 定期的に作図して Pages へ公開（未テスト） |
| `output/{モデル}/{初期値}/{地域}/{図種}_{FT3桁}.png` | 作成画像（git除外）。`output/manifest.json` が一覧 |

## 仕様メモ・注意

- 最新の初期値は「FT72h（既定）まで揃っているもの」だけを採用（公開途中の初期値は飛ばす）。ECMWFの06/18UTCは90hまで。
- 取得GRIB2は `data/{model}/{初期値}/` に一時保存し、作図後にファイル単位で削除（`--keep-data` で残す）。
- 公開の可否・方式・手順・容量見積もりは **PUBLISH.md**。**公開（public化・Pages有効化）は未実施**。
- **出典・ライセンス・免責・改変の表示**を画面に常時出している（ECMWF: 著作権表示・「based on data and products of ECMWF」・CC BY 4.0・免責・改変の明示、NOAA: 出典と取得日・改変の明示・NOAA/NWS非推奨・免責）。文言は `nwp_data.legal_text()`、規約の根拠と未確認事項は PUBLISH.md。
- 0.25°データは、東アジア広域の `ept850` で等値線が細かくなる（今後の調整余地）。
