"""Canadian Forest Fire Weather Index System (Van Wagner 1987), one day at a time.

Inputs per day: noon temperature (°C), relative humidity (%), wind (km/h) and 24 h rain (mm).
Day-length factors for DMC and DC depend on latitude; the southern tables follow the R package
cffdrs (Wang et al. 2017), which adapts the system outside Canada.
"""

import math
from dataclasses import dataclass

# DMC effective day length by month, by latitude band.
DMC_DAY_LENGTH = {
    "north_33": [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0],
    "north_15": [7.9, 8.4, 8.9, 9.5, 9.9, 10.2, 10.1, 9.7, 9.1, 8.6, 8.1, 7.8],
    "equator": [9.0] * 12,
    "south_15": [10.1, 9.6, 9.1, 8.5, 8.1, 7.8, 7.9, 8.3, 8.9, 9.4, 9.9, 10.2],
    "south_30": [11.5, 10.5, 9.2, 7.9, 6.8, 6.2, 6.5, 7.4, 8.7, 10.0, 11.2, 11.8],
}
# DC day length adjustment by month.
DC_DAY_LENGTH = {
    "north": [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6],
    "equator": [1.4] * 12,
    "south": [6.4, 5.0, 2.4, 0.4, -1.6, -1.6, -1.6, -1.6, -1.6, 0.9, 3.8, 5.8],
}


@dataclass(frozen=True)
class FwiState:
    """The three moisture codes carried from one day to the next."""

    ffmc: float = 85.0
    dmc: float = 6.0
    dc: float = 15.0


@dataclass(frozen=True)
class FwiDay:
    ffmc: float
    dmc: float
    dc: float
    isi: float
    bui: float
    fwi: float

    @property
    def state(self) -> FwiState:
        return FwiState(self.ffmc, self.dmc, self.dc)


def _dmc_day_length(latitude: float, month: int) -> float:
    if latitude > 33:
        band = "north_33"
    elif latitude > 15:
        band = "north_15"
    elif latitude > -15:
        band = "equator"
    elif latitude > -30:
        band = "south_15"
    else:
        band = "south_30"
    return DMC_DAY_LENGTH[band][month - 1]


def _dc_day_length(latitude: float, month: int) -> float:
    band = "north" if latitude > 20 else "south" if latitude <= -20 else "equator"
    return DC_DAY_LENGTH[band][month - 1]


def ffmc(previous: float, temp: float, rh: float, wind: float, rain: float) -> float:
    mo = 147.2 * (101 - previous) / (59.5 + previous)
    if rain > 0.5:
        rf = rain - 0.5
        wetting = 42.5 * rf * math.exp(-100 / (251 - mo)) * (1 - math.exp(-6.93 / rf))
        if mo > 150:
            wetting += 0.0015 * (mo - 150) ** 2 * math.sqrt(rf)
        mo = min(mo + wetting, 250.0)
    ed = (
        0.942 * rh**0.679
        + 11 * math.exp((rh - 100) / 10)
        + 0.18 * (21.1 - temp) * (1 - math.exp(-0.115 * rh))
    )
    if mo > ed:
        ko = 0.424 * (1 - (rh / 100) ** 1.7) + 0.0694 * math.sqrt(wind) * (1 - (rh / 100) ** 8)
        kd = ko * 0.581 * math.exp(0.0365 * temp)
        m = ed + (mo - ed) * 10 ** (-kd)
    else:
        ew = (
            0.618 * rh**0.753
            + 10 * math.exp((rh - 100) / 10)
            + 0.18 * (21.1 - temp) * (1 - math.exp(-0.115 * rh))
        )
        if mo < ew:
            dry = (100 - rh) / 100
            k1 = 0.424 * (1 - dry**1.7) + 0.0694 * math.sqrt(wind) * (1 - dry**8)
            kw = k1 * 0.581 * math.exp(0.0365 * temp)
            m = ew - (ew - mo) * 10 ** (-kw)
        else:
            m = mo
    return min(max(59.5 * (250 - m) / (147.2 + m), 0.0), 101.0)


def dmc(previous: float, temp: float, rh: float, rain: float, month: int, latitude: float) -> float:
    temp = max(temp, -1.1)
    rk = 1.894 * (temp + 1.1) * (100 - rh) * _dmc_day_length(latitude, month) * 1e-4
    if rain > 1.5:
        rw = 0.92 * rain - 1.27
        wmi = 20 + 280 / math.exp(0.023 * previous)
        if previous <= 33:
            b = 100 / (0.5 + 0.3 * previous)
        elif previous <= 65:
            b = 14 - 1.3 * math.log(previous)
        else:
            b = 6.2 * math.log(previous) - 17.2
        wmr = wmi + 1000 * rw / (48.77 + b * rw)
        pr = max(43.43 * (5.6348 - math.log(wmr - 20)), 0.0)
    else:
        pr = previous
    return pr + max(rk, 0.0)


def dc(previous: float, temp: float, rain: float, month: int, latitude: float) -> float:
    temp = max(temp, -2.8)
    pe = max((0.36 * (temp + 2.8) + _dc_day_length(latitude, month)) / 2, 0.0)
    if rain > 2.8:
        rw = 0.83 * rain - 1.27
        smi = 800 * math.exp(-previous / 400)
        dr = max(previous - 400 * math.log(1 + 3.937 * rw / smi), 0.0)
    else:
        dr = previous
    return dr + pe


def isi(ffmc_value: float, wind: float) -> float:
    fm = 147.2 * (101 - ffmc_value) / (59.5 + ffmc_value)
    spread = 19.115 * math.exp(-0.1386 * fm) * (1 + fm**5.31 / 4.93e7)
    return spread * math.exp(0.05039 * wind)


def bui(dmc_value: float, dc_value: float) -> float:
    if dmc_value == 0 and dc_value == 0:
        return 0.0
    if dmc_value <= 0.4 * dc_value:
        value = 0.8 * dc_value * dmc_value / (dmc_value + 0.4 * dc_value)
    else:
        value = dmc_value - (1 - 0.8 * dc_value / (dmc_value + 0.4 * dc_value)) * (
            0.92 + (0.0114 * dmc_value) ** 1.7
        )
    return max(value, 0.0)


def fwi(isi_value: float, bui_value: float) -> float:
    if bui_value <= 80:
        bb = 0.1 * isi_value * (0.626 * bui_value**0.809 + 2)
    else:
        bb = 0.1 * isi_value * (1000 / (25 + 108.64 * math.exp(-0.023 * bui_value)))
    return bb if bb <= 1 else math.exp(2.72 * (0.434 * math.log(bb)) ** 0.647)


def next_day(
    state: FwiState,
    temp: float,
    rh: float,
    wind: float,
    rain: float,
    month: int,
    latitude: float,
) -> FwiDay:
    rh = min(max(rh, 0.0), 100.0)
    ffmc_value = ffmc(state.ffmc, temp, rh, wind, rain)
    dmc_value = dmc(state.dmc, temp, rh, rain, month, latitude)
    dc_value = dc(state.dc, temp, rain, month, latitude)
    isi_value = isi(ffmc_value, wind)
    bui_value = bui(dmc_value, dc_value)
    return FwiDay(ffmc_value, dmc_value, dc_value, isi_value, bui_value, fwi(isi_value, bui_value))
