#!/usr/bin/env python
# coding: utf-8
"""JRA-55（ローカル専用）の過去の有効時刻を取得して作図する／取得済みの一覧・削除。past_gsm.py の JRA-55 版。

JRA-55 は再解析（解析値）なので「初期値」は有効時刻で、予報時間は0のみ。6時間毎（00/06/12/18UTC）。
取得は京大RISHの月ファイルから、必要な時刻・気圧面だけを範囲読み込みして、時刻ごとの小さなキャッシュ
（data/jra55/YYYYMMDDHH.npz・約7MB）に保存する（詳細は jra55_source.py）。月ファイル（約1.4GB）は保存しない。
地域はアジア域と日本域のみ。キャッシュと画像は自動では削除されない（JRA-55は自動更新の対象外）。

画面（通常版の「GSM過去分」ボタンのダイアログで、モデルを JRA-55 にする）からも同じことができる（server.py の /api/past/*）。

使用例:
  python past_jra55.py fetch 1959092612              # 1日分（4時刻）を取得して作図（約2〜3分）
  python past_jra55.py fetch 1959092600 --days 3     # 3日分（12時刻）。同じ5日ブロックの時刻はほぼ追加コストなし
  python past_jra55.py list
  python past_jra55.py delete 1959092612             # キャッシュ(npz)だけ削除（画像は残す）
  python past_jra55.py delete 1959092612 --png       # 画像も削除
  python past_jra55.py ? / -? / --?                  # ヘルプ
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import jra55_source

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "jra55"       # 作図した PNG（テストでは差し替える）
DAYS_CHOICES = (1, 2, 3, 5)              # 一度に取得する日数（6時間毎×4×日数）


def list_rows():
    """有効時刻ごとの {init, has_data, data_mb, png_count, png_mb} を新しい順に返す（画面の一覧用。initは有効時刻）。"""
    cached = {r["valid"]: r["mb"] for r in jra55_source.list_cached()}
    names = set(cached)
    if OUTPUT.is_dir():
        names |= {d.name for d in OUTPUT.iterdir() if d.is_dir() and re.fullmatch(r"\d{10}", d.name)}
    rows = []
    for n in names:
        pngs = list((OUTPUT / n).glob("*/*.png")) if (OUTPUT / n).is_dir() else []
        rows.append({"init": n, "has_data": n in cached, "data_mb": cached.get(n, 0), "png_count": len(pngs),
                     "png_mb": round(sum(f.stat().st_size for f in pngs) / 1e6, 1)})
    rows.sort(key=lambda r: r["init"], reverse=True)
    return rows


def refresh_manifest():
    subprocess.run([sys.executable, str(ROOT / "make_charts.py"), "--manifest-only"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def delete(valid_s, with_png=False, refresh=True):
    """キャッシュ(npz)を削除する。with_png=True なら画像も削除する。{data, png} の削除数を返す。"""
    s = jra55_source.valid_name(valid_s)
    n_data = jra55_source.delete_cache(s)
    n_png = 0
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
        try:
            d.rmdir()
        except OSError:
            pass
    if refresh and with_png:
        refresh_manifest()
    return {"data": n_data, "png": n_png}


def fetch(valid_s, days=1, jobs=3):
    """有効時刻から days 日分を取得して作図する（make_charts.py jra55 を実行）。戻り値は終了コード。"""
    s = jra55_source.parse_valid(valid_s)
    if days not in DAYS_CHOICES:
        raise ValueError(f"日数は {'/'.join(map(str, DAYS_CHOICES))} のいずれかです")
    print(f"JRA-55 {s}（UTC）から {days} 日分を取得して作図します", flush=True)
    rc = subprocess.run([sys.executable, "-u", str(ROOT / "make_charts.py"), "jra55", s, "--days", str(days),
                         "--jobs", str(jobs), "--dl-jobs", "6"], cwd=ROOT).returncode
    print(f"取得完了: JRA-55 {s}（{days}日・終了コード {rc}）" if rc == 0 else f"取得に失敗: JRA-55 {s}（終了コード {rc}）", flush=True)
    return rc


def main():
    p = argparse.ArgumentParser(description="JRA-55の過去の時刻の取得・一覧・削除（ローカル専用）",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    pf = sub.add_parser("fetch", help="有効時刻から取得して作図する")
    pf.add_argument("init", help="有効時刻 YYYYMMDDHH（UTC。00/06/12/18時。1958〜2023年）")
    pf.add_argument("--days", type=int, default=1, choices=DAYS_CHOICES)
    sub.add_parser("list", help="取得済みの一覧")
    pd = sub.add_parser("delete", help="有効時刻を指定して削除する")
    pd.add_argument("init")
    pd.add_argument("--png", action="store_true", help="画像も削除する（既定はキャッシュだけ）")
    if any(a in sys.argv[1:] for a in ("?", "-?", "--?")):
        p.print_help()
        return 0
    a = p.parse_args()
    try:
        if a.cmd == "fetch":
            return fetch(a.init, a.days)
        if a.cmd == "list":
            rows = list_rows()
            print("有効時刻(UTC)  データ     画像")
            for r in rows:
                print(f"{r['init']}   {r['data_mb']:>5}MB  {r['png_count']:>4}枚 {r['png_mb']:>6}MB")
            print(f"合計 データ {round(sum(r['data_mb'] for r in rows), 1)}MB / 画像 {round(sum(r['png_mb'] for r in rows))}MB")
            return 0
        r = delete(a.init, with_png=a.png)
        print(f"削除: キャッシュ {r['data']} 件" + (f"、画像 {r['png']} 枚" if a.png else ""))
        return 0
    except ValueError as e:
        print("エラー:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
