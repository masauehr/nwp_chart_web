#!/usr/bin/env python
# coding: utf-8
"""特定の初期値を「保存」する（自動削除の対象から外す）／保存を解除する／一覧。

背景: 自動取得の画像・データは、初期時刻が3日より古くなると自動で削除される（update_latest.py の --keep-days、
sync_public.py の整理）。過去分取得（past_gsm.py / past_msm.py）は取得時に目印 .keep を置いて除外しているが、
**自動で取れた初期値**（今の台風や大雨の事例など）は後から残す手段が無かった。この機能は、既にある初期値に
同じ目印 output/<モデル>/<初期値>/.keep を置く／外すだけで、過去分取得と同じ扱いにする。

  pin     初期値を保存する（.keep を置く）。画像が output/ に無い初期値は保存できない。
  unpin   保存を解除する（.keep を外す。画像・データは消さない。次回の自動整理で3日超なら消える）。
  list    保存している初期値の一覧（モデル・初期値・画像の数と容量・GRIB2の容量）。

保存で守られるもの（目印 .keep を見て除外する処理）:
  ・update_latest.py の --keep-days / --keep（画像。GSM・MSM は取得データ GRIB2 も）
  ・sync_public.py の古い初期値の整理（ECMWF/GFS/AIFS の画像）
注意:
  ・ECMWF・GFS・AIFS は取得データ（GRIB2）を作図後に捨てる設計のため、保存されるのは**画像だけ**。
  ・GSM・MSM のデータ（GRIB2）は、まだ手元にある間に保存すること（3日を過ぎて消えた後は戻せない）。
  ・JRA-55 は元から自動削除されないので対象外。
  ・保存した分は容量を使い続ける（1初期値: ECMWF/GFS/AIFS 約20〜50MB、GSM 約130MB＋GRIB2 約0.6GB、MSM 約95MB＋GRIB2 約0.57GB）。
    不要になったら unpin して、過去分取得の一覧（GSM・MSM）などで削除する。

標準ライブラリのみ（server.py から読み込むため）。

使用例:
  python keep_init.py pin gfs 2026112700
  python keep_init.py unpin gfs 2026112700
  python keep_init.py list
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"          # テストでは差し替える
DATA = ROOT / "data"              # 同上
KEEP = ".keep"                    # 過去分取得と同じ目印
MODELS = ("ecmwf", "gfs", "aifs", "gsm", "msm")   # JRA-55 は元から自動削除されない
GRIB_TAG = {"gsm": "GSM", "msm": "MSM"}           # 取得データを手元に残すモデル（ファイル名のタグ）


def _check(model, init_s):
    """モデルと初期値の形式を確認する（パス組み立ての安全のため）。不正なら ValueError。"""
    if model not in MODELS:
        raise ValueError(f"モデルは {' / '.join(MODELS)} のいずれかです")
    s = str(init_s).strip()
    if not re.fullmatch(r"\d{10}", s):
        raise ValueError("初期値は YYYYMMDDHH（UTC）の10桁で指定してください")
    return s


def is_pinned(model, init_s):
    return (OUTPUT / model / init_s / KEEP).exists()


def pin(model, init_s, pinned=True):
    """保存する（pinned=False なら解除）。画像のある初期値だけ。{model, init, pinned} を返す。"""
    s = _check(model, init_s)
    d = OUTPUT / model / s
    if not d.is_dir():
        raise ValueError(f"{model} の {s} の画像が手元にありません（保存できません）")
    if pinned:
        (d / KEEP).touch()
    else:
        (d / KEEP).unlink(missing_ok=True)
    return {"model": model, "init": s, "pinned": pinned}


def _size(files):
    return sum(f.stat().st_size for f in files)


def list_pinned():
    """保存している初期値の一覧 [{model, init, png_count, png_mb, grib_mb}]（新しい初期値が先）。"""
    rows = []
    for m in MODELS:
        md = OUTPUT / m
        if not md.is_dir():
            continue
        for d in md.iterdir():
            if not (d.is_dir() and re.fullmatch(r"\d{10}", d.name) and (d / KEEP).exists()):
                continue
            pngs = list(d.glob("*/*.png"))
            grib = []
            if m in GRIB_TAG and (DATA / m).is_dir():
                grib = [f for f in (DATA / m).glob(f"Z__C_RJTD_{d.name}*_{GRIB_TAG[m]}_GPV_*.bin")]
            rows.append({"model": m, "init": d.name, "png_count": len(pngs), "png_mb": round(_size(pngs) / 1e6, 1),
                         "grib_mb": round(_size(grib) / 1e6)})
    rows.sort(key=lambda r: (r["init"], r["model"]), reverse=True)
    return rows


def pinned_map():
    """{モデル: [保存している初期値]}（画面が★を付けるための軽い版）。"""
    out = {}
    for r in list_pinned():
        out.setdefault(r["model"], []).append(r["init"])
    return out


def main():
    p = argparse.ArgumentParser(description="初期値の保存（自動削除の除外）／解除／一覧",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, h in (("pin", "初期値を保存する"), ("unpin", "保存を解除する")):
        sp = sub.add_parser(name, help=h)
        sp.add_argument("model", choices=MODELS)
        sp.add_argument("init", help="初期値 YYYYMMDDHH（UTC）")
    sub.add_parser("list", help="保存している初期値の一覧")
    if any(a in sys.argv[1:] for a in ("?", "-?", "--?")):
        p.print_help()
        return 0
    a = p.parse_args()
    try:
        if a.cmd == "list":
            rows = list_pinned()
            print("モデル  初期値(UTC)   画像           GRIB2")
            for r in rows:
                print(f"{r['model']:<6}  {r['init']}   {r['png_count']:>5}枚 {r['png_mb']:>6}MB  {r['grib_mb']:>5}MB")
            print(f"合計 画像 {round(sum(r['png_mb'] for r in rows))}MB / GRIB2 {sum(r['grib_mb'] for r in rows)}MB（{len(rows)}件）")
            return 0
        r = pin(a.model, a.init, a.cmd == "pin")
        print(f"{'保存しました' if r['pinned'] else '保存を解除しました'}: {r['model']} {r['init']}")
        return 0
    except ValueError as e:
        print("エラー:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
