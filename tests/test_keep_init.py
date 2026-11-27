"""keep_init.py（初期値の保存＝自動削除の除外）と、自動整理が保存分を残すことの単体テスト（ネットワーク不使用）"""
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import keep_init  # noqa: E402
import server  # noqa: E402
import sync_public  # noqa: E402
import update_latest  # noqa: E402


def make_init(out, model, init, n=2):
    d = out / model / init / "japan"
    d.mkdir(parents=True)
    for i in range(n):
        (d / f"surf_{i * 6:03d}.png").write_bytes(b"x" * 1000)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.out, self.data = t / "output", t / "data"
        self.out.mkdir()
        self.data.mkdir()
        self._o = (keep_init.OUTPUT, keep_init.DATA, update_latest.OUTPUT_DIR, sync_public.ROOT)
        keep_init.OUTPUT, keep_init.DATA, update_latest.OUTPUT_DIR, sync_public.ROOT = self.out, self.data, self.out, t

    def tearDown(self):
        keep_init.OUTPUT, keep_init.DATA, update_latest.OUTPUT_DIR, sync_public.ROOT = self._o
        self.tmp.cleanup()


class TestKeep(Base):
    def test_保存と解除(self):
        make_init(self.out, "gfs", "2026112700")
        self.assertFalse(keep_init.is_pinned("gfs", "2026112700"))
        keep_init.pin("gfs", "2026112700")
        self.assertTrue(keep_init.is_pinned("gfs", "2026112700"))
        self.assertEqual(keep_init.pinned_map(), {"gfs": ["2026112700"]})
        keep_init.pin("gfs", "2026112700", False)
        self.assertFalse(keep_init.is_pinned("gfs", "2026112700"))
        self.assertTrue((self.out / "gfs" / "2026112700" / "japan" / "surf_000.png").exists())   # 解除しても画像は消さない

    def test_不正な指定(self):
        make_init(self.out, "gfs", "2026112700")
        for model, init in (("jra55", "2026112700"), ("xxx", "2026112700"), ("gfs", "../etc"), ("gfs", "20261127"),
                            ("gfs", "2026112712")):       # 最後は画像が無い初期値
            with self.assertRaises(ValueError):
                keep_init.pin(model, init)

    def test_一覧にGRIB2の容量も出る(self):
        make_init(self.out, "msm", "2026112700", 3)
        (self.data / "msm").mkdir()
        (self.data / "msm" / "Z__C_RJTD_2026112700" "0000_MSM_GPV_Rjp_L-pall_FH00-15_grib2.bin").write_bytes(b"y" * 2_000_000)
        (self.data / "msm" / "Z__C_RJTD_2026112703" "0000_MSM_GPV_Rjp_L-pall_FH00-15_grib2.bin").write_bytes(b"y" * 9_000_000)   # 別の初期値
        keep_init.pin("msm", "2026112700")
        rows = keep_init.list_pinned()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["png_count"], rows[0]["grib_mb"]), (3, 2))


class TestAutoPruneKeeps(Base):
    def test_update_latestの3日整理は保存分を残す(self):
        make_init(self.out, "gsm", "2020010100")
        make_init(self.out, "gsm", "2020010200")
        (self.data / "gsm").mkdir()
        for init in ("2020010100", "2020010200"):
            (self.data / "gsm" / f"Z__C_RJTD_{init}0000_GSM_GPV_Rjp_Gll0p1deg_L-pall_FD0000-0023_grib2.bin").write_bytes(b"x")
        keep_init.pin("gsm", "2020010100")
        update_latest.prune_days(["gsm"], 3, self.data)
        self.assertTrue((self.out / "gsm" / "2020010100").is_dir())
        self.assertFalse((self.out / "gsm" / "2020010200").exists())
        left = [p.name for p in (self.data / "gsm").glob("*.bin")]
        self.assertEqual(len(left), 1)
        self.assertIn("2020010100", left[0])                     # 保存した初期値のGRIB2も残る

    def test_sync_publicの整理は保存分を残す(self):
        make_init(self.out, "gfs", "2020010100")
        make_init(self.out, "gfs", "2020010200")
        keep_init.pin("gfs", "2020010100")
        self.assertEqual(sync_public.prune(3), 1)
        self.assertTrue((self.out / "gfs" / "2020010100").is_dir())
        self.assertFalse((self.out / "gfs" / "2020010200").exists())


class TestApi(Base):
    def setUp(self):
        super().setUp()
        make_init(self.out, "aifs", "2026112700")
        h = partial(server.Handler, directory=str(ROOT / "web")) if hasattr(server, "Handler") else None
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), h)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def call(self, path, body=None, origin=None):
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_保存と一覧(self):
        self.assertEqual(self.call("/api/keep")[1]["pinned"], {})
        st, j = self.call("/api/keep", {"model": "aifs", "init": "2026112700", "keep": True})
        self.assertEqual((st, j["pinned_map"]), (200, {"aifs": ["2026112700"]}))
        self.assertEqual(self.call("/api/keep")[1]["pinned"], {"aifs": ["2026112700"]})
        self.assertEqual(self.call("/api/keep", {"model": "aifs", "init": "2026112700", "keep": False})[1]["pinned_map"], {})

    def test_不正は400_他サイトのOriginは403(self):
        self.assertEqual(self.call("/api/keep", {"model": "aifs", "init": "bad"})[0], 400)
        self.assertEqual(self.call("/api/keep", {"model": "aifs", "init": "2026112700"}, origin="http://evil.example")[0], 403)


if __name__ == "__main__":
    unittest.main()
