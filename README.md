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

## 公開サイト（Web）

- **通常版: <https://masauehr.github.io/nwp_chart_web/>**
- **画用紙版（複数図の並べ表示・ECMWFとGFSの比較）: <https://masauehr.github.io/nwp_chart_web/board/>**

GitHub Actions（`.github/workflows/update.yml`）が 1日4回（UTC 5:30 / 11:30 / 17:30 / 23:30）、各モデルの最新の揃った初期値を取得・作図し、GitHub Pages へ公開する。初回の手動実行は成功（約40分）。公開物は PNG と manifest だけで、元データ（GRIB2）は公開サーバーにも保存されない。
方式・容量・利用条件（ECMWF CC BY 4.0 / NOAA）・手順は [PUBLISH.md](PUBLISH.md)。出典・ライセンス・免責・改変の表示は画面に常時出している。

**既知の制約**: 公開サイトには各モデルの最新の初期値だけが載るため、ECMWF と GFS で初期値が異なる場合、画用紙版の「モデル違い」（同じ初期値で比較）が使えないことがある。

## 追加予定

- **ECMWF AIFS（AI予報モデル）の追加を予定**（未実装）。IFS・GFS との比較ができるようにする。詳細は [DESIGN.md](DESIGN.md) の「追加予定: ECMWF AIFS」。

## 図種・地域

- 図種: 地上（降水）/ 地上（天気・SSI）/ 500hPa 高度・渦度 / 500hPa 気温・湿数 / 300 / 850 / 700 / 925 / 975hPa（GFSのみ）/ 850hPa EPT・SSI
- 地域: 日本周辺 / 沖縄周辺 / 東アジア広域

## データ出典

- ECMWF: ECMWF Open Data（CC BY 4.0）。Contains ECMWF open data.
- NOAA/NCEP GFS（NOMADS / AWS Open Data）。
