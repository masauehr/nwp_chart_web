# nwp_chart_web — ECMWF / GFS / AIFS 天気図ビューア（公開サーバー対応）

詳しくは [nwp-chart-web.md](nwp-chart-web.md) を参照。公開サーバーの方式・手順は [PUBLISH.md](PUBLISH.md)、設計・調査結果は [DESIGN.md](DESIGN.md)。

ECMWF（IFS）・ECMWF AIFS（AI予報モデル）・NOAA GFS（いずれも 0.25°）から、気象庁ビューア風の天気図PNGを作り、ブラウザで閲覧する。
`gsm_chart_web`（GSM版）と同じ機能を、3モデルで・公開サーバーに置ける形で作ったもの。

## クイックスタート（ローカル）

```bash
cd ~/projects/nwp_chart_web
conda activate met_env_310
python update_latest.py          # 各モデルの最新の揃った初期値を取得・作図（FT0〜72h、6時間毎）
python server.py                 # → http://127.0.0.1:8790/  （画用紙版は /board/）
```

## 公開サイト（Web）

- **通常版: <https://masauehr.github.io/nwp_chart_web/>**
- **画用紙版（複数図の並べ表示・ECMWFとGFSの比較）: <https://masauehr.github.io/nwp_chart_web/board/>**

公開は **gh-pages ブランチ**方式（詳細は [PUBLISH.md](PUBLISH.md)）。
- **画面だけの修正**は、push すると `deploy-web.yml` が**画像を作らず**画面ファイルだけを数十秒で反映する。
- **データの更新**は `update-model.yml` が 1日4回（UTC 5:30 / 11:30 / 17:30 / 23:30）、**モデルごとに別ジョブで並行**して作図し、できたモデルから公開する（取得完了を待たずステップごとに作図）。
- 公開物は PNG と manifest だけで、元データ（GRIB2）は公開サーバーにも保存されない。各モデル最新2初期値を載せる。

出典・ライセンス・免責・改変の表示は画面に常時出している。

**モデル比較**: 画用紙版の「モデル違い」で ECMWF（IFS）・AIFS・GFS を並べられる（IFS と AI モデルの差が見どころ）。最新の初期値がモデルで違っても、**予報有効時刻を合わせて**表示する（見出しに `GFS [11/04 00Z +6h]` のように初期値と予報時間が出る）。

## 図種・地域

- 図種: 地上（降水）/ 地上（天気・SSI）/ 500hPa 高度・渦度 / 500hPa 気温・湿数 / 300 / 850 / 700 / 925 / 975hPa（GFSのみ）/ 850hPa EPT・SSI
- モデル: ECMWF IFS / ECMWF AIFS（AI。6時間刻み）/ NOAA GFS
- 地域: 日本周辺 / 沖縄周辺 / 東アジア広域

## データ出典

- ECMWF（IFS・AIFS）: ECMWF Open Data（CC BY 4.0）。Contains ECMWF open data.
- NOAA/NCEP GFS（NOMADS / AWS Open Data）。
