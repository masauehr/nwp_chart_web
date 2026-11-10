#!/usr/bin/env python
# coding: utf-8
"""JRA-55 再解析（1.25°・6時間毎）の取得と読み込み。**ローカル専用モデル**用（公開サイトには載せない）。

データ提供元: 京都大学生存圏研究所 (RISH) JRA-55 アーカイブ（気象庁 JRA-55 を再配信）
  https://database.rish.kyoto-u.ac.jp/arch/jra55/data/isobaric_1.25d/
  ※ 2026-11-10 の確認では、認証なしで取得できた（tenkizu の README には「認証必要」とあるが、公開側の設定が変わった模様）。
     401/403 が返る場合は、環境変数 JRA55_USER / JRA55_PASSWORD は使えない（NetCDFの範囲読み込みが認証に対応しないため）。
     その場合は月ファイルを手動で JRA55_RAW_DIR（下記）に置く。

方式（月ファイル全体の約1.4GBを取らない）:
  配信は NetCDF4(HDF5) の月単位（等圧面）・年単位（地上）ファイル。HTTP の範囲読み込み（netCDF4 の `#mode=bytes`）で、
  **必要な時刻・気圧面だけ**を読み、時刻ごとの小さなキャッシュ data/jra55/YYYYMMDDHH.npz（約7MB）に保存する。
  同じ5日ブロック（月ファイルの時間チャンク=20時刻）に含まれる時刻は、まとめて読むとほぼ追加コストなしで取れる。
  JRA55_RAW_DIR に月ファイルのコピー（tenkizu の data/Jra55 と同じ構成）があれば、そちらを優先して読む（読み取りのみ・削除しない）。

**系列**: 開始時刻から N 日分（6時間毎）を1つの系列として取得し、「初期値」＝開始時刻・「予報時間」＝開始からの経過時間（FT=0,6,12,…）として扱う
（予報モデルと同じ形なので、画面の予報時間スライダーで時間の推移を動かせる。キャッシュは data/jra55/<開始時刻>/YYYYMMDDHH.npz）。
作れない図: 雲量・降水を使う「地上（天気）」。降水は無い（地上図は気圧・風のみ）。

標準ライブラリ以外（numpy・xarray・netCDF4）は、使うときに読み込む。
"""
import os
import sys
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

BASE_URL = "https://database.rish.kyoto-u.ac.jp/arch/jra55/data/isobaric_1.25d"
DATA = Path(__file__).resolve().parent / "data" / "jra55"    # 時刻ごとのキャッシュ（テストでは差し替える）
LEVELS = (975, 925, 850, 700, 500, 300, 200, 100)             # 取り込む等圧面[hPa]（RHは100〜1000hPaのみ）
ISO_VARS = {"HGT": "gh", "TMP": "t", "UGRD": "u", "VGRD": "v", "RH": "r", "VVEL": "w"}   # 等圧面（VVELは無くても可）
REQUIRED_ISO = ("gh", "t", "u", "v", "r")
SURF_VARS = {"PRES": ("sfc", "sp"), "PRMSL": ("msl", "msl"), "TMP": ("fhg", "t2"),
             "UGRD": ("fhg", "u10"), "VGRD": ("fhg", "v10")}      # 地上（年単位ファイル）: 変数 → (接尾辞, 内部名)
VALID_HOURS = (0, 6, 12, 18)
YEAR_MIN, YEAR_MAX = 1958, 2023                               # RISH の JRA-55 の範囲（2026-11-10 時点）


def parse_valid(text):
    """'2020091012' → 同じ文字列（検証済み）。形式・存在する日時・時刻(00/06/12/18)・年の範囲を確認し、不正なら ValueError。"""
    s = str(text).strip()
    if not re.fullmatch(r"\d{10}", s):
        raise ValueError("有効時刻は YYYYMMDDHH（UTC）の10桁で指定してください")
    try:
        d = datetime.strptime(s, "%Y%m%d%H")
    except ValueError:
        raise ValueError("存在しない日時です")
    if d.hour not in VALID_HOURS:
        raise ValueError("時刻は 00/06/12/18 UTC のいずれかです")
    if not (YEAR_MIN <= d.year <= YEAR_MAX):
        raise ValueError(f"JRA-55 の範囲は {YEAR_MIN}〜{YEAR_MAX} 年です")
    return s


def valid_name(text):
    """既存データの指定用（削除など）。形式だけ確認する（パス組み立ての安全のため）。"""
    s = str(text).strip()
    if not re.fullmatch(r"\d{10}", s):
        raise ValueError("有効時刻は YYYYMMDDHH（UTC）の10桁で指定してください")
    return s


def times_from(start_s, days):
    """start から days 日分（6時間毎・4×days 個）の有効時刻の文字列リスト。範囲外に出たら打ち切る。"""
    d0 = datetime.strptime(parse_valid(start_s), "%Y%m%d%H")
    out = []
    for i in range(int(days) * 4):
        d = d0 + timedelta(hours=6 * i)
        if d.year > YEAR_MAX:
            break
        out.append(f"{d:%Y%m%d%H}")
    return out


def cache_path(valid_s, data_dir=None):
    """時刻ごとのキャッシュ(npz)のパス。data_dir は系列のフォルダ（data/jra55/<開始時刻>/）。"""
    return Path(data_dir or DATA) / f"{valid_s}.npz"


def series_dir(start_s, root=None):
    return Path(root or DATA) / start_s


def have(valid_s, data_dir=None):
    p = cache_path(valid_s, data_dir)
    return p.exists() and p.stat().st_size > 0


# ------------------------------------------------------------------ 取得（範囲読み込み）
def _source(rel):
    """読み込み元。JRA55_RAW_DIR に同じ相対パスのファイルがあればそれ、無ければ RISH（範囲読み込み）。"""
    raw = os.environ.get("JRA55_RAW_DIR")
    if raw and (Path(raw) / rel).exists():
        return str(Path(raw) / rel)
    return f"{BASE_URL}/{rel}#mode=bytes"


def _read_task(args):
    """1ファイル・1変数から、指定した時刻（と気圧面）だけを読む。サブプロセスで実行される。

    戻り値: (name, 時刻リスト, 配列[time,(level),lat,lon] float32, lats, lons)
    """
    import time
    import numpy as np
    import xarray as xr
    kind, rel, var, name, times, levels = args
    last = None
    for attempt in range(3):
        try:
            ds = xr.open_dataset(_source(rel), engine="netcdf4")
            try:
                v = var if var in ds.data_vars else (f"{var}_{rel.split('_')[-2]}" if f"{var}_{rel.split('_')[-2]}" in ds.data_vars
                                                      else list(ds.data_vars)[0])
                da = ds[v].sel(time=[np.datetime64(t) for t in times])
                if levels:
                    da = da.sel(level=list(levels))
                return name, times, da.values.astype("float32"), ds["lat"].values.astype("float32"), ds["lon"].values.astype("float32")
            finally:
                ds.close()
        except Exception as e:     # ネットワークの一時的な失敗は少し待ってやり直す
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{rel} の {var} を読めません: {last!r}")


def _iso(t):
    return f"{t[:4]}-{t[4:6]}-{t[6:8]}T{t[8:10]}:00"


def plan(valid_list):
    """時刻リスト → 読み込みタスクのリスト。等圧面は(変数,年月)ごと、地上は(変数,年)ごとにまとめる。"""
    iso, surf = {}, {}
    for t in valid_list:
        for var, name in ISO_VARS.items():
            iso.setdefault((var, t[:6]), []).append(t)
        for var in SURF_VARS:
            surf.setdefault((var, t[:4]), []).append(t)
    tasks = []
    for (var, ym), ts in sorted(iso.items()):
        rel = f"{var}/{ym[:4]}/{var}_{ym}.nc"
        tasks.append(("iso", rel, var, ISO_VARS[var], [_iso(t) for t in ts], LEVELS))
    for (var, y), ts in sorted(surf.items()):
        suf, name = SURF_VARS[var]
        rel = f"surf/{var}/{var}_{suf}_{y}.nc"
        tasks.append(("surf", rel, var, name, [_iso(t) for t in ts], None))
    return tasks


def fetch(valid_list, data_dir=None, workers=6, log=print):
    """時刻リストのうち未取得のものを取得してキャッシュ(npz)に保存する。取得できた時刻のリストを返す。"""
    import numpy as np
    out_dir = Path(data_dir or DATA)
    todo = [t for t in valid_list if not have(t, out_dir)]
    if not todo:
        return list(valid_list)
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks = plan(todo)
    log(f"JRA-55: {len(todo)} 時刻を取得します（{len(tasks)} 件の読み込みを並列で実行。必要な時刻・気圧面だけ）")
    got = {t: {} for t in todo}
    lats = lons = None
    failed = []
    with ProcessPoolExecutor(max_workers=max(1, min(workers, len(tasks)))) as ex:
        futs = {ex.submit(_read_task, tk): tk for tk in tasks}
        for n, f in enumerate(as_completed(futs), 1):
            tk = futs[f]
            try:
                name, times, arr, la, lo = f.result()
            except Exception as e:
                failed.append((tk[2], tk[1], str(e)[:120]))
                log(f"  失敗: {tk[1]} {tk[2]}: {str(e)[:100]}")
                continue
            lats, lons = la, lo
            for i, iso in enumerate(times):
                got[iso.replace("-", "").replace("T", "").replace(":00", "")[:10]][name] = arr[i]
            log(f"  {tk[2]} {tk[1].split('/')[-1]} 完了（{n}/{len(tasks)}）")
    done = []
    for t in todo:
        d = got[t]
        miss = [k for k in REQUIRED_ISO + ("sp", "msl", "t2", "u10", "v10") if k not in d]
        if miss:
            log(f"  {t}: 必要な変数が揃わないため保存しません（不足: {' '.join(miss)}）")
            continue
        np.savez_compressed(cache_path(t, out_dir), lats=lats, lons=lons, levels=np.array(LEVELS, dtype="int16"), **d)
        done.append(t)
    return [t for t in valid_list if have(t, out_dir)]


# ------------------------------------------------------------------ 読み込み
def load(valid_s, data_dir=None):
    """キャッシュ(npz)から、nwp_charts が使う形式の辞書を作る。無ければ None。

    返り値: {"lats"(昇順),"lons"(0〜358.75),"msl"(hPa),"sp"(hPa),"u10","v10","t2"(℃),"tcc"(None),"rr"(None),"rr_h"(6),
             "no_cloud"(True),"p": {975..100: {"gh"(m),"t"(℃),"u","v","r"(%),"w"(hPa/h)}}}
    """
    import numpy as np
    p = cache_path(valid_s, data_dir)
    if not p.exists():
        return None
    z = np.load(p)
    lats, lons = z["lats"], z["lons"]
    flip = lats[0] > lats[-1]                    # JRA-55 は北→南なので、緯度を昇順（南→北）に直す
    fl = (lambda a: a[..., ::-1, :]) if flip else (lambda a: a)
    F = {"lats": lats[::-1] if flip else lats, "lons": lons, "p": {}, "rr": None, "rr_h": 6, "no_cloud": True}
    F["msl"] = fl(z["msl"]) / 100.0
    F["sp"] = fl(z["sp"]) / 100.0
    F["u10"], F["v10"] = fl(z["u10"]), fl(z["v10"])
    F["t2"] = fl(z["t2"]) - 273.15
    F["tcc"] = np.zeros_like(F["msl"])           # 雲量は無い（天気図は作らない）
    for i, lv in enumerate(int(x) for x in z["levels"]):
        d = {"gh": fl(z["gh"])[i], "t": fl(z["t"])[i] - 273.15, "u": fl(z["u"])[i], "v": fl(z["v"])[i], "r": fl(z["r"])[i]}
        d["w"] = fl(z["w"])[i] * 36.0 if "w" in z.files else np.zeros_like(d["t"])    # Pa/s → hPa/h（無ければ0）
        F["p"][lv] = d
    return F


def list_cached(data_dir=None):
    """キャッシュ済みの有効時刻の一覧 [{valid, mb}]（新しい順）。"""
    d = Path(data_dir or DATA)
    rows = []
    if d.is_dir():
        for f in d.glob("*.npz"):
            if re.fullmatch(r"\d{10}", f.stem):
                rows.append({"valid": f.stem, "mb": round(f.stat().st_size / 1e6, 1)})
    rows.sort(key=lambda r: r["valid"], reverse=True)
    return rows


def delete_cache(valid_s, data_dir=None):
    """キャッシュ(npz)を削除する。削除したら 1、無ければ 0。"""
    p = cache_path(valid_name(valid_s), data_dir)
    if p.exists():
        p.unlink()
        return 1
    return 0


def list_series(root=None):
    """系列（開始時刻）ごとの {series, frames, mb}（新しい順）。root は data/jra55/。"""
    r = Path(root or DATA)
    rows = []
    if r.is_dir():
        for d in r.iterdir():
            if d.is_dir() and re.fullmatch(r"\d{10}", d.name):
                fs = [f for f in d.glob("*.npz") if re.fullmatch(r"\d{10}", f.stem)]
                if fs:
                    rows.append({"series": d.name, "frames": len(fs), "mb": round(sum(f.stat().st_size for f in fs) / 1e6, 1)})
    rows.sort(key=lambda x: x["series"], reverse=True)
    return rows


def delete_series(start_s, root=None):
    """系列のキャッシュ(npz)をすべて削除する（ファイル単位。フォルダも空なら消す）。削除したファイル数を返す。"""
    d = series_dir(valid_name(start_s), root)
    n = 0
    if d.is_dir():
        for f in d.glob("*.npz"):
            f.unlink()
            n += 1
        try:
            d.rmdir()
        except OSError:
            pass
    return n


def migrate_flat(root=None):
    """旧形式（data/jra55/YYYYMMDDHH.npz が直下に並ぶ）を、1時刻ごとの系列フォルダ data/jra55/<時刻>/<時刻>.npz へ移す。移した数を返す。"""
    r = Path(root or DATA)
    n = 0
    if r.is_dir():
        for f in list(r.glob("*.npz")):
            if re.fullmatch(r"\d{10}", f.stem):
                d = r / f.stem
                d.mkdir(exist_ok=True)
                f.rename(d / f.name)
                n += 1
    return n
