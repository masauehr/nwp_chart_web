#!/usr/bin/env python
# coding: utf-8
"""各モデル（ECMWF・GFS・AIFS）の初期値が「いつ揃うか」を実測して記録する。

目的: GitHub Actions の取得時刻（cron）を、推測でなく実測で決めるためのデータ集め。
動作: 直近の初期値について、代表の予報時間（FT0・24・48・72h）が配信されたかを軽く確認（HEAD要求のみ・データは取らない）し、
      **最初に確認できた時刻**を logs/availability.csv に追記する。10分おきに実行する想定（launchd）。
      確認の間隔が検出の分解能になる（10分おきなら誤差は最大10分）。

使用例:
  python check_availability.py            # 1回確認して記録（launchd から呼ぶ）
  python check_availability.py --report   # 記録を集計して、モデル×初期時刻ごとの遅れ（初期値からの経過時間）を表示

注意:
  - 初回実行時にすでに揃っていたものは「いつ揃ったか分からない」ので記録しない（状態だけ覚える）。
  - Mac がスリープしている間は確認できない。その間に揃ったものは、復帰後の確認時刻が記録される（遅れが実際より大きく出る）。
    csv の「検出間隔[分]」（前回の確認からの経過）が大きい行は精度が低い。
"""
import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import nwp_data

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
STATE = LOG_DIR / "availability_state.json"
CSV = LOG_DIR / "availability.csv"
MODELS = ("ecmwf", "gfs", "aifs")
FTS = (0, 24, 48, 72)          # 代表の予報時間。72h が「作図に必要な最後」
HOURS_BACK = 30                # この時間より古い初期値は確認しない
HEADER = ["モデル", "初期値UTC", "FT", "検出時刻UTC", "初期値からの経過[h]", "検出間隔[分]"]


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return None


def check():
    LOG_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)
    st = load_state()
    first_run = st is None
    if first_run:
        st = {"seen": {}, "last_check": None}
    last_check = datetime.fromisoformat(st["last_check"]) if st.get("last_check") else None
    gap_min = round((now - last_check).total_seconds() / 60) if last_check else None
    rows = []
    for model in MODELS:
        for init in nwp_data.candidate_inits(days_back=2):
            age_h = (now - init).total_seconds() / 3600
            if age_h < 0 or age_h > HOURS_BACK:
                continue
            for ft in FTS:
                if ft > nwp_data.max_step(model, init):
                    continue
                key = f"{model}/{init:%Y%m%d%H}/{ft}"
                if key in st["seen"]:
                    continue
                if not nwp_data.is_available(model, init, ft):
                    continue
                if first_run:
                    st["seen"][key] = "baseline"          # 初回に揃っていたもの。いつ揃ったか不明
                else:
                    st["seen"][key] = now.isoformat(timespec="seconds")
                    rows.append([model, f"{init:%Y%m%d%H}", ft, f"{now:%Y-%m-%d %H:%M}", f"{age_h:.2f}", gap_min])
    # 古い状態を整理
    cutoff = now - timedelta(hours=HOURS_BACK + 24)
    st["seen"] = {k: v for k, v in st["seen"].items() if nwp_data.parse_init(k.split("/")[1]) > cutoff}
    st["last_check"] = now.isoformat(timespec="seconds")
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    if rows:
        new = not CSV.exists()
        with CSV.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(HEADER)
            w.writerows(rows)
    stamp = f"{now:%Y-%m-%d %H:%M:%S}"
    if first_run:
        print(f"{stamp} 初回: 揃い済み {len(st['seen'])} 件を基準として記録（以降の新規だけ記録します）")
    else:
        for r in rows:
            print(f"{stamp} 新規: {r[0]} {r[1]} FT{r[2]} 経過 {r[4]}h（検出間隔 {r[5]}分）")
        if not rows:
            print(f"{stamp} 新規なし")


def report():
    if not CSV.exists():
        print("まだ記録がありません")
        return
    with CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"記録 {len(rows)} 件（初期値からの経過時間[h]。検出間隔が30分を超える行は除く）")
    print("\n■ 初期値ごとの実測（72h が揃った経過時間 = 作図に必要な最後）")
    last = {}
    for r in rows:
        if r["FT"] == "72":
            last[(r["モデル"], r["初期値UTC"])] = (float(r["初期値からの経過[h]"]), r["検出時刻UTC"], r["検出間隔[分]"])
    for (m, i), (h, t, g) in sorted(last.items(), key=lambda x: (x[0][0], x[0][1])):
        print(f"  {m:6s} {i} → {t} UTC 揃う（初期値から {h:.2f}h後, 検出間隔 {g}分）")
    print("\n■ モデル×初期時刻(UTC)ごとの FT72 が揃うまでの経過時間[h]（中央値・最大・件数）")
    by = {}
    for r in rows:
        if r["FT"] == "72" and (r["検出間隔[分]"] in ("", "None") or int(r["検出間隔[分]"]) <= 30):
            by.setdefault((r["モデル"], r["初期値UTC"][-2:] + "UTC"), []).append(float(r["初期値からの経過[h]"]))
    for (m, hh), v in sorted(by.items()):
        print(f"  {m:6s} {hh}: 中央値 {statistics.median(v):.2f}h / 最大 {max(v):.2f}h / {len(v)}件")
    print("\n■ 参考: FT0 から FT72 までに掛かる時間（公開が順次進む長さ）")
    t0 = {}
    for r in rows:
        t0.setdefault((r["モデル"], r["初期値UTC"]), {})[r["FT"]] = float(r["初期値からの経過[h]"])
    for k, d in sorted(t0.items()):
        if "0" in d and "72" in d:
            print(f"  {k[0]:6s} {k[1]}: FT0 {d['0']:.2f}h → FT72 {d['72']:.2f}h（差 {d['72'] - d['0']:.2f}h）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="初期値が揃う時刻を実測して記録する")
    ap.add_argument("--report", action="store_true", help="記録を集計して表示する")
    a = ap.parse_args()
    report() if a.report else check()
