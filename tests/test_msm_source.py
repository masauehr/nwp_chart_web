"""msm_source.py（MSM の取得・読み込み）と past_msm.py の単体テスト（ネットワーク・RISH不使用）"""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import msm_source as ms  # noqa: E402
import past_msm  # noqa: E402
import nwp_data  # noqa: E402
import nwp_charts  # noqa: E402


def names_for(init, hours):
    """00/12UTC 風（78h）か、それ以外（39h）かのファイル名一覧を作る。"""
    pall = ["00-15", "18-33", "36-39"] + (["42-51", "54-78"] if hours == 78 else [])
    surf = ["00-15", "16-33", "34-39"] + (["40-51", "52-78"] if hours == 78 else [])
    return ([f"Z__C_RJTD_{init}0000_MSM_GPV_Rjp_L-pall_FH{r}_grib2.bin" for r in pall]
            + [f"Z__C_RJTD_{init}0000_MSM_GPV_Rjp_Lsurf_FH{r}_grib2.bin" for r in surf])


class TestNames(unittest.TestCase):
    def test_file_range(self):
        n = "Z__C_RJTD_2026112400" + "0000_MSM_GPV_Rjp_L-pall_FH18-33_grib2.bin"
        self.assertEqual(ms.file_range(n), ("2026112400", "L-pall", 18, 33))
        self.assertIsNone(ms.file_range("Z__C_RJTD_2026112400" + "0000_GSM_GPV_Rgl_FD0006_grib2.bin"))

    def test_pick_区間をまたぐFT(self):
        names = names_for("2026112400", 78)
        self.assertTrue(ms.pick(names, "2026112400", "L-pall", 15).endswith("FH00-15_grib2.bin"))
        self.assertTrue(ms.pick(names, "2026112400", "L-pall", 18).endswith("FH18-33_grib2.bin"))
        self.assertTrue(ms.pick(names, "2026112400", "Lsurf", 16).endswith("FH16-33_grib2.bin"))
        self.assertTrue(ms.pick(names, "2026112400", "L-pall", 78).endswith("FH54-78_grib2.bin"))
        self.assertIsNone(ms.pick(names, "2026112400", "L-pall", 81))
        self.assertIsNone(ms.pick(names, "2026112500", "L-pall", 0))

    def test_最大FT(self):
        for h, ft in ((0, 78), (12, 78), (18, 39), (3, 39), (21, 39)):
            self.assertEqual(ms.max_ft_of(datetime(2026, 11, 24, h, tzinfo=timezone.utc)), ft)
            self.assertEqual(nwp_data.max_step("msm", datetime(2026, 11, 24, h, tzinfo=timezone.utc)), ft)


class TestRemote(unittest.TestCase):
    def test_remote_status(self):
        init = datetime(2026, 11, 24, 0, tzinfo=timezone.utc)
        names = names_for("2026112400", 78)
        self.assertTrue(ms.remote_status(init, 72, 3, names)["complete"])
        part = [n for n in names if "FH54-78" not in n and "FH52-78" not in n]       # 公開の途中
        st = ms.remote_status(init, 72, 3, part)
        self.assertFalse(st["complete"])
        self.assertIn(72, st["missing"])
        self.assertTrue(ms.remote_status(init, 39, 3, part)["complete"])

    def test_find_latest_18Zは39hに丸める(self):
        day = datetime(2026, 11, 24, tzinfo=timezone.utc)
        listing = names_for("2026112412", 78) + names_for("2026112418", 39)
        orig_list, orig_now = ms.list_day, ms.datetime
        ms.list_day = lambda d: listing if d.day == 24 else []

        class FakeDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 24, 23, 0, tzinfo=tz)
        ms.datetime = FakeDT
        try:
            self.assertEqual(ms.find_latest_complete(72, 3, 0, hours=[0, 12, 18]), datetime(2026, 11, 24, 18, tzinfo=timezone.utc))
            self.assertEqual(ms.find_latest_complete(72, 3, 0, hours=[0, 12]), datetime(2026, 11, 24, 12, tzinfo=timezone.utc))
        finally:
            ms.list_day, ms.datetime = orig_list, orig_now


class TestRegrid(unittest.TestCase):
    def test_等圧面を地上の格子へそろえる(self):
        import numpy as np
        lat_s, lon_s = np.linspace(22.4, 47.6, 505), np.linspace(120, 150, 481)
        lat_p, lon_p = np.linspace(22.4, 47.6, 253), np.linspace(120, 150, 241)
        z = np.tile(np.linspace(0, 1, 241, dtype=np.float32), (253, 1))
        surf = {"msl": np.full((505, 481), 101325.0, np.float32), "sp": np.full((505, 481), 101325.0, np.float32),
                "u10": np.zeros((505, 481), np.float32), "v10": np.zeros((505, 481), np.float32),
                "t2": np.full((505, 481), 273.15, np.float32), "p": {}, "lats": lat_s, "lons": lon_s}
        pall = {"p": {500: {k: z.copy() for k in ("gh", "t", "u", "v")}}, "lats": lat_p, "lons": lon_p}
        F = ms._finish([pall, surf])
        self.assertEqual(F["p"][500]["gh"].shape, (505, 481))
        self.assertEqual(len(F["lats"]), 505)
        self.assertAlmostEqual(float(F["p"][500]["gh"][0, -1]), 1.0, places=5)       # 端点が保たれる
        self.assertAlmostEqual(float(F["p"][500]["gh"][0, 1]), 1 / 480, places=5)    # 線形補間
        self.assertEqual(F["p"][500]["r"].shape, (505, 481))                         # 相対湿度が無い面は50%で埋める


class TestRegionsAndPast(unittest.TestCase):
    def test_MSMの地域は日本域のみ(self):
        self.assertEqual(nwp_charts.regions_for("msm"), ["japan3", "okinawa3"])
        self.assertTrue(nwp_data.MODELS["msm"]["local_only"])
        self.assertEqual(nwp_data.default_interval("msm"), 3)

    def test_past_parse_init(self):
        self.assertEqual(past_msm.parse_init("2026101003"), "2026101003")
        with self.assertRaises(ValueError):
            past_msm.parse_init("2026101004")          # 3時間毎でない
        with self.assertRaises(ValueError):
            past_msm.parse_init("2999010100")          # 未来

    def test_past_delete(self):
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            data, out = t / "data", t / "out"
            (out / "2026101012" / "japan3").mkdir(parents=True)
            data.mkdir()
            (data / "Z__C_RJTD_2026101012" "0000_MSM_GPV_Rjp_L-pall_FH00-15_grib2.bin").write_bytes(b"x")
            (data / "Z__C_RJTD_2026101100" "0000_MSM_GPV_Rjp_L-pall_FH00-15_grib2.bin").write_bytes(b"x")
            (out / "2026101012" / "japan3" / "surf_000.png").write_bytes(b"x")
            (out / "2026101012" / ".keep").touch()
            od, oo = past_msm.DATA, past_msm.OUTPUT
            past_msm.DATA, past_msm.OUTPUT = data, out
            try:
                r = past_msm.delete("2026101012", with_png=True, refresh=False)
                self.assertEqual(r, {"grib": 1, "png": 1})
                self.assertEqual(len(list(data.glob("*.bin"))), 1)      # 別の初期値は残る
                self.assertFalse((out / "2026101012").exists())
            finally:
                past_msm.DATA, past_msm.OUTPUT = od, oo


if __name__ == "__main__":
    unittest.main()
