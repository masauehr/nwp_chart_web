# CLAUDE.md — nwp_chart_web

## 概要
ECMWF オープンデータと NOAA GFS（0.25°）から気象庁ビューア風の天気図PNGを作り、ブラウザ/公開サイトで閲覧する。GSM版 `gsm_chart_web` の多モデル・公開対応版。詳しくは [nwp-chart-web.md](nwp-chart-web.md)、方式は [DESIGN.md](DESIGN.md)、公開は [PUBLISH.md](PUBLISH.md)。

## 実行環境
- Python: `/opt/anaconda3/envs/met_env_310/bin/python`（pygrib/cartopy/metpy/scipy/requests/pillow）。`python -I` は使わない。
- 作成: `python update_latest.py` / 閲覧: `python server.py`（http://127.0.0.1:8790/）/ 公開用: `python build_site.py` → `_site/`

## 規約
- コメント・UIは日本語。インデント: Python 4、JS/HTML/CSS 2。f-string内で同じ種類の引用符を入れ子にしない（Python 3.10）。
- **gsm_chart_web と共通部品化しない**（`nwp_charts.py` は `gsm_charts.py` のコピーを調整したもの）。
- 図種は `nwp_charts.py` の `CHARTS`、地域は `REGIONS`。モデルは `nwp_data.py` の `MODELS`。追加したら README・マニュアル・pc_docs も更新。
- `data/`（取得GRIB2の一時置き場）、`output/`、`_site/` はgit除外。

## 今後の予定
- **ECMWF AIFS（`aifs-single`）を3つ目のモデルとして追加予定**（調査結果と実装方針は DESIGN.md）。AIFSには相対湿度 `r` が無いので比湿 `q` から計算する。出典表記は規約確認後に `legal_text()` へ。

## 落とし穴
- 取得は **索引(.index/.idx)のバイト範囲だけ**。全体（ECMWF約100MB・GFS約540MB/ステップ）を取らない。
- 最新の初期値は「FT72hまで揃っているもの」だけ採る（公開途中を避ける）。ECMWF 06/18UTC は90hまで。
- ECMWFの降水は積算[m]なので前ステップとの差分、GFSは窓付き積算（APCP）で最短窓を採る。
- 975hPa は GFS のみ（ECMWFオープンデータに無い）。図種の `levels` で無い面は自動スキップ。
- numpy のスレッド競合で並列描画が桁違いに遅くなる → `nwp_charts.py` 冒頭でスレッド数1に固定済み（外さない）。
- 画用紙版はモデルの初期値が違っても**予報有効時刻で合わせる**（`resolve()` / `panelFts()`）。全体の初期値が無いモデルは `ft = 全体の有効時刻 − そのモデルの初期値` の画像を探す。
- Web は**相対パス**（`output/`、`../output/`）。GitHub Pages のサブパスで動くように絶対パスにしない。更新API(`api/`)は無ければボタンを隠す。
- 更新APIはローカル限定（`_local_only`）。外せない。
- 公開（Pages・public化）は勝手にしない。ユーザー確認を取る。
- **出典・ライセンス・免責・改変の表示は外さない**（ECMWF CC BY 4.0 の要件）。文言は `nwp_data.legal_text()`、manifest経由で表示。規約の根拠は PUBLISH.md。
