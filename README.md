# nwp_chart_web — ECMWF / GFS 天気図ビューア（公開サーバー対応）

詳しくは [nwp-chart-web.md](nwp-chart-web.md) を参照。公開サーバーの方式・手順は [PUBLISH.md](PUBLISH.md)、設計・調査結果は [DESIGN.md](DESIGN.md)。

ECMWF（IFS オープンデータ）と NOAA GFS（ともに 0.25°）から、気象庁ビューア風の天気図PNGを作り、ブラウザで閲覧する。
`gsm_chart_web`（GSM版）と同じ機能を、2モデルで・公開サーバーに置ける形で作ったもの。

## クイックスタート（ローカル）

```bash
cd ~/projects/nwp_chart_web
conda activate met_env_310
python update_latest.py          # 各モデルの最新の揃った初期値を取得・作図（FT0〜72h、6時間毎）
python server.py                 # → http://127.0.0.1:8790/  （画用紙版は /board/）
```

## 公開サーバー

GitHub Actions で定期的に作図し GitHub Pages へ公開する構成（`.github/workflows/update.yml`）。
**まだ公開していない**（public リポジトリ化と Pages 有効化が必要）。手順は [PUBLISH.md](PUBLISH.md)。

## 図種・地域

- 図種: 地上（降水）/ 地上（天気・SSI）/ 500hPa 高度・渦度 / 500hPa 気温・湿数 / 300 / 850 / 700 / 925 / 975hPa（GFSのみ）/ 850hPa EPT・SSI
- 地域: 日本周辺 / 沖縄周辺 / 東アジア広域

## データ出典

- ECMWF: ECMWF Open Data（CC BY 4.0）。Contains ECMWF open data.
- NOAA/NCEP GFS（NOMADS / AWS Open Data）。
