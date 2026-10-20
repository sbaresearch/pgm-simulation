from typing import NamedTuple

import geopandas as gpd
from pandapower.timeseries.data_sources.frame_data import DataSource


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
