#!/usr/bin/env python
# coding: utf-8
"""ECMWF / GFS（0.25°）のGRIB2から気象庁ビューア風の天気図PNGを描画する。

gsm_chart_web の gsm_charts.py をコピーして多モデル用に調整したもの（共通部品化しない方針）。
図種: surf / tenki / z500 / jet300 / t500 / t850 / t700 / t925 / t975 / ept850（975hPaはGFSのみ）
地域: japan（日本周辺・ランベルト） / okinawa（沖縄周辺・正距円筒） / asia（東アジア広域）
  GSMだけ japan3 / okinawa3（日本域0.125°・3時間毎。src="rjp"）
"""
import os
import sys

_proj = os.path.join(sys.prefix, "share", "proj")
if os.path.isdir(_proj):
    os.environ.setdefault("PROJ_LIB", _proj)

# 並列実行時のスレッド競合（sys時間の暴走）を避ける。numpy を import する前に設定
for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_k, "1")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from datetime import timedelta
from matplotlib.collections import LineCollection
from scipy.ndimage import zoom, maximum_filter, minimum_filter

PC = ccrs.PlateCarree()
KT = 1.94384  # m/s → kt

# 画像サイズ（サンプルと同じ 950×760。下部 42px はキャプション帯）
FIG_W, FIG_H, DPI = 9.5, 7.6, 100
MAP_RECT = [0.002, 42 / 760, 0.996, 716 / 760]
MAP_ASPECT = (0.996 * 9.5) / (716 / 100)  # 地図部分の縦横比（幅/高さ）

# ---------------------------------------------------------------- 地域定義
# center: 投影中心(lon,lat)  width_km: 地図幅  bbox: データ切り出し範囲(lon0,lon1,lat0,lat1)
REGIONS = {
    "japan": dict(label="日本周辺", kind="lcc", center=(133.0, 36.0), width_km=4400,
                  bbox=(95, 180, 5, 68), barb_n=20, coast="10m", zoom=2),
    "okinawa": dict(label="沖縄周辺", kind="pc", center=(128.0, 27.0), width_deg=24.0,
                    bbox=(105, 152, 8, 46), barb_n=16, coast="10m", zoom=3),
    "asia": dict(label="東アジア広域", kind="lcc", center=(115.0, 33.0), width_km=8600,
                 bbox=(55, 180, -8, 80), barb_n=24, coast="50m", zoom=1),
    # GSM 日本域 0.125°（Rjp, 3時間毎）。データ範囲は 120-150E, 20-50N。**GSM（ローカル専用）だけ**が持つ地域
    "japan3": dict(label="日本域（0.125°・3時間毎）", kind="lcc", center=(135.0, 36.0), width_km=2700,
                   bbox=(120, 150, 20, 50), barb_n=20, coast="10m", zoom=1, src="rjp", models=("gsm",)),
    "okinawa3": dict(label="南西域（0.125°・3時間毎）", kind="pc", center=(133.0, 30.0), width_deg=26.0,
                     bbox=(120, 150, 20, 50), barb_n=16, coast="10m", zoom=1, src="rjp", models=("gsm",)),
}


def regions_for(model):
    """そのモデルで作れる地域（地域の models 指定があればそのモデルだけ。無ければ全モデル共通）。"""
    return [k for k, v in REGIONS.items() if "models" not in v or model in v["models"]]


def make_projection(region):
    """地域の投影と、地図が画像いっぱいに収まる表示範囲（投影座標）を返す。"""
    r = REGIONS[region]
    lon0, lat0 = r["center"]
    if r["kind"] == "lcc":
        proj = ccrs.LambertConformal(central_longitude=lon0, central_latitude=lat0,
                                     standard_parallels=(30, 60))
        cx, cy = proj.transform_point(lon0, lat0, PC)
        w = r["width_km"] * 1000.0
        h = w / MAP_ASPECT
    else:
        proj = ccrs.PlateCarree()
        cx, cy = lon0, lat0
        w = r["width_deg"]
        h = w / MAP_ASPECT
    return proj, (cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2)


# ---------------------------------------------------------------- データ前処理
class View:
    """全球場を地域の切り出し範囲へ切り出し、等値線用に補間して返す。"""

    def __init__(self, F, region):
        r = REGIONS[region]
        lon0, lon1, lat0, lat1 = r["bbox"]
        ix = np.where((F["lons"] >= lon0) & (F["lons"] <= lon1))[0]
        iy = np.where((F["lats"] >= lat0) & (F["lats"] <= lat1))[0]
        self.sx, self.sy = slice(ix[0], ix[-1] + 1), slice(iy[0], iy[-1] + 1)
        self.lons, self.lats = F["lons"][self.sx], F["lats"][self.sy]
        self.z = r["zoom"]
        self.barb_n = r["barb_n"]
        nx, ny = len(self.lons), len(self.lats)
        nfx, nfy = (nx - 1) * self.z + 1, (ny - 1) * self.z + 1
        self._zf = (nfy / ny, nfx / nx)  # 出力形状を明示（端点が揃う）
        fx = np.linspace(self.lons[0], self.lons[-1], nfx)
        fy = np.linspace(self.lats[0], self.lats[-1], nfy)
        self.flon, self.flat = np.meshgrid(fx, fy)
        self.rlon, self.rlat = np.meshgrid(self.lons, self.lats)
        self.dx = float(self.lons[1] - self.lons[0])  # 元格子の間隔[度]（0.5 or 0.125）
        self.rmask = self.fmask = None  # 地面下マスク（set_level で設定）

    def set_level(self, F, level):
        """等圧面の図で、地表気圧が level より低い（=地面の下）領域をマスクする。None で解除。"""
        if level is None:
            self.rmask = self.fmask = None
            return
        under = (self.raw(F["sp"]) < level).astype(np.float32)
        self.rmask = under > 0.5
        self.fmask = zoom(under, self._zf, order=1) > 0.5

    def raw(self, a):
        """切り出しのみ（元の0.5°格子）"""
        return a[self.sy, self.sx]

    def fine(self, a, cropped=False):
        """切り出して3次補間で細かくした場（等値線・塗りつぶし用）。cropped=True なら切り出し済み"""
        z = zoom(a if cropped else self.raw(a), self._zf, order=3)
        return np.ma.masked_where(self.fmask, z) if self.fmask is not None else z


def dewpoint(t_c, rh):
    """気温[℃]・相対湿度[%] → 露点[℃]（Magnus式）"""
    rh = np.clip(rh, 1.0, 100.0)
    a, b = 17.62, 243.12
    g = np.log(rh / 100.0) + a * t_c / (b + t_c)
    return b * g / (a - g)


def vorticity(u, v, lats, lons):
    """相対渦度 [1e-6 /s]（球面格子の中心差分）"""
    R = 6.371e6
    la = np.deg2rad(lats)[:, None]
    dlam = np.deg2rad(lons[1] - lons[0])
    dphi = np.deg2rad(lats[1] - lats[0])
    cosp = np.cos(la)
    dvdx = np.gradient(v, axis=1) / (R * cosp * dlam)
    ducos = np.gradient(u * cosp, axis=0) / (R * cosp * dphi)
    return (dvdx - ducos) * 1e6


_THW_TABLES = {}


def _theta_w_to_tup(level_up):
    """湿潤断熱線（θw）上の level_up[hPa] の気温[K]を引く対応表（SSI用）。level_up ごとに一度だけ作る。"""
    if level_up not in _THW_TABLES:
        import metpy.calc as mpcalc
        from metpy.units import units
        thw = np.arange(240.0, 321.0, 1.0)
        tup = []
        for t in thw:
            r = mpcalc.moist_lapse(np.array([1000.0, float(level_up)]) * units.hPa, t * units.K)
            tup.append(float(r[-1].to("K").m))
        _THW_TABLES[level_up] = (thw, np.array(tup))
    return _THW_TABLES[level_up]


def ssi(F, lv_low=850, lv_up=500):
    """ショワルター安定指数 SSI = T(lv_up) − lv_low から持ち上げた気塊の気温。負で不安定。"""
    import metpy.calc as mpcalc
    from metpy.units import units
    d = F["p"][lv_low]
    td = np.minimum(dewpoint(d["t"], d["r"]), d["t"])
    thw = mpcalc.wet_bulb_potential_temperature(
        lv_low * units.hPa, d["t"] * units.degC, td * units.degC).to("K").m
    tp_up = np.interp(thw, *_theta_w_to_tup(lv_up))
    return (F["p"][lv_up]["t"] + 273.15) - tp_up


def ept(F, lv=850):
    """相当温位[K]"""
    import metpy.calc as mpcalc
    from metpy.units import units
    d = F["p"][lv]
    td = np.minimum(dewpoint(d["t"], d["r"]), d["t"])
    return mpcalc.equivalent_potential_temperature(
        lv * units.hPa, d["t"] * units.degC, td * units.degC).to("K").m


# ---------------------------------------------------------------- 描画部品
def lines(ax, V, a, levels, major=None, color="k", lw=0.8, lw_major=1.8, ls="-",
          label_levels=None, fmt="%d", fs=8):
    """細線＋太線(major)の等値線。label_levels の線にはラベルを付ける。"""
    lv = np.array(levels, dtype=float)
    z = V.fine(a)
    if lv.min() > np.nanmax(z) or lv.max() < np.nanmin(z):
        return
    cs = ax.contour(V.flon, V.flat, z, levels=lv, colors=color, linewidths=lw,
                    linestyles=ls, transform=PC, zorder=3)
    if major is not None and len(major):
        m = [x for x in major if np.nanmin(z) <= x <= np.nanmax(z)]
        if m:
            ax.contour(V.flon, V.flat, z, levels=m, colors=color, linewidths=lw_major,
                       linestyles=ls, transform=PC, zorder=3)
    ll = label_levels if label_levels is not None else major
    if ll:
        ll = [x for x in ll if np.nanmin(z) <= x <= np.nanmax(z)]
        if ll:
            try:
                ax.clabel(cs, levels=ll, fmt=fmt, fontsize=fs, inline=True, inline_spacing=2)
            except Exception:
                pass


def hatch(ax, V, a, levels, hatches, color, zorder=2):
    """ハッチ（斜線・点）塗り。levels は境界、hatches は各区間のパターン。"""
    z = V.fine(a)
    with matplotlib.rc_context({"hatch.color": color, "hatch.linewidth": 0.8}):
        ax.contourf(V.flon, V.flat, z, levels=levels, colors="none", hatches=hatches,
                    transform=PC, zorder=zorder, extend="neither")


def fill(ax, V, a, levels, colors, zorder=1, extend="neither"):
    z = V.fine(a)
    ax.contourf(V.flon, V.flat, z, levels=levels, colors=colors, transform=PC,
                zorder=zorder, extend=extend)


def barbs(ax, V, u, v, color, lw=0.7, length=5.2):
    """風矢羽（kt）。regrid_shape で間引く。"""
    uu, vv = V.raw(u) * KT, V.raw(v) * KT
    if V.rmask is not None:
        uu, vv = np.ma.masked_where(V.rmask, uu), np.ma.masked_where(V.rmask, vv)
    ax.barbs(V.rlon, V.rlat, uu, vv, transform=PC, regrid_shape=V.barb_n,
             length=length, linewidth=lw, color=color, zorder=5)


def extrema(ax, V, a, kind, win, color="k", fs=11, dec=0):
    """高気圧(H)・低気圧(L)のスタンプ。近接する重複は強い方だけ残す。
    win は 0.5°格子での格子点数。格子間隔が違えば度数が同じになるよう換算する。"""
    win = max(3, int(round(win * 0.5 / V.dx)))
    z = V.raw(a)
    if V.dx < 0.4:  # 細かい格子では小さな凹凸が極値になるため、3度程度に平滑化してから探す
        from scipy.ndimage import uniform_filter
        z = uniform_filter(z, size=max(3, int(round(1.5 / V.dx))), mode="nearest")
    filt = maximum_filter if kind == "H" else minimum_filter
    ys, xs = np.where(filt(z, size=win, mode="nearest") == z)
    mg = max(3, int(round(1.5 / V.dx)))  # 切り出し端から1.5度は除く
    cand = sorted(((z[j, i], i, j) for j, i in zip(ys, xs)
                   if mg < i < len(V.lons) - mg - 1 and mg < j < len(V.lats) - mg - 1),
                  reverse=(kind == "H"))
    ex = ax.get_extent()
    mx = (ex[1] - ex[0]) * 0.02  # 画面端から2%は除外
    my = (ex[3] - ex[2]) * 0.02
    chosen = []
    for val, i, j in cand:
        if any((i - ci) ** 2 + (j - cj) ** 2 < win ** 2 for _, ci, cj in chosen):
            continue
        px, py = ax.projection.transform_point(V.lons[i], V.lats[j], PC)
        if not (ex[0] + mx < px < ex[1] - mx and ex[2] + my < py < ex[3] - my):
            continue
        chosen.append((val, i, j))
        lo, la = V.lons[i], V.lats[j]
        ax.text(lo, la, kind, transform=PC, ha="center", va="center", fontsize=fs + 3,
                fontweight="bold", color=color, zorder=8)
        ax.text(lo, la - 0.9, f"{val:.{dec}f}", transform=PC, ha="center", va="top",
                fontsize=fs - 3, color=color, zorder=8)


def legend_box(ax, boxes, labels, center=False):
    """右下の凡例。boxes=[(facecolor, hatch, hatchcolor)...]、labels は境界値の文字列（len(boxes)+1）。"""
    ia = ax.inset_axes([0.724, 0.008, 0.272, 0.078], transform=ax.transAxes, zorder=20)
    ia.set_xlim(0, 1)
    ia.set_ylim(0, 1)
    ia.set_xticks([])
    ia.set_yticks([])
    for s in ia.spines.values():
        s.set_linewidth(1.0)
    ia.set_facecolor("white")
    n = len(boxes)
    x0, x1 = 0.04, 0.96
    w = (x1 - x0) / n
    for k, (fc, ht, hc) in enumerate(boxes):
        # ハッチ色は edgecolor で決まるため、ハッチ用と枠線用の2枚を重ねる
        ia.add_patch(plt.Rectangle((x0 + k * w, 0.52), w, 0.36, facecolor=fc,
                                   edgecolor=hc or "k", linewidth=0, hatch=ht))
        ia.add_patch(plt.Rectangle((x0 + k * w, 0.52), w, 0.36, fill=False,
                                   edgecolor="k", linewidth=0.6))
    for k, lab in enumerate(labels):
        # center=True: 各ボックスの中央に区分名を書く（日本語は和文フォントへフォールバック）
        ia.text(x0 + (k + 0.5 if center else k) * w, 0.30, lab, ha="center", va="center", fontsize=7,
                family=["Hiragino Sans", "Arial Unicode MS", "DejaVu Sans"])


# ---------------------------------------------------------------- 各図の描画
def chart_surf(ax, V, F, ctx):
    P = F["msl"]
    V.set_level(F, None)
    boxes = labels = None
    rr = F.get("rr")
    if rr is not None:
        cols = ["#c4ecff", "#9be89b", "#3fc43f", "#ffe84a", "#ff9f1c", "#ff2a1a"]
        fill(ax, V, rr, [0.1, 1, 2, 5, 10, 20, 50], cols, extend="max")
        boxes = [(c, None, None) for c in cols]
        labels = ["0.1", "1", "2", "5", "10", "20", "50"]
        ctx["title"] = ("RR1" if F["rr_h"] == 1 else f"RR{F['rr_h']}h") + ",PseaSURF,WindSURF"
    else:
        ctx["title"] = "PseaSURF,WindSURF"
    lines(ax, V, P, np.arange(900, 1060, 4), major=list(range(900, 1060, 20)),
          fmt="%d", fs=8)
    extrema(ax, V, P, "H", 13, color="#1030c0")
    extrema(ax, V, P, "L", 13, color="#c01010")
    barbs(ax, V, F["u10"], F["v10"], "red")
    if boxes:
        legend_box(ax, boxes, labels)


def chart_tenki(ax, V, F, ctx):
    """天気（雲量・降水の色分け）＋ 海面気圧 ＋ SSI(700-850) ＋ 地上風"""
    V.set_level(F, None)
    # 全雲量: 晴(白) / 薄曇(淡黄) / 曇(灰)。降水があれば緑
    fill(ax, V, F["tcc"], [-1, 30, 70, 101], ["#ffffff", "#fff3b0", "#d9d9d9"])
    ax.contour(V.flon, V.flat, V.fine(F["tcc"]), levels=[30, 70], colors="#e0a030",
               linewidths=0.6, transform=PC, zorder=2)
    if F.get("rr") is not None:
        thr = 0.5 if F["rr_h"] == 1 else 0.2   # 1時間降水0.5mm / 6時間平均0.2mm/h 以上を雨とみなす
        ax.contourf(V.flon, V.flat, V.fine(F["rr"]), levels=[thr, 1e4], colors=["#22cc22"],
                    transform=PC, zorder=2)
    RD = "#e03030"
    if 850 in F["p"] and 700 in F["p"]:
        s = ssi(F, 850, 700)
        hatch(ax, V, s, [-100, 0], ["oo"], RD)
        ax.contour(V.flon, V.flat, V.fine(s), levels=[-3, 0], colors=RD, linewidths=0.7,
                   linestyles="--", transform=PC, zorder=3)
    lines(ax, V, F["msl"], np.arange(900, 1060, 4), major=list(range(900, 1060, 20)), fmt="%d", fs=8)
    extrema(ax, V, F["msl"], "H", 13, color="#1030c0")
    extrema(ax, V, F["msl"], "L", 13, color="#c01010")
    barbs(ax, V, F["u10"], F["v10"], "red")
    ctx["title"] = "TENKI,PseaSURF,SSI(700-850),WindSURF"
    legend_box(ax, [("#ffffff", None, None), ("#fff3b0", None, None), ("#d9d9d9", None, None),
                    ("#22cc22", None, None), ("white", "oo", RD)],
               ["晴", "薄曇", "曇", "雨", "不安定"], center=True)


def chart_z500(ax, V, F, ctx):
    d = F["p"][500]
    V.set_level(F, 500)
    zeta = vorticity(d["u"], d["v"], F["lats"], F["lons"])
    ctx["title"] = "Z500,Vor500"
    vf = V.fine(zeta)
    ax.contour(V.flon, V.flat, vf, levels=np.arange(-200, 900, 40), colors="#e8890c",
               linewidths=0.8, transform=PC, zorder=2)
    with matplotlib.rc_context({"hatch.color": "#e8890c", "hatch.linewidth": 0.9}):
        ax.contourf(V.flon, V.flat, vf, levels=[40, 1e4], colors="none", hatches=["////"],
                    transform=PC, zorder=2)
    lines(ax, V, d["gh"], np.arange(4800, 6200, 60), major=list(range(4800, 6200, 300)),
          fmt="%d", fs=8)
    extrema(ax, V, d["gh"], "L", 11, color="#c01010")
    legend_box(ax, [("white", None, None)] * 4 + [("white", "////", "#e8890c")] * 5,
               ["-200", "-120", "-80", "-40", "0", "40", "120", "200", "400", "900"])


def chart_jet300(ax, V, F, ctx):
    d = F["p"][300]
    V.set_level(F, 300)
    spd = np.hypot(d["u"], d["v"]) * KT
    lv = [60, 80, 100, 120, 140, 160, 180, 200, 1000]
    cols = ["#fffbd0", "#fff6a0", "#fff070", "#ffe940", "#ffdd1a", "#ffd000", "#ffc400", "#ffb800"]
    fill(ax, V, spd, lv, cols)
    lines(ax, V, d["t"], np.arange(-90, 0, 3), color="red", lw=0.9, label_levels=list(range(-90, 0, 9)),
          fmt="%d", fs=8)
    lines(ax, V, d["gh"], np.arange(8400, 10000, 120), major=list(range(8400, 10000, 600)),
          fmt="%d", fs=8)
    barbs(ax, V, d["u"], d["v"], "#1a237e")
    ctx["title"] = "ISTAC300,Z300,T300,Wind300"
    legend_box(ax, [(c, None, None) for c in cols[:8]],
               ["60", "80", "100", "120", "140", "160", "180", "200", ""])


def _chart_tdep(ax, V, F, ctx, lv):
    """850/925hPa: 気温・湿数・風"""
    d = F["p"][lv]
    V.set_level(F, lv)
    ttd = np.maximum(d["t"] - dewpoint(d["t"], d["r"]), 0.0)  # 飽和付近の-1e-6程度の負値を0に（等値線の穴を防ぐ）
    BL = "#3a6fd8"
    hatch(ax, V, ttd, [-0.1, 1.5, 3], ["\\\\\\\\\\\\", "\\\\\\\\"], BL)
    hatch(ax, V, ttd, [3, 6], ["////"], "#8a8a8a")
    ax.contour(V.flon, V.flat, V.fine(ttd), levels=[3], colors=BL, linewidths=0.8,
               linestyles="--", transform=PC, zorder=3)
    lines(ax, V, d["t"], np.arange(-60, 45, 3), major=None, color="red", lw=1.1,
          ls="--", label_levels=list(range(-60, 45, 3)), fmt="%d", fs=8)
    barbs(ax, V, d["u"], d["v"], "red")
    ctx["title"] = f"TTD{lv},T{lv},Wind{lv}"
    legend_box(ax, [("white", "\\\\\\\\\\\\", BL), ("white", "\\\\\\\\", BL),
                    ("white", "////", "#8a8a8a"), ("white", None, None)],
               ["0", "1.5", "3", "6", "12"])


def chart_t850(ax, V, F, ctx):
    _chart_tdep(ax, V, F, ctx, 850)


def chart_t925(ax, V, F, ctx):
    _chart_tdep(ax, V, F, ctx, 925)


def chart_t975(ax, V, F, ctx):
    _chart_tdep(ax, V, F, ctx, 975)


def chart_t500(ax, V, F, ctx):
    _chart_tdep(ax, V, F, ctx, 500)


def chart_t700(ax, V, F, ctx):
    d = F["p"][700]
    V.set_level(F, 700)
    RD = "#e03030"
    hatch(ax, V, d["w"], [-1000, -70, -30, -10], ["OO", "oo", ".."], RD)
    ttd = d["t"] - dewpoint(d["t"], d["r"])
    ax.contour(V.flon, V.flat, V.fine(ttd), levels=[3], colors="#3a6fd8", linewidths=0.8,
               linestyles="--", transform=PC, zorder=3)
    lines(ax, V, d["t"], np.arange(-40, 30, 3), color="red", lw=1.1,
          label_levels=list(range(-30, 30, 3)), fmt="%d", fs=8)
    barbs(ax, V, d["u"], d["v"], "red")
    ctx["title"] = "TTD700,OMG,T700,Wind700"
    legend_box(ax, [("white", "OO", RD), ("white", "oo", RD), ("white", "..", RD)],
               ["", "-70", "-30", "-10"])


def chart_ept850(ax, V, F, ctx):
    d = F["p"][850]
    V.set_level(F, 850)
    s = ssi(F)
    RD = "#e03030"
    hatch(ax, V, s, [-100, -3, 0], ["OO", "oo"], RD)
    ax.contour(V.flon, V.flat, V.fine(s), levels=[-9, -6, -3, 0, 3, 6], colors=RD, linewidths=0.7,
               linestyles="--", transform=PC, zorder=3)
    e = ept(F)
    lines(ax, V, e, np.arange(240, 390, 3), color="#9b30d9", lw=1.0, lw_major=2.0,
          major=list(range(240, 390, 9)), label_levels=list(range(240, 390, 9)), fmt="%d", fs=8)
    barbs(ax, V, d["u"], d["v"], "red")
    ctx["title"] = "Wind850,SSI(500-850),EPT"
    legend_box(ax, [("white", "OO", RD), ("white", "oo", RD), ("white", None, None), ("white", None, None)],
               ["-9", "-3", "0", "3", "6"])


CHARTS = {
    "surf": dict(label="地上（気圧・風・降水）", fn=chart_surf),
    "tenki": dict(label="地上（天気・気圧・SSI）", fn=chart_tenki),
    "z500": dict(label="500hPa（高度・渦度）", fn=chart_z500),
    "t500": dict(label="500hPa（気温・湿数・風）", fn=chart_t500),
    "jet300": dict(label="300hPa（ジェット・気温・風）", fn=chart_jet300),
    "t850": dict(label="850hPa（気温・湿数・風）", fn=chart_t850),
    "t700": dict(label="700hPa（上昇流・気温・湿数）", fn=chart_t700),
    "t925": dict(label="925hPa（気温・湿数・風）", fn=chart_t925),
    "t975": dict(label="975hPa（気温・湿数・風）", fn=chart_t975, levels=[975]),
    "ept850": dict(label="850hPa（EPT・SSI・風）", fn=chart_ept850),
}


# ---------------------------------------------------------------- 海岸線・国境（地域ごとに一度だけ投影）
_BASE_CACHE = {}


def base_lines(region, proj):
    """海岸線・国境を地域の範囲で切り出して投影した線分リスト（coast, border）を返す。"""
    if region in _BASE_CACHE:
        return _BASE_CACHE[region]
    from shapely.geometry import box
    r = REGIONS[region]
    lon0, lon1, lat0, lat1 = r["bbox"]
    clip = box(lon0, lat0, lon1, lat1)

    def project(feature):
        segs = []
        for g in feature.geometries():
            g = g.intersection(clip)
            if g.is_empty:
                continue
            pg = proj.project_geometry(g, PC)
            for part in getattr(pg, "geoms", [pg]):
                if part.geom_type == "LineString":
                    segs.append(np.asarray(part.coords))
        return segs

    coast = project(cfeature.COASTLINE.with_scale(r["coast"]))
    border = project(cfeature.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land", "50m"))
    _BASE_CACHE[region] = (coast, border)
    return coast, border


# ---------------------------------------------------------------- 枠・見出し
def _caption(fig, parts, y):
    """色の違う文字を横に並べる（実際の描画幅で位置を決める）。"""
    r = fig.canvas.get_renderer()
    x = 4 / (FIG_W * DPI)
    for text, color, fs in parts:
        t = fig.text(x, y, text, color=color, fontsize=fs, family="serif",
                     va="center", ha="left")
        bb = t.get_window_extent(r)
        x += bb.width / (FIG_W * DPI) + 8 / (FIG_W * DPI)


def render_chart(chart, region, F, init, ft, outpath, model="", quantize=True):
    """1枚描画して outpath に保存する。init は UTC の datetime。"""
    proj, extent = make_projection(region)
    V = View(F, region)
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    ax = fig.add_axes(MAP_RECT, projection=proj)
    ax.set_extent(extent, crs=proj)

    coast, border = base_lines(region, proj)
    ax.add_collection(LineCollection(coast, colors="k", linewidths=0.8, zorder=4))
    ax.add_collection(LineCollection(border, colors="#555555", linewidths=0.4, zorder=4))
    gl = ax.gridlines(crs=PC, draw_labels=False, linewidth=0.7, color="k", alpha=1.0,
                      xlocs=np.arange(-180, 361, 10), ylocs=np.arange(-80, 91, 10))
    gl.set_zorder(4)
    for s in ax.spines.values():
        s.set_edgecolor("#1010e0")
        s.set_linewidth(2.5)

    ctx = dict(ft=ft, title=chart)
    CHARTS[chart]["fn"](ax, V, F, ctx)

    valid = init + timedelta(hours=ft)
    jst = valid + timedelta(hours=9)
    ax.text(0.02, 0.975, f"{valid:%d %H}", transform=ax.transAxes, fontsize=27, family="serif",
            color="#5a3410", va="top", zorder=30)
    ax.text(0.145, 0.955, "UTC", transform=ax.transAxes, fontsize=9,
            family="serif", color="#5a3410", va="top", zorder=30)
    ax.text(0.985, 0.975, f"{jst:%d %H}", transform=ax.transAxes, fontsize=27,
            family="serif", color="red", va="top", ha="right", zorder=30)
    ax.text(0.985, 0.915, "JST", transform=ax.transAxes, fontsize=9, family="serif",
            color="red", va="top", ha="right", zorder=30)
    ax.text(0.006, 0.012, f"{model} INIT:{init:%m/%d %H:%M}(UTC)".strip(), transform=ax.transAxes, fontsize=10,
            color="k", va="bottom", zorder=30)

    _caption(fig, [(f"{init:%d%H}", "#1010e0", 17), (f"<{ft}>", "#d020d0", 17),
                   (ctx["title"], "#7a5a30", 17)], y=21 / 760)
    fig.savefig(outpath, dpi=DPI)
    plt.close(fig)
    if quantize:
        _quantize_png(outpath)


def _quantize_png(path):
    """PNGを256色パレットへ減色して容量を約1/3にする（線画・塗り主体なので見た目はほぼ変わらない）。"""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(path).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
