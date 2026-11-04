#!/usr/bin/env python
# coding: utf-8
"""ECMWF / GFS 天気図の一括作成CLI（取得 → 作図 → 一時データ削除 → manifest更新）。

使用例:
  python make_charts.py ecmwf --latest                      # 最新の揃った初期値を取得して作図（FT0〜72h、6時間毎）
  python make_charts.py gfs 2026110312 --max-ft 24          # 初期値指定
  python make_charts.py ecmwf --latest --interval 3 --jobs 3
  python make_charts.py gfs --latest --charts surf z500 --regions japan
  python make_charts.py --manifest-only                     # output/ を走査して manifest.json だけ更新
  python make_charts.py ? / -? / --?                        # ヘルプ

取得したGRIB2（必要な変数だけ、1ステップ ECMWF約20MB・GFS約40MB）は作図後に削除する（--keep-data で残す）。
サーバーに残るのは output/{model}/{初期値}/{地域}/{図種}_{FT}.png と manifest.json だけ。
"""
import argparse
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import nwp_data
import nwp_charts

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"


def parse_args():
    p = argparse.ArgumentParser(description="ECMWF/GFS から天気図PNGを作成する",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("model", nargs="?", choices=list(nwp_data.MODELS), help="ecmwf または gfs")
    p.add_argument("init_time", nargs="?", help="初期時刻 YYYYMMDDHH（UTC）。--latest 指定時は省略可")
    p.add_argument("--latest", action="store_true", help="必要な予報時間が全部揃った最新の初期値を自動検索する")
    p.add_argument("--max-ft", type=int, default=72, help="作成する最大予報時間[h]（既定: 72）")
    p.add_argument("--min-ft", type=int, default=0, help="作成する最小予報時間[h]（既定: 0）")
    p.add_argument("--interval", type=int, default=6, help="FT間隔[h]（既定: 6。3も可）")
    p.add_argument("--charts", nargs="+", default=list(nwp_charts.CHARTS), choices=list(nwp_charts.CHARTS))
    p.add_argument("--regions", nargs="+", default=list(nwp_charts.REGIONS), choices=list(nwp_charts.REGIONS))
    p.add_argument("--data-dir", default=str(nwp_data.DEFAULT_DATA_DIR), help="取得GRIB2の一時置き場（既定: data/）")
    p.add_argument("--jobs", type=int, default=2, help="作図の並列数（既定: 2）")
    p.add_argument("--dl-jobs", type=int, default=4, help="ダウンロードの並列数（既定: 4）")
    p.add_argument("--keep-data", action="store_true", help="作図後も取得GRIB2を残す")
    p.add_argument("--no-download", action="store_true", help="ダウンロードせず手元のファイルだけ使う")
    p.add_argument("--manifest-only", action="store_true", help="manifest.json の更新だけ行う")
    if any(a in sys.argv[1:] for a in ("?", "-?", "--?")):
        p.print_help()
        sys.exit(0)
    a = p.parse_args()
    if not a.manifest_only and not a.model:
        p.error("model（ecmwf / gfs）を指定してください")
    return a


def _render_ft(args):
    """1つのFT分（全図種・全地域）を描画する。サブプロセスで実行される。"""
    model, init_s, ft, charts, regions, data_dir, interval, keep = args
    init = nwp_data.parse_init(init_s)
    d = Path(data_dir)
    path = d / model / init_s / f"f{ft:03d}.grib2"
    if not path.exists():
        return ft, 0, "データなし"
    tp_prev, zero = None, False
    if model == "ecmwf":
        if ft - interval >= 1:
            tp_prev = d / model / init_s / f"tp_f{ft - interval:03d}.grib2"
        elif ft == interval:
            zero = True
    F = nwp_data.load_fields(model, path, tp_prev if tp_prev and tp_prev.exists() else None, interval, zero)
    n = 0
    for region in regions:
        out = OUTPUT_DIR / model / init_s / region
        out.mkdir(parents=True, exist_ok=True)
        for chart in charts:
            if any(lv not in F["p"] for lv in nwp_charts.CHARTS[chart].get("levels", [])):
                continue  # このモデルに無い気圧面（ECMWFの975hPa）はスキップ
            try:
                nwp_charts.render_chart(chart, region, F, init, ft, out / f"{chart}_{ft:03d}.png",
                                        model=nwp_data.MODELS[model]["label"])
                n += 1
            except Exception as e:  # 1枚の失敗で全体を止めない
                print(f"  失敗: {model} {init_s} FT{ft} {region}/{chart}: {e!r}", flush=True)
    if not keep:
        path.unlink(missing_ok=True)  # 作図が終わったら一時データを捨てる（ファイル単位で削除）
        if model == "ecmwf":
            (d / model / init_s / f"tp_f{ft - interval:03d}.grib2").unlink(missing_ok=True)
    return ft, n, "ok" if n else "データなし"


def write_manifest():
    """output/ を走査して output/manifest.json を作る（Webアプリはこれを読む）。"""
    models = {}
    for model, info in nwp_data.MODELS.items():
        md = OUTPUT_DIR / model
        inits = []
        if md.is_dir():
            for d in sorted(md.iterdir(), reverse=True):
                if not (d.is_dir() and re.fullmatch(r"\d{10}", d.name)):
                    continue
                regions = {}
                for rd in sorted(d.iterdir()):
                    if not rd.is_dir() or rd.name not in nwp_charts.REGIONS:
                        continue
                    charts = {}
                    for f in rd.glob("*_*.png"):
                        m = re.fullmatch(r"(\w+?)_(\d{3})\.png", f.name)
                        if m and m.group(1) in nwp_charts.CHARTS:
                            charts.setdefault(m.group(1), []).append(int(m.group(2)))
                    if charts:
                        regions[rd.name] = {c: sorted(v) for c, v in sorted(charts.items())}
                if regions:
                    inits.append({"init": d.name, "regions": regions})
        if inits:
            now = datetime.now(timezone.utc)
            legal = nwp_data.legal_text(model, now.year, now.strftime("%Y-%m-%d"))
            models[model] = {"label": info["label"], "credit": legal["short"], "notice": legal["notice"],
                             "license_url": legal["license_url"], "inits": inits}
    manifest = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclaimer": ("本サイトの図は、上記の元データを加工して本アプリが作図したもので、各提供元（ECMWF・NOAA/NCEP）の公式な図ではありません。"
                       "予報は不確実性を含みます。防災・安全に関わる判断には、気象庁など公的機関の公式情報を使ってください。"
                       "図の内容や利用による損害について、本サイトの作成者は責任を負いません。"),
        "charts": {k: v["label"] for k, v in nwp_charts.CHARTS.items()},
        "regions": {k: v["label"] for k, v in nwp_charts.REGIONS.items()},
        "models": models,
    }
    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    summary = ", ".join("%s %d件" % (m, len(v["inits"])) for m, v in models.items()) or "画像なし"
    print("manifest.json 更新: " + summary, flush=True)


def build(a):
    """1モデル・1初期値を作る。"""
    data_dir = Path(a.data_dir)
    model = a.model
    if a.latest or not a.init_time:
        init = nwp_data.find_latest_complete(model, a.max_ft, a.interval)
        if init is None:
            print(f"{model}: FT{a.max_ft}hまで揃った初期値が見つかりません")
            return 1
        print(f"{model}: 最新初期値 {init:%Y-%m-%d %H}UTC", flush=True)
    else:
        init = nwp_data.parse_init(a.init_time)
    init_s = f"{init:%Y%m%d%H}"
    ft_list = list(range(a.min_ft, a.max_ft + 1, a.interval))

    if not a.no_download:
        print(f"ダウンロード({model}): FT {len(ft_list)} 個（必要な変数だけ）", flush=True)

        def dl(ft):
            ok = nwp_data.fetch_subset(model, init, ft, data_dir) is not None
            if ok and model == "ecmwf" and ft - a.interval >= 1:
                nwp_data.fetch_tp_only(init, ft - a.interval, data_dir)
            return ft, ok

        with ThreadPoolExecutor(max_workers=a.dl_jobs) as ex:
            res = list(ex.map(dl, ft_list))
        ft_list = [ft for ft, ok in res if ok]
    print(f"描画: FT {len(ft_list)} 個 × 地域 {len(a.regions)} × 図種 {len(a.charts)}", flush=True)

    tasks = [(model, init_s, ft, a.charts, a.regions, str(data_dir), a.interval, a.keep_data) for ft in ft_list]
    if a.jobs > 1:
        with ProcessPoolExecutor(max_workers=a.jobs) as ex:
            results = list(ex.map(_render_ft, tasks))
    else:
        results = [_render_ft(t) for t in tasks]
    total = sum(r[1] for r in results)
    for ft, n, msg in results:
        if msg != "ok":
            print(f"  FT{ft}: {msg}")
    print(f"完了({model}): {total} 枚 → {OUTPUT_DIR / model / init_s}", flush=True)
    return 0 if total else 1


def main():
    a = parse_args()
    if a.manifest_only:
        write_manifest()
        return
    rc = build(a)
    write_manifest()
    sys.exit(rc)


if __name__ == "__main__":
    main()
