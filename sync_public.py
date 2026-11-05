#!/usr/bin/env python
# coding: utf-8
"""公開サイト（gh-pages）で作られた画像を、手元の output/ へ取り込んで manifest.json を更新する。

目的: GitHub Actions が作った新しい初期値は公開側にしか無く、ローカル版（server.py）に出ない。
      これを取り込んで、ローカルでも同じ初期値を見られるようにする。
動作: 公開ブランチの先頭コミットが前回と同じなら何もしない（重い取り込みを避ける）。
      違えば ECMWF / GFS / AIFS を順に取り込み、manifest.json を作り直す。
      GSM（ローカル専用）には触れない。

使用例:
  python sync_public.py            # 変更があれば取り込む（launchd・画面のボタンから呼ぶ）
  python sync_public.py --force    # 変更の有無にかかわらず取り込む
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import make_charts
import nwp_data
import publish

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "logs" / "sync_state.json"
MODELS = [m for m, c in nwp_data.MODELS.items() if not c.get("local_only")]


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="公開済みの画像を手元へ取り込む")
    ap.add_argument("--force", action="store_true", help="変更の有無にかかわらず取り込む")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default="gh-pages")
    a = ap.parse_args()
    tip = publish.fetch_tip(a.remote, a.branch)
    if tip is None:
        log("公開ブランチを取得できません（ネットワークを確認）")
        return 1
    last = json.loads(STATE.read_text(encoding="utf-8")).get("tip") if STATE.exists() else None
    if tip == last and not a.force:
        log("公開側に変更はありません")
        return 0
    for m in MODELS:
        publish.pull(SimpleNamespace(remote=a.remote, branch=a.branch, model=m))
    make_charts.write_manifest()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps({"tip": tip, "synced": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")
    log("取り込み完了（manifest.json を更新しました）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
