"""past_gsm.py（GSM過去分の取得・一覧・削除）、自動削除の除外、サーバーAPIの単体テスト（ネットワーク・RISH不使用）"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import past_gsm  # noqa: E402
import server  # noqa: E402
import update_latest  # noqa: E402


def grib_name(init, ft=0, kind="Rgl"):
    return f"Z__C_RJTD_{init}0000_GSM_GPV_{kind}_FD{ft:04d}_grib2.bin"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.data, self.out = t / "data" / "gsm", t / "output" / "gsm"
        self.data.mkdir(parents=True)
        self.out.mkdir(parents=True)
        self._o = (past_gsm.DATA, past_gsm.OUTPUT, update_latest.OUTPUT_DIR)
        past_gsm.DATA, past_gsm.OUTPUT, update_latest.OUTPUT_DIR = self.data, self.out, t / "output"
        self.refreshed = []
        self._r = past_gsm.refresh_manifest
        past_gsm.refresh_manifest = lambda: self.refreshed.append(1)   # 実際の作り直しはしない

    def tearDown(self):
        past_gsm.DATA, past_gsm.OUTPUT, update_latest.OUTPUT_DIR = self._o
        past_gsm.refresh_manifest = self._r
        self.tmp.cleanup()

    def make(self, init, manual=False, grib=2, png=3):
        for ft in range(grib):
            (self.data / grib_name(init, ft * 6)).write_bytes(b"x" * 1000)
        d = self.out / init / "asia"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(png):
            (d / f"surf_{i:03d}.png").write_bytes(b"p" * 500)
        if manual:
            (self.out / init / ".keep").touch()


class TestParse(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(past_gsm.parse_init(" 2026101012 "), "2026101012")

    def test_bad(self):
        for bad in ("20261010", "2026101013", "2026101007", "abcdefghij", "2026023012", ""):
            with self.assertRaises(ValueError, msg=bad):
                past_gsm.parse_init(bad)

    def test_future(self):
        f = (datetime.utcnow() + timedelta(days=2)).strftime("%Y%m%d") + "00"
        with self.assertRaises(ValueError):
            past_gsm.parse_init(f)

    def test_name_blocks_path_tricks(self):
        for bad in ("../x", "2026101012/../..", "2026-10-10"):
            with self.assertRaises(ValueError):
                past_gsm.valid_init_name(bad)


class TestListDelete(Base):
    def test_list(self):
        self.make("2026101012", manual=True)
        self.make("2026110900")
        rows = past_gsm.list_inits()
        self.assertEqual([r["init"] for r in rows], ["2026110900", "2026101012"])   # 新しい順
        r = {x["init"]: x for x in rows}["2026101012"]
        self.assertEqual((r["grib_files"], r["png_count"], r["manual"]), (2, 3, True))
        self.assertFalse(rows[0]["manual"])

    def test_delete_grib_only(self):
        self.make("2026101012", manual=True)
        self.make("2026110900")
        r = past_gsm.delete("2026101012")
        self.assertEqual(r, {"grib": 2, "png": 0})
        self.assertEqual(len(list(self.data.glob("*.bin"))), 2)            # 別の初期値は残る
        self.assertTrue((self.out / "2026101012" / "asia" / "surf_000.png").exists())
        self.assertTrue((self.out / "2026101012" / ".keep").exists())      # 画像が残るので目印も残る
        self.assertEqual(self.refreshed, [])

    def test_delete_all(self):
        self.make("2026101012", manual=True)
        r = past_gsm.delete("2026101012", with_png=True)
        self.assertEqual(r, {"grib": 2, "png": 3})
        self.assertFalse((self.out / "2026101012").exists())
        self.assertEqual(self.refreshed, [1])

    def test_delete_missing_is_ok(self):
        self.assertEqual(past_gsm.delete("2026101012", with_png=True), {"grib": 0, "png": 0})


class TestAutoPruneSkipsManual(Base):
    def test_prune_days(self):
        self.make("2026101012", manual=True)    # 古い・手動 → 残る
        self.make("2026101000")                 # 古い・自動 → 消える
        update_latest.prune_days(["gsm"], 3, str(self.data.parent), dry_run=False)
        self.assertTrue((self.out / "2026101012").exists())
        self.assertEqual(len(list(self.data.glob("*20261010120000*"))), 2)
        self.assertEqual(len(list(self.data.glob("*20261010000000*"))), 0)
        self.assertFalse(any((self.out / "2026101000").glob("*/*.png")))

    def test_prune_keep_count(self):
        self.make("2026101012", manual=True)
        self.make("2026110900")
        self.make("2026110912")
        update_latest.prune("gsm", 1)           # 最新1件だけ残す（手動は数に入れず残す）
        self.assertTrue(any((self.out / "2026101012").glob("*/*.png")))
        self.assertTrue(any((self.out / "2026110912").glob("*/*.png")))
        self.assertFalse(any((self.out / "2026110900").glob("*/*.png")))


class TestServerApi(Base):
    def setUp(self):
        super().setUp()
        self.started = []
        self._s = server.start_update
        server.start_update = lambda script="", args=(): self.started.append((script, args)) or True
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.Handler, directory=str(ROOT / "web")))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        server.start_update = self._s
        super().tearDown()

    def call(self, path, body=None, origin=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_list(self):
        self.make("2026101012", manual=True)
        code, j = self.call("/api/past/list")
        self.assertEqual(code, 200)
        self.assertEqual(j["inits"][0]["init"], "2026101012")
        self.assertEqual(j["ft_choices"], [24, 48, 72])

    def test_fetch_starts_job(self):
        code, j = self.call("/api/past/fetch", {"init": "2026101012", "max_ft": 24})
        self.assertEqual(code, 200)
        self.assertEqual(self.started, [("past_gsm.py", ("fetch", "2026101012", "--max-ft", "24"))])

    def test_fetch_rejects_bad_input(self):
        for body in ({"init": "2026101013"}, {"init": "../etc"}, {"init": "2026101012", "max_ft": 999}, {}):
            code, j = self.call("/api/past/fetch", body)
            self.assertEqual(code, 400, body)
        self.assertEqual(self.started, [])

    def test_delete(self):
        self.make("2026101012", manual=True)
        code, j = self.call("/api/past/delete", {"init": "2026101012"})
        self.assertEqual((code, j["deleted"]["grib"]), (200, 2))
        code, j = self.call("/api/past/delete", {"init": "2026101012", "png": True})
        self.assertEqual((code, j["deleted"]["png"]), (200, 3))

    def test_delete_refused_while_running(self):
        self._js = server.job_status
        server.job_status = lambda: {"running": True, "started": 0, "rc": None, "log": []}
        try:
            self.make("2026101012")
            code, j = self.call("/api/past/delete", {"init": "2026101012"})
            self.assertEqual(code, 409)
            self.assertEqual(len(list(self.data.glob("*.bin"))), 2)    # 消えていない
        finally:
            server.job_status = self._js

    def test_foreign_origin_rejected(self):
        code, j = self.call("/api/past/fetch", {"init": "2026101012"}, origin="http://evil.example")
        self.assertEqual(code, 403)
        self.assertEqual(self.started, [])


if __name__ == "__main__":
    unittest.main()
