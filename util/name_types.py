from __future__ import annotations
from typing import NamedTuple
from enum import Enum

from pandapower.timeseries.data_sources.frame_data import DataSource
from pandapower.control import ConstControl
import geopandas as gpd


class RunStatus(Enum):
    SUCCESS = 1
    CONTROLLER_ERROR = 2
    FAILED = 3


class Model(NamedTuple):
    subs: gpd.GeoDataFrame
    gens: gpd.GeoDataFrame
    lines: gpd.GeoDataFrame


class DataSources(NamedTuple):
    load_real_ds: DataSource
    load_reactive_ds: DataSource
    gen_ds: DataSource
    sgen_real_ds: DataSource
    sgen_reactive_ds: DataSource
