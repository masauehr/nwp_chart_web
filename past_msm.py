#!/usr/bin/env python
# coding: utf-8
"""MSM（ローカル専用）の過去の初期値を手動で取得して作図する／取得済みの一覧・削除。

past_gsm.py をコピーして MSM 用に調整したもの（共通部品化しない方針）。
背景: MSM の自動取得（update_latest.py）は最新の初期値だけを取り、3日より古い PNG と GRIB2 を自動で削除する
（--keep-days 3）。過去の事例を見たいときは、この機能で京大RISHのアーカイブから初期値を指定して取得する。

  fetch   RISHの過去の初期値（3時間毎）を取得して作図する（make_charts.py msm を裏で実行）。
          取得した初期値には目印 output/msm/<初期値>/.keep を置く → **自動削除の対象外**になる。
  list    手元にある MSM の初期値ごとの、GRIB2・画像の数と容量を表示する。
  delete  初期値の GRIB2 を削除する（--png で画像・目印も削除）。

使用例:
  python past_msm.py fetch 2026101012                 # 78時間分（約0.57GB。00/12UTC以外は最大39時間）
  python past_msm.py fetch 2026101012 --max-ft 24     # 24時間分
  python past_msm.py list
  python past_msm.py delete 2026101012 --png
"""
import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "msm"          # 取得した GRIB2（テストでは差し替える）
OUTPUT = ROOT / "output" / "msm"      # 作図した PNG
KEEP = ".keep"                        # 手動取得の目印（これがある初期値は自動削除しない）
FILE_RE = re.compile(r"Z__C_RJTD_(\d{10})\d{4}_MSM_GPV_")
INIT_HOURS = (0, 3, 6, 9, 12, 15, 18, 21)   # MSM の初期時刻（UTC・3時間毎）
FT_CHOICES = (24, 48, 78)             # 取得する予報時間[h]の選択肢（78hで約0.57GB。00/12UTC以外は39hまで）


def parse_init(text):
    """'2026101012' → 同じ文字列（検証済み）。形式・時刻(00/06/12/18UTC)・未来でないことを確認し、不正なら ValueError。"""
    s = str(text).strip()
    if not re.fullmatch(r"\d{10}", s):
        raise ValueError("初期値は YYYYMMDDHH（UTC）の10桁で指定してください")
    try:
        d = datetime.strptime(s, "%Y%m%d%H")
    except ValueError:
        raise ValueError("存在しない日時です")
    if d.hour not in INIT_HOURS:
        raise ValueError("初期時刻は 00/03/06/…/21 UTC（3時間毎）のいずれかです")
    if d > datetime.now(timezone.utc).replace(tzinfo=None):
        raise ValueError("未来の初期値は指定できません")
    return s


def valid_init_name(text):
    """削除など既存の初期値の指定用。形式だけ確認する（パス組み立ての安全のため。未来・時刻は問わない）。"""
    s = str(text).strip()
    if not re.fullmatch(r"\d{10}", s):
        raise ValueError("初期値は YYYYMMDDHH（UTC）の10桁で指定してください")
    return s


def is_kept(init_s):
    return (OUTPUT / init_s / KEEP).exists()


def _dir_size(files):
    return sum(f.stat().st_size for f in files)


def list_inits():
    """MSM の初期値ごとの {init, grib_files, grib_mb, png_count, png_mb, manual} を新しい順に返す。"""
    gribs = {}
    if DATA.is_dir():
        for f in DATA.glob("Z__C_RJTD_*_MSM_GPV_*.bin"):
            m = FILE_RE.match(f.name)
            if m:
                gribs.setdefault(m.group(1), []).append(f)
    names = set(gribs)
    if OUTPUT.is_dir():
        names |= {d.name for d in OUTPUT.iterdir() if d.is_dir() and re.fullmatch(r"\d{10}", d.name)}
    rows = []
    for n in names:
        pngs = list((OUTPUT / n).glob("*/*.png")) if (OUTPUT / n).is_dir() else []
        gf = gribs.get(n, [])
        rows.append({"init": n, "grib_files": len(gf), "grib_mb": round(_dir_size(gf) / 1e6), "png_count": len(pngs),
                     "png_mb": round(_dir_size(pngs) / 1e6, 1), "manual": is_kept(n)})
    rows.sort(key=lambda r: r["init"], reverse=True)
    return rows


def refresh_manifest():
    """画面の一覧(manifest.json)を作り直す。"""
    subprocess.run([sys.executable, str(ROOT / "make_charts.py"), "--manifest-only"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def delete(init_s, with_png=False, refresh=True):
    """初期値の GRIB2 を削除する。with_png=True なら画像と目印(.keep)も削除する。{grib, png} の削除数を返す。"""
    s = valid_init_name(init_s)
    n_grib = n_png = 0
    if DATA.is_dir():
        for f in DATA.glob("Z__C_RJTD_*_MSM_GPV_*.bin"):
            m = FILE_RE.match(f.name)
            if m and m.group(1) == s:
                f.unlink()
                n_grib += 1
    d = OUTPUT / s
    if with_png and d.is_dir():
        for f in d.glob("*/*.png"):
            f.unlink()
            n_png += 1
        for sub in list(d.iterdir()):
            if sub.is_dir():
                try:
                    sub.rmdir()
                except OSError:
                    pass
        (d / KEEP).unlink(missing_ok=True)
        try:
            d.rmdir()
        except OSError:
            pass
    if refresh and with_png:
        refresh_manifest()
    return {"grib": n_grib, "png": n_png}


def fetch(init_s, max_ft=78, jobs=3, dl_jobs=4):
    """RISHから初期値を取得して作図する。戻り値は終了コード。"""
    s = parse_init(init_s)
    if max_ft not in FT_CHOICES:
        raise ValueError(f"予報時間は {'/'.join(map(str, FT_CHOICES))} のいずれかです")
    import msm_source  # RISHへの問い合わせだけ（ここで初めて requests 等を読み込む）
    day = datetime.strptime(s, "%Y%m%d%H")
    remote = {msm_source.file_range(n)[0] for n in msm_source.list_day(day) if msm_source.file_range(n)}
    if s not in remote:
        print(f"エラー: RISH に {s}（UTC）の初期値がありません（アーカイブに無い日時か、まだ公開されていません）", flush=True)
        return 2
    d = OUTPUT / s
    d.mkdir(parents=True, exist_ok=True)
    (d / KEEP).touch()  # 先に目印を置く（途中で止まっても自動削除されない）
    max_ft = min(max_ft, msm_source.max_ft_of(msm_source.parse_init(s)))   # 00/12UTC以外は39hまで
    print(f"{s}（UTC）を取得して作図します（FT0〜{max_ft}h）", flush=True)
    rc = subprocess.run([sys.executable, "-u", str(ROOT / "make_charts.py"), "msm", s, "--max-ft", str(max_ft),
                         "--interval", "3", "--jobs", str(jobs), "--dl-jobs", str(dl_jobs)], cwd=ROOT).returncode
    print(f"取得完了: {s}（終了コード {rc}）" if rc == 0 else f"取得に失敗: {s}（終了コード {rc}）", flush=True)
    return rc


def main():
    p = argparse.ArgumentParser(description="MSMの過去の初期値の取得・一覧・削除（ローカル専用）",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fetch", help="過去の初期値を取得して作図する")
    pf.add_argument("init", help="初期値 YYYYMMDDHH（UTC。3時間毎）")
    pf.add_argument("--max-ft", type=int, default=78, choices=FT_CHOICES)
    sub.add_parser("list", help="取得済みの一覧")
    pd = sub.add_parser("delete", help="初期値を削除する")
    pd.add_argument("init")
    pd.add_argument("--png", action="store_true", help="画像と目印も削除する（既定はGRIB2だけ）")
    if any(a in sys.argv[1:] for a in ("?", "-?", "--?")):
        p.print_help()
        return 0
    a = p.parse_args()
    try:
        if a.cmd == "fetch":
            return fetch(a.init, a.max_ft)
        if a.cmd == "list":
            rows = list_inits()
            print("初期値(UTC)   GRIB2          画像           手動取得")
            for r in rows:
                print(f"{r['init']}   {r['grib_files']:>3}個 {r['grib_mb']:>5}MB  {r['png_count']:>5}枚 {r['png_mb']:>6}MB   {'○' if r['manual'] else ''}")
            print(f"合計 GRIB2 {sum(r['grib_mb'] for r in rows)}MB / 画像 {round(sum(r['png_mb'] for r in rows))}MB")
            return 0
        r = delete(a.init, with_png=a.png)
        print(f"削除: GRIB2 {r['grib']} 個" + (f"、画像 {r['png']} 枚" if a.png else ""))
        return 0
    except ValueError as e:
        print("エラー:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
