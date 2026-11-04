# 設計メモ

## 目的
`gsm_chart_web`（GSM版）と同じ機能を ECMWF と GFS で作り、公開サーバーでも見られるようにする。

## 構成
```
配信元(ECMWF/GFS) --索引+Range--> nwp_data.py --> nwp_charts.py --> output/{model}/.../*.png + manifest.json
                                                                       └→ build_site.py → _site/ → GitHub Pages
web/ (相対パス) ← server.py(ローカル) / 静的ホスト(公開)
```
- 取得は必要な変数だけ（索引のバイト範囲）。作図後にGRIB2は捨てる。
- `nwp_data.load_fields` は gsm_chart_web と同じ辞書を返すため、描画コードはほぼそのまま使えた。

## 判断の記録
| 判断 | 理由 |
|---|---|
| gsm_chart_web を共通部品化せずコピーして独立 | 各リポジトリを単独クローンで動かす方針 |
| 全球を最初に東アジア付近へ切り出す（lon50-185, lat-15〜82） | 0.25°全球(1440×721)のまま計算すると遅く、メモリも食う |
| 最新判定は「最後のFTと最初のFTの存在」で代表 | ステップは順に公開される。全FTのHEADは遅い |
| 最新のみ公開・履歴なし（CI） | Actionsはステートレス。容量・運用が単純 |
| PNGを256色に減色 | 容量約1/3。線画・塗り主体で見た目はほぼ変わらない |
| Webは相対パス、更新APIが無ければボタンを隠す | GitHub Pages のサブパスで動かすため |
| ECMWF降水は前ステップとの差分、GFSは最短窓のAPCP | 配信形式の違いを吸収（rr[mm/h]とrr_hで統一） |

## 追加予定: ECMWF AIFS（AI予報モデル）

**予定（未実装）**。ECMWF の AI モデル `aifs-single`（0.25°）を3つ目のモデルとして追加し、IFS・GFS と並べて比較できるようにする。

### 調査済みの事実（2026-11-04、実データの索引を確認）
| 項目 | 内容 |
|---|---|
| 配信元 | `https://data.ecmwf.int/forecasts/{YYYYMMDD}/{HH}z/aifs-single/0p25/oper/{YYYYMMDDHH}0000-{step}h-oper-fc.{grib2,index}`（IFS と同じ構造で、パスの `ifs` が `aifs-single` に変わるだけ） |
| 取得方式 | IFS と同じ（`.index` のバイト範囲を HTTP Range で部分取得） |
| ファイル容量 | 1ステップ全体 約56MB → 必要変数だけで **約22MB**（IFS と同程度） |
| 予報時間 | **6時間刻み**（3時間毎は無い）。12z で 0〜360h の6時間毎を確認。00/06/18z の提供範囲は要確認 |
| 気圧面変数 | `gh, z, t, u, v, w, q`（10〜1000hPaの14面）。**相対湿度 `r` が無い** |
| 地上変数 | `msl, sp, 10u, 10v, 2t, 2d, tcc, lcc, mcc, hcc, tp, cp, sf` など |
| 975hPa | 無い（IFS と同じ。`t975` は GFS のみ） |

### 実装方針
1. `nwp_data.py` の `MODELS` に `aifs` を追加し、`base_url()` / `max_step()` を分岐（`ifs`→`aifs-single`、最大ステップ、提供する初期値の確認）。
2. **湿数の計算が必要**: `r` が無いので、比湿 `q`・気温 `t`・気圧面の気圧から相対湿度を計算して `F["p"][lv]["r"]` に入れる（e = q·p/(0.622+0.378q)、飽和水蒸気圧は Bolton の式など。描画側は変更不要）。地上の露点は `2d` を使える。取得する変数に `q` を追加。
3. 降水は IFS と同様に積算 `tp` の前ステップとの差分。単位（m）は取得して確認する。
4. `update_latest.py` / `build_site.py` / manifest はモデル追加のみで動く設計（`MODELS` を回す）。画面は自動でモデル選択に出る。
5. 画用紙版の「モデル違い」で IFS / AIFS / GFS を並べて比較できる。**IFS と AIFS の差（AIとの比較）が見どころ**。

### 追加時の注意
- **規約の再確認が必要**: AIFS の出力は CC BY 4.0 とされる見込みだが、**AI モデルの出力としての追加の出典表記・注記の有無は未確認**。`nwp_data.legal_text()` に AIFS 用の文言（「ECMWF AIFS」＋ AI が生成した予報である旨＋改変の明示＋免責）を足す前に、ECMWF の公式ページで確認する（PUBLISH.md の確認手順に従う）。
- **容量**: 1モデル増えると約65MB/初期値（6時間毎72h）。合計 約205MB。GitHub Pages の目安（1GB）以内。
- **CI時間**: モデルが増える分、実行時間が延びる。現行（2モデル）の初回実行時間を見て、並列度や対象図種・FTを調整する。
- AIFS のアンサンブル（`aifs-ens`）は今回の予定外。tenkizu に `AIFS_ENS_SurfacePressure.py`（コントロールメンバー）の取得・描画の実装があり、参考にできる。
- 参考: tenkizu の `AIFS_SurfacePressure.py`（地上気圧・風・2m気温、`data/aifs/` へDL）。

## 既知の制約・今後
- CIは未テスト（pip版 pygrib/cartopy、cartopy海岸線の取得、実行時間）。
- ECMWF 00/12UTC の 72h が揃う時刻は実測していない（cron の時刻は目安）。
- 3時間毎の運用は容量が倍（約280MB）。必要になったら `--interval 3`。
- AIFS（ECMWFのAIモデル）の追加は上の「追加予定」を参照。
- ECMWF の 975hPa は無いため `t975` は GFS のみ。
