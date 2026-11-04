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

## 既知の制約・今後
- CIは未テスト（pip版 pygrib/cartopy、cartopy海岸線の取得、実行時間）。
- ECMWF 00/12UTC の 72h が揃う時刻は実測していない（cron の時刻は目安）。
- 3時間毎の運用は容量が倍（約280MB）。必要になったら `--interval 3`。
- AIFS（ECMWFのAIモデル）は同じ配信元の `aifs-single` で、同じ方式で追加できる見込み。
- ECMWF の 975hPa は無いため `t975` は GFS のみ。
