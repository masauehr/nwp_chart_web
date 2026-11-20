"""等値線ラベルの重点域（LABEL_ZONES）のテスト。"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs

import nwp_charts


def test_region_zone_names_exist():
    """地域の label_zones は、すべて LABEL_ZONES に定義がある。"""
    for name, r in nwp_charts.REGIONS.items():
        for z in r.get("label_zones", ()):
            assert z in nwp_charts.LABEL_ZONES, (name, z)


def test_zone_label_added_when_missing():
    """箱の中を通る等値線に、自動のラベルが無くても1つラベルが付く。"""
    class FakeV:
        zones = [nwp_charts.LABEL_ZONES["east_china_sea"]]
        flon, flat = np.meshgrid(np.linspace(105, 152, 200), np.linspace(8, 46, 200))

        def fine(self, a):
            return a

        def xy(self, ax):
            return self.flon, self.flat

    V = FakeV()
    fig = plt.figure()
    ax = fig.add_axes([0, 0, 1, 1], projection=ccrs.PlateCarree())
    ax.set_extent([105, 152, 8, 46], crs=ccrs.PlateCarree())
    a = V.flat * 0.5   # 緯度方向に気温が変わる場
    n0 = len(ax.texts)
    nwp_charts.lines(ax, V, a, [14, 15, 16], color="red", label_levels=[15], zone_labels=True)
    assert len(ax.texts) > n0
    plt.close(fig)


def test_japan_regions_use_japan_zones():
    """日本周辺・日本域は全国の重点域（JAPAN_ZONES）を使う。"""
    for name in ("japan", "japan3"):
        assert nwp_charts.REGIONS[name]["label_zones"] == nwp_charts.JAPAN_ZONES


# ---------------------------------------------------------------- 地域の設定ファイル
def _copy():
    return {k: dict(v) for k, v in nwp_charts.REGIONS.items()}, dict(nwp_charts.LABEL_ZONES)


def test_region_config_swaps_okinawa():
    """設定で沖縄周辺の名前・範囲を入れ替えられ、キーは変わらない。"""
    import pytest
    regs, zones = _copy()
    cfg = {"label_zones": {"z": [128, 134, 30, 35]},
           "regions": {"okinawa": {"label": "九州周辺", "center": [131, 33], "width_deg": 14,
                                   "bbox": [115, 148, 20, 46], "label_zones": ["z"]}}}
    assert nwp_charts.apply_region_config(cfg, regs, zones) == ["okinawa"]
    assert regs["okinawa"]["label"] == "九州周辺" and regs["okinawa"]["center"] == (131.0, 33.0)
    assert regs["okinawa"]["label_zones"] == ("z",) and zones["z"] == (128.0, 134.0, 30.0, 35.0)
    assert regs["okinawa"]["exclude"] == ("jra55",)   # 書かなかった項目は元のまま


def test_region_config_rejects_bad_input():
    """不正な設定は ValueError で、地域定義は変わらない（地域の追加・範囲外・未知の項目・未定義ゾーン）。"""
    import pytest
    base = {"label": "x", "center": [131, 33], "width_deg": 14, "bbox": [115, 148, 20, 46]}
    bads = [
        {"regions": {"new_region": base}},                                  # 地域は増やせない
        {"regions": {"okinawa": {**base, "bbox": [0, 148, 20, 46]}}},      # データ範囲の外
        {"regions": {"okinawa": {**base, "foo": 1}}},                      # 未知の項目
        {"regions": {"okinawa": {**base, "label_zones": ["nothing"]}}},    # 未定義のゾーン
        {"regions": {"okinawa": {**base, "width_deg": -1}}},               # 幅が不正
        {"regions": {"okinawa3": {**base, "bbox": [115, 148, 20, 46]}}},   # GSM日本域の範囲外
    ]
    for cfg in bads:
        regs, zones = _copy()
        with pytest.raises(ValueError):
            nwp_charts.apply_region_config(cfg, regs, zones)
        assert regs == _copy()[0]


def test_region_config_missing_file_is_noop(tmp_path):
    assert nwp_charts.load_region_config(tmp_path / "none.json") == []


def test_region_config_broken_file_is_ignored(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    assert nwp_charts.load_region_config(p) == []
