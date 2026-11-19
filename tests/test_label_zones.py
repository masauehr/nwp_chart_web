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
