#!/usr/bin/env python
# coding: utf-8
"""気象庁 メソモデル(MSM)の取得（京都大学 RISH）と読み込み。**ローカル専用モデル**用。

gsm_source.py（Rjp 方式）をコピーして MSM 用に調整したもの（共通部品化しない方針）。
MSM のデータ・作図画像は公開サイトには載せない（nwp_data.MODELS の local_only。publish.py が除外する）。

データ提供元: 京都大学生存圏研究所 (RISH) 気象庁データアーカイブ
  http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original/
ファイル（日本域 0.125°×0.1°・約5km。範囲は 120-150E, 22.4-47.6N。481×505）:
  Z__C_RJTD_{YYYYMMDDHH}0000_MSM_GPV_Rjp_{L-pall|Lsurf}_FH{開始}-{終了}_grib2.bin
  初期値は3時間毎（00/03/…/21UTC）。00/12UTC は FT0〜78h、それ以外は FT0〜39h。
  区間は一定でない（pall: 00-15/18-33/36-39/42-51/54-78、surf: 00-15/16-33/34-39/40-51/52-78）。
  等圧面は3時間毎・16面（1000〜100hPa。相対湿度は300hPa以下のみ）、地上は1時間毎。
  降水（APCP）は「直前1時間」の窓（startStep=ft-1, endStep=ft）。全雲量は3時間毎。
取得したファイルは data/msm/ に**残す**（複数のFTで共有されるため。3日超は自動取得の --keep-days が消す）。
"""
import os
import re
import sys

# pygrib/cartopy より前に PROJ のデータ場所を指定（conda 環境で必要になることがある）
_proj = os.path.join(sys.prefix, "share", "proj")
if os.path.isdir(_proj):
    os.environ.setdefault("PROJ_LIB", _proj)

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

BASE_URL = "http://database.rish.kyoto-u.ac.jp/arch/jmadata/data/gpv/original"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NWP-Chart-Web/0.2)"}
DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data" / "msm"
_LOCKS = {}                 # 同じファイルを並行スレッドが二重に取得しないための排他（ファイル名ごと）
_LOCKS_GUARD = threading.Lock()

FILE_RE = re.compile(r"Z__C_RJTD_(\d{10})0000_MSM_GPV_Rjp_(L-pall|Lsurf)_FH(\d{2})-(\d{2})_grib2\.bin")


def parse_init(text: str) -> datetime:
    """YYYYMMDDHH（UTC）→ datetime"""
    return datetime.strptime(text, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def max_ft_of(init: datetime) -> int:
    """その初期値で提供される最大予報時間（00/12UTC は78h、それ以外は39h）。"""
    return 78 if init.hour in (0, 12) else 39


def file_range(name: str):
    """ファイル名 → (初期値, 種別, 開始FT, 終了FT)。該当しなければ None。"""
    m = FILE_RE.fullmatch(name)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3)), int(m.group(4))


def pick(names, init_s: str, kind: str, ft: int):
    """ファイル名の一覧から、指定の初期値・種別で ft を含むものを返す。無ければ None。"""
    for n in names:
        r = file_range(n)
        if r and r[0] == init_s and r[1] == kind and r[2] <= ft <= r[3]:
            return n
    return None


def _get_text(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        return r.text if r.status_code == 200 else None
    except requests.RequestException as e:
        print(f"  RISHへの接続に失敗: {e}")
        return None


def list_day(day: datetime) -> list:
    """指定日(UTC)のRISHディレクトリにある MSM ファイル名の一覧。"""
    text = _get_text(f"{BASE_URL}/{day:%Y/%m/%d}/")
    if text is None:
        return []
    return sorted(set(re.findall(r"Z__C_RJTD_\d{10}0000_MSM_GPV_Rjp_[^\"'<> ]+?_grib2\.bin", text)))


def list_remote(init: datetime) -> list:
    """初期値の MSM ファイル名の一覧。"""
    init_s = f"{init:%Y%m%d%H}"
    return [n for n in list_day(init) if file_range(n) and file_range(n)[0] == init_s]


def remote_status(init: datetime, max_ft: int, step: int = 3, names=None) -> dict:
    """RISH 上で、この初期値の必要ファイルが max_ft まで揃っているかを調べる。

    返り値: {"missing": [FT...], "complete": bool}。公開の途中で作図を始めないための判定。
    """
    names = list_remote(init) if names is None else names
    init_s = f"{init:%Y%m%d%H}"
    missing = [ft for ft in range(0, max_ft + 1, step)
               if pick(names, init_s, "L-pall", ft) is None or pick(names, init_s, "Lsurf", ft) is None]
    return {"missing": missing, "complete": not missing}


def find_latest_complete(max_ft: int, interval: int = 3, days_back: int = 3, hours=None):
    """max_ft まで揃っている最新の初期値を返す。無ければ None。hours（UTC）を指定するとその時刻の初期値だけ。"""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for d in range(days_back + 1):
        day = today - timedelta(days=d)
        names = list_day(day)
        inits = sorted({file_range(n)[0] for n in names if file_range(n)}, reverse=True)
        for init_s in inits:
            init = parse_init(init_s)
            if hours and init.hour not in hours:
                continue
            need = min(max_ft, max_ft_of(init))      # 18UTC などは39hまでなので、その初期値の上限に丸める
            if remote_status(init, need, interval, names)["complete"]:
                return init
    return None


def _fetch(url: str, dest: Path) -> Path | None:
    """URLをdestへ保存。既存ならスキップ。失敗時は None（壊れたファイルは残さない）。
    並行スレッドが同じファイルを要求しても、1つだけが取得し、残りは完了を待って既存として扱う。"""
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(str(dest), threading.Lock())
    with lock:
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            with requests.get(url, headers=HEADERS, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
        except requests.RequestException as e:
            print(f"  ダウンロード失敗 {dest.name}: {e}")
            tmp.unlink(missing_ok=True)
            return None


def download(init: datetime, ft: int, data_dir: Path = DEFAULT_DATA_DIR, names=None) -> bool:
    """ft に必要なファイル（等圧面・地上）を取得する。両方使えれば True。"""
    names = list_remote(init) if names is None else names
    init_s = f"{init:%Y%m%d%H}"
    got = []
    for kind in ("L-pall", "Lsurf"):
        n = pick(names, init_s, kind, ft)
        if n is None:
            return False
        got.append(_fetch(f"{BASE_URL}/{init:%Y/%m/%d}/{n}", Path(data_dir) / n))
    return all(got)


def local_file(data_dir: Path, init: datetime, kind: str, ft: int) -> Path | None:
    """手元のファイルから ft を含むものを探す。"""
    names = [p.name for p in Path(data_dir).glob(f"Z__C_RJTD_{init:%Y%m%d%H}0000_MSM_GPV_Rjp_*")]
    n = pick(names, f"{init:%Y%m%d%H}", kind, ft)
    return Path(data_dir) / n if n else None


# ------------------------------------------------------------------ 読み込み
SURFACE = {
    "msl": ("prmsl", "meanSea", 0),
    "sp": ("sp", "surface", 0),
    "u10": ("10u", "heightAboveGround", 10),
    "v10": ("10v", "heightAboveGround", 10),
    "t2": ("t", "heightAboveGround", 2),            # 2m気温（shortName は t）
}
PLEVELS = (1000, 975, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100)
PVARS = ("gh", "t", "u", "v", "r", "w")


def _scan(path: Path, ft: int):
    """GRIB2を1回走査して、予報時間 ft の場を集める。降水(APCP)は ft の直前1時間の窓を採る。"""
    import numpy as np
    import pygrib

    want = {v: ("s", k) for k, v in SURFACE.items()}
    for lv in PLEVELS:
        for sn in PVARS:
            want[(sn, "isobaricInhPa", lv)] = ("p", (lv, sn))

    out = {"p": {}, "tcc": None, "tp": None}
    lats = lons = None
    grbs = pygrib.open(str(path))
    try:
        for m in grbs:
            end = int(m.endStep)
            if m.typeOfLevel == "surface" and m.shortName == "unknown" \
                    and m.parameterCategory == 1 and m.parameterNumber == 8:
                # 積算降水量 APCP（直前1時間 mm）。pygribの表に無く name が unknown になる
                if end == ft and int(m.startStep) == ft - 1:
                    out["tp"] = np.asarray(m.values, dtype=np.float32)
                continue
            if end != ft:
                continue
            key = (m.shortName, m.typeOfLevel, m.level)
            if key in want:
                kind, k = want[key]
                vals = np.asarray(m.values, dtype=np.float32)
                if lats is None:
                    la, lo = m.latlons()
                    lats, lons = la[:, 0], lo[0, :]
                if kind == "s":
                    out[k] = vals
                else:
                    out["p"].setdefault(k[0], {})[k[1]] = vals
            elif (m.typeOfLevel == "surface" and m.shortName == "unknown"
                  and m.parameterCategory == 6 and m.parameterNumber == 1):
                out["tcc"] = np.asarray(m.values, dtype=np.float32)  # 全雲量 %
    finally:
        grbs.close()
    out["lats"], out["lons"] = lats, lons
    return out


def _finish(parts: list):
    """複数ファイルの走査結果を統合し、単位変換・緯度昇順化して描画用の辞書にする。"""
    import numpy as np
    # 等圧面は 0.25°×0.2°（253×241）、地上は 0.125°×0.1°（505×481）と格子が違う（点は整列＝ちょうど2倍）。
    # 地上の細かい格子に合わせ、等圧面を線形補間（端点を合わせた2倍）でそろえる（新しい情報は増えない）
    tgt = next(d for d in parts if d.get("msl") is not None)
    for d in parts:
        if d is tgt or d.get("lats") is None or len(d["lats"]) == len(tgt["lats"]):
            continue
        from scipy.ndimage import zoom
        fy, fx = len(tgt["lats"]) / len(d["lats"]), len(tgt["lons"]) / len(d["lons"])
        for dd in d["p"].values():
            for k in dd:
                dd[k] = zoom(dd[k], (fy, fx), order=1).astype(np.float32)
        d["lats"], d["lons"] = tgt["lats"], tgt["lons"]
    F = {"p": {}, "tcc": None, "rr": None, "rr_h": 1}
    for d in parts:
        for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "lats", "lons"):
            if d.get(k) is not None:
                F[k] = d[k]
        if d.get("tp") is not None:
            F["rr"] = d["tp"]
        for lv, dd in d["p"].items():
            F["p"].setdefault(lv, {}).update(dd)
    # 必要な変数が揃った面だけ残す
    F["p"] = {lv: d for lv, d in F["p"].items() if all(k in d for k in ("gh", "t", "u", "v"))}
    F["msl"] = F["msl"] / 100.0           # Pa → hPa
    F["sp"] = F["sp"] / 100.0             # 地表気圧 Pa → hPa（地面下のマスクに使う）
    F["t2"] = F["t2"] - 273.15            # K → ℃
    if F["rr"] is not None:
        F["rr"] = F["rr"].clip(min=0)     # 直前1時間 mm/h
    for lv, d in F["p"].items():
        d["t"] = d["t"] - 273.15
        if "w" in d:
            d["w"] = d["w"] * 36.0        # Pa/s → hPa/h（上昇が負）
        else:
            d["w"] = np.zeros_like(d["t"])
        if "r" not in d:                  # 相対湿度は300hPa以下のみ。無い面は50%で埋める（図に使わない面）
            d["r"] = np.full_like(d["t"], 50.0)
    if F["lats"][0] > F["lats"][-1]:      # 緯度を昇順（南→北）へ
        F["lats"] = F["lats"][::-1]
        for k in ("msl", "sp", "u10", "v10", "t2", "tcc", "rr"):
            if F.get(k) is not None:
                F[k] = F[k][::-1, :]
        for d in F["p"].values():
            for k in d:
                d[k] = d[k][::-1, :]
    return F


def load_fields(data_dir: Path, init: datetime, ft: int) -> dict | None:
    """手元のファイルから ft の場を読む。等圧面は3時間毎なので ft が3の倍数でなければ None。ファイルが無ければ None。

    返り値: {"lats","lons","msl"(hPa),"sp"(hPa),"u10","v10","t2"(℃),"tcc"(%),"rr"(mm/h|None),"rr_h"(降水の平均時間=1),
             "p": {1000..100: {"gh"(m),"t"(℃),"u","v","r"(%),"w"(hPa/h)}}}
    """
    if ft % 3 != 0:
        return None
    pall = local_file(data_dir, init, "L-pall", ft)
    surf = local_file(data_dir, init, "Lsurf", ft)
    if pall is None or surf is None:
        return None
    return _finish([_scan(pall, ft), _scan(surf, ft)])


# ------------------------------------------------------------------ nwp_chart_web 用の入口
def fetch(init: datetime, ft: int, data_dir: Path, names=None) -> bool:
    """予報時間 ft に必要なファイルを取得する。ft が3の倍数でなければ何もしない（False）。"""
    if ft % 3 != 0:
        return False
    return download(init, ft, data_dir, names)


def load(init: datetime, ft: int, src: str, data_dir: Path) -> dict | None:
    """描画用の辞書を返す（src は地域の src。MSM は日本域 "rjp" のみ）。"""
    return load_fields(data_dir, init, ft)
