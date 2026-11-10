"""jra55_source.py・past_jra55.py・JRA-55のモデル登録/地域/図種の制約・サーバーAPI（JRA-55分）の単体テスト（ネットワーク不使用）"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import jra55_source as js  # noqa: E402
import nwp_charts  # noqa: E402
import nwp_data  # noqa: E402
import past_jra55  # noqa: E402
import server  # noqa: E402


def fake_npz(path, with_w=True):
    """小さな格子（lat 90→-90 の北→南）のキャッシュを作る。値は検算しやすい定数。"""
    nlat, nlon, L = 5, 8, len(js.LEVELS)
    lats = np.linspace(90, -90, nlat).astype("float32")
    lons = np.arange(nlon, dtype="float32") * 45
    g = lambda v: np.full((L, nlat, nlon), v, "float32")
    d = dict(lats=lats, lons=lons, levels=np.array(js.LEVELS, dtype="int16"),
             gh=g(5000), t=g(273.15), u=g(10), v=g(-5), r=g(60),
             sp=np.full((nlat, nlon), 101300, "float32"), msl=np.full((nlat, nlon), 101300, "float32"),
             t2=np.full((nlat, nlon), 288.15, "float32"), u10=np.full((nlat, nlon), 3, "float32"), v10=np.full((nlat, nlon), 4, "float32"))
    d["gh"][:, 0, :] = 9999            # 北端（先頭行）だけ値を変えて、緯度の向きの反転を確認できるようにする
    if with_w:
        d["w"] = g(-0.5)
    np.savez_compressed(path, **d)


class TestParse(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(js.parse_valid("1959092612"), "1959092612")

    def test_bad(self):
        for bad in ("19590926", "1959092613", "1957010100", "2024010100", "1959023012", "abcdefghij"):
            with self.assertRaises(ValueError, msg=bad):
                js.parse_valid(bad)

    def test_name_blocks_path_tricks(self):
        for bad in ("../x", "1959-09-26"):
            with self.assertRaises(ValueError):
                js.valid_name(bad)

    def test_times_from(self):
        t = js.times_from("1959092612", 1)
        self.assertEqual(t, ["1959092612", "1959092618", "1959092700", "1959092706"])
        self.assertEqual(len(js.times_from("1959092600", 3)), 12)
        self.assertEqual(js.times_from("2023123118", 2), ["2023123118"])     # 範囲(2023年)の終わりで打ち切る


class TestPlan(unittest.TestCase):
    def test_groups_by_month_and_year(self):
        ts = ["1959093018", "1959100100"]                  # 月をまたぐ
        tasks = js.plan(ts)
        iso = [t for t in tasks if t[0] == "iso"]
        surf = [t for t in tasks if t[0] == "surf"]
        self.assertEqual(len(iso), 6 * 2)                  # 6変数 × 2か月
        self.assertEqual(len(surf), 5)                     # 5変数 × 1年
        self.assertTrue(all(t[5] == js.LEVELS for t in iso))
        self.assertIn("surf/PRES/PRES_sfc_1959.nc", [t[1] for t in surf])
        self.assertIn("VVEL/1959/VVEL_195909.nc", [t[1] for t in iso])


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_units_and_orientation(self):
        fake_npz(self.d / "1959092612.npz")
        F = js.load("1959092612", self.d)
        self.assertTrue(np.all(np.diff(F["lats"]) > 0))                    # 緯度は昇順（南→北）
        self.assertEqual(F["p"][500]["gh"][-1, 0], 9999)                   # 元の先頭行(北端)が末尾(北)へ
        self.assertAlmostEqual(float(F["p"][500]["t"][0, 0]), 0.0, places=3)   # K→℃
        self.assertAlmostEqual(float(F["sp"][0, 0]), 1013.0, places=2)         # Pa→hPa
        self.assertAlmostEqual(float(F["t2"][0, 0]), 15.0, places=3)
        self.assertAlmostEqual(float(F["p"][300]["w"][0, 0]), -18.0, places=3)  # -0.5 Pa/s → hPa/h
        self.assertTrue(F["no_cloud"])
        self.assertIsNone(F["rr"])
        self.assertEqual(sorted(F["p"]), sorted(js.LEVELS))

    def test_missing_w_is_zero(self):
        fake_npz(self.d / "1959092612.npz", with_w=False)
        F = js.load("1959092612", self.d)
        self.assertEqual(float(np.abs(F["p"][700]["w"]).max()), 0.0)

    def test_load_none_when_missing(self):
        self.assertIsNone(js.load("1959092612", self.d))

    def test_list_and_delete(self):
        fake_npz(self.d / "1959092612.npz")
        fake_npz(self.d / "1959092618.npz")
        (self.d / "notes.txt").write_text("x")
        self.assertEqual([r["valid"] for r in js.list_cached(self.d)], ["1959092618", "1959092612"])
        self.assertEqual(js.delete_cache("1959092612", self.d), 1)
        self.assertEqual(js.delete_cache("1959092612", self.d), 0)
        self.assertTrue(js.have("1959092618", self.d))


class TestSeries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_and_delete_series(self):
        for start, n in (("1959092600", 3), ("1959092700", 1)):
            d = js.series_dir(start, self.root)
            d.mkdir()
            for k in range(n):
                fake_npz(d / f"{js.times_from(start, 1)[k]}.npz")
        rows = js.list_series(self.root)
        self.assertEqual([(r["series"], r["frames"]) for r in rows], [("1959092700", 1), ("1959092600", 3)])
        self.assertEqual(js.delete_series("1959092600", self.root), 3)
        self.assertFalse(js.series_dir("1959092600", self.root).exists())       # 空になったフォルダも消える
        self.assertEqual(js.delete_series("1959092600", self.root), 0)
        with self.assertRaises(ValueError):
            js.delete_series("../x", self.root)

    def test_migrate_flat(self):
        fake_npz(self.root / "1959092612.npz")                    # 旧形式
        fake_npz(self.root / "1959092618.npz")
        self.assertEqual(js.migrate_flat(self.root), 2)
        self.assertTrue((self.root / "1959092612" / "1959092612.npz").exists())
        self.assertEqual(js.migrate_flat(self.root), 0)           # 2回目は何もしない
        self.assertEqual([r["series"] for r in js.list_series(self.root)], ["1959092618", "1959092612"])


class TestRegistry(unittest.TestCase):
    def test_model(self):
        m = nwp_data.MODELS["jra55"]
        self.assertTrue(m["local_only"])                    # 公開しない
        self.assertNotIn("jra55", nwp_data.public_models())
        self.assertNotIn("jra55", nwp_data.auto_models())   # 自動更新の対象外
        self.assertIn("gsm", nwp_data.auto_models())

    def test_regions(self):
        self.assertEqual(sorted(nwp_charts.regions_for("jra55")), ["asia", "japan"])    # アジア・日本のみ
        self.assertIn("okinawa", nwp_charts.regions_for("ecmwf"))                       # 他モデルは従来どおり
        self.assertNotIn("japan3", nwp_charts.regions_for("jra55"))

    def test_tenki_needs_cloud(self):
        self.assertTrue(nwp_charts.CHARTS["tenki"].get("cloud"))
        self.assertFalse(nwp_charts.CHARTS["surf"].get("cloud"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.data, self.out = t / "data", t / "output" / "jra55"
        self.data.mkdir(parents=True)
        self.out.mkdir(parents=True)
        self._o = (js.DATA, past_jra55.OUTPUT, past_jra55.refresh_manifest)
        js.DATA, past_jra55.OUTPUT = self.data, self.out
        self.refreshed = []
        past_jra55.refresh_manifest = lambda: self.refreshed.append(1)

    def tearDown(self):
        js.DATA, past_jra55.OUTPUT, past_jra55.refresh_manifest = self._o
        self.tmp.cleanup()

    def make(self, valid, png=3, frames=1):
        """系列（開始時刻=valid）のキャッシュを frames コマ分と、画像 png 枚を作る。"""
        sd = self.data / valid
        sd.mkdir(parents=True, exist_ok=True)
        for k in range(frames):
            t = js.times_from(valid, 1)[k]
            fake_npz(sd / f"{t}.npz")
        d = self.out / valid / "asia"
        d.mkdir(parents=True, exist_ok=True)
        for i in range(png):
            (d / f"surf_{i:03d}.png").write_bytes(b"p" * 500)


class TestPast(Base):
    def test_list_rows(self):
        self.make("1959092612", frames=4)
        self.make("1959092618", png=0)
        rows = past_jra55.list_rows()
        self.assertEqual([r["init"] for r in rows], ["1959092618", "1959092612"])
        r = {x["init"]: x for x in rows}["1959092612"]
        self.assertEqual((r["png_count"], r["has_data"], r["frames"]), (3, True, 4))
        self.assertFalse({x["init"]: x for x in rows}["1959092618"]["png_count"])

    def test_delete_data_only_then_all(self):
        self.make("1959092612", frames=2)
        self.assertEqual(past_jra55.delete("1959092612"), {"data": 2, "png": 0})
        self.assertTrue((self.out / "1959092612" / "asia" / "surf_000.png").exists())     # 画像は残る
        self.assertEqual(self.refreshed, [])
        self.assertEqual(past_jra55.delete("1959092612", with_png=True), {"data": 0, "png": 3})
        self.assertFalse((self.out / "1959092612").exists())
        self.assertEqual(self.refreshed, [1])

    def test_fetch_rejects_bad_days_and_time(self):
        with self.assertRaises(ValueError):
            past_jra55.fetch("1959092612", days=4)       # 選択肢にない日数
        with self.assertRaises(ValueError):
            past_jra55.fetch("1959092613", days=1)


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

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     method="GET" if body is None else "POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_list_has_jra55(self):
        self.make("1959092612")
        code, j = self.call("/api/past/list")
        self.assertEqual(code, 200)
        self.assertEqual(j["jra55"][0]["init"], "1959092612")
        self.assertEqual(j["days_choices"], [1, 2, 3, 5, 7, 10])

    def test_fetch_starts_job(self):
        code, j = self.call("/api/past/fetch", {"model": "jra55", "init": "1959092612", "days": 2})
        self.assertEqual(code, 200)
        self.assertEqual(self.started, [("past_jra55.py", ("fetch", "1959092612", "--days", "2"))])

    def test_fetch_rejects_bad_input(self):
        for body in ({"model": "jra55", "init": "2024010100"}, {"model": "jra55", "init": "1959092612", "days": 9},
                     {"model": "jra55", "init": "../x"}, {"model": "jra55"}):
            code, _ = self.call("/api/past/fetch", body)
            self.assertEqual(code, 400, body)
        self.assertEqual(self.started, [])

    def test_delete(self):
        self.make("1959092612")
        code, j = self.call("/api/past/delete", {"model": "jra55", "init": "1959092612"})
        self.assertEqual((code, j["deleted"]["grib"]), (200, 1))
        code, j = self.call("/api/past/delete", {"model": "jra55", "init": "1959092612", "png": True})
        self.assertEqual((code, j["deleted"]["png"]), (200, 3))

    def test_gsm_default_unchanged(self):
        code, _ = self.call("/api/past/fetch", {"init": "2026101012", "max_ft": 24})     # model省略=GSM
        self.assertEqual(code, 200)
        self.assertEqual(self.started[0][0], "past_gsm.py")


if __name__ == "__main__":
    unittest.main()
