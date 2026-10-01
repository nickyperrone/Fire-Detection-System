import pytest

from app.forecast.fwi import FwiState, next_day


def test_matches_the_reference_day():
    # First row of the cffdrs test data (Van Wagner and Pickett 1985): a day in April at 46° N
    # starting from the standard start-up values.
    day = next_day(FwiState(85.0, 6.0, 15.0), temp=17, rh=42, wind=25, rain=0, month=4, latitude=46)
    assert day.ffmc == pytest.approx(87.69, abs=0.01)
    assert day.dmc == pytest.approx(8.55, abs=0.01)
    assert day.dc == pytest.approx(19.01, abs=0.01)
    assert day.isi == pytest.approx(10.85, abs=0.01)
    assert day.bui == pytest.approx(8.49, abs=0.01)
    assert day.fwi == pytest.approx(10.10, abs=0.01)


def test_rain_lowers_every_code_and_dry_days_raise_them():
    state = FwiState(90.0, 40.0, 300.0)
    wet = next_day(state, temp=20, rh=80, wind=10, rain=25, month=1, latitude=-33)
    assert wet.ffmc < state.ffmc and wet.dmc < state.dmc and wet.dc < state.dc
    dry = next_day(state, temp=34, rh=15, wind=30, rain=0, month=1, latitude=-33)
    assert dry.ffmc > state.ffmc and dry.dmc > state.dmc and dry.dc > state.dc
    assert dry.fwi > wet.fwi


def test_southern_summer_dries_faster_than_southern_winter():
    state = FwiState()
    january = next_day(state, temp=25, rh=40, wind=10, rain=0, month=1, latitude=-33)
    july = next_day(state, temp=25, rh=40, wind=10, rain=0, month=7, latitude=-33)
    assert january.dmc > july.dmc
    assert january.dc > july.dc
