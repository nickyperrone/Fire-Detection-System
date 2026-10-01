from datetime import date, timedelta

import numpy as np

from app.forecast.dataset import DAYS_SINCE_CAP, history_features, labels

DAYS = [date(2020, 1, 1) + timedelta(days=i) for i in range(366 + 365)]  # 2020 and 2021


def grid_with_fire(*cells_days: tuple[int, int, int]) -> np.ndarray:
    fire = np.zeros((3, 3, len(DAYS)), dtype=bool)
    for row, col, day in cells_days:
        fire[row, col, day] = True
    return fire


def test_labels_look_only_ahead():
    fire = grid_with_fire((1, 1, 10))
    y = labels(fire, horizon=2)[1, 1]
    assert y[8] == 1 and y[9] == 1  # the fire is in the next 2 days
    assert y[10] == 0  # the same day is not "ahead"
    assert y[7] == 0
    assert np.isnan(y[-2:]).all()  # no future to look at


def test_month_rate_uses_earlier_years_only():
    # A fire on 15 Jan 2021 must not inform January 2021 itself.
    jan_15_2021 = DAYS.index(date(2021, 1, 15))
    fire = grid_with_fire((1, 1, 14), (1, 1, jan_15_2021))  # 15 Jan 2020 and 15 Jan 2021
    rate = history_features(fire, DAYS)["cell_month_fire_rate"][1, 1]
    assert np.isnan(rate[DAYS.index(date(2020, 1, 20))])  # no earlier year yet
    assert rate[DAYS.index(date(2021, 1, 20))] == 1.0  # one fire day in one earlier January
    assert rate[DAYS.index(date(2021, 2, 20))] == 0.0


def test_recency_and_neighbourhood():
    fire = grid_with_fire((0, 0, 100))
    features = history_features(fire, DAYS)
    since = features["days_since_cell_fire"][0, 0]
    assert since[99] == DAYS_SINCE_CAP and since[100] == 0 and since[103] == 3
    around = features["fire_days_around_7d"]
    assert around[1, 1, 100] == 1  # diagonal neighbour
    assert around[2, 2, 100] == 0  # two cells away
    assert around[1, 1, 106] == 1 and around[1, 1, 107] == 0  # 7-day window
