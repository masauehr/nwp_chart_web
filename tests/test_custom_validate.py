# 自由選択（断面図・エマグラム）の入力検証のテスト（nwp_chart_web 固有: 読み込み範囲・対象モデル・13層の取得指定）
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import custom
import nwp_data

Q = dict(lat1="41", lon1="126", lat2="29", lon2="146")


def test_accepts_forecast_models_and_rejects_reanalysis_and_unknown():
    for m in ("ecmwf", "gfs", "aifs", "gsm"):
        assert custom.validate("xsection", m, "2026111018", "12", Q)["model"] == m
    with pytest.raises(custom.CustomError) as e:
        custom.validate("xsection", "jra55", "2026111018", "12", Q)               # 再解析（JRA-55）は対象外
    assert "JRA-55" in str(e.value)
    with pytest.raises(custom.CustomError):
        custom.validate("xsection", "nonexistent", "2026111018", "12", Q)


def test_points_must_be_inside_the_data_range():
    c = nwp_data.CROP                                                              # 東経50〜185度・北緯−15〜82度（データを読む範囲）
    ok = dict(lat=str(c["lat1"]), lon=str(c["lon0"]))
    assert custom.validate("emagram", "gfs", "2026111018", "0", ok)["lat"] == c["lat1"]
    for bad in (dict(lat="85", lon="130"), dict(lat="35", lon="10"), dict(lat="-20", lon="130"), dict(lat="35", lon="200")):
        with pytest.raises(custom.CustomError):
            custom.validate("emagram", "gfs", "2026111018", "0", bad)
    with pytest.raises(custom.CustomError):
        custom.validate("xsection", "gfs", "2026111018", "0", dict(Q, lon2="190"))


def test_custom_uses_13_levels_but_the_regular_pipeline_keeps_7():
    assert len(nwp_data.CUSTOM_PLEVELS) == 13 and 100 in nwp_data.CUSTOM_PLEVELS and 1000 in nwp_data.CUSTOM_PLEVELS
    assert nwp_data.PLEVELS == (975, 925, 850, 700, 500, 300, 200)                 # 自動更新の取得量は増やさない


def test_plevels_argument_selects_levels():
    rows = [{"param": "t", "levtype": "pl", "levelist": str(lv), "_offset": i * 10, "_length": 10}
            for i, lv in enumerate((1000, 850, 400, 100))]
    assert len(nwp_data._ecmwf_select(rows)) == 1                                  # 既定(PLEVELS)では 850 だけ
    assert len(nwp_data._ecmwf_select(rows, "ecmwf", nwp_data.CUSTOM_PLEVELS)) == 4  # 自由選択の13層では4層とも選ぶ
