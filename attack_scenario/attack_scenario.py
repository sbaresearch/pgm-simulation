import json

import geopandas as gpd

from util import config
from util.name_types import Model


def remove_attacked_elements(model) -> Model:
    with open(config.ATTACK_SCENARIO, "r") as f:
        data = json.load(f)

    subs = model.subs
    lines = model.lines
    gens = model.gens
    # cons = model.cons

    subs_to_remove = data.get("subs")
    if subs_to_remove is not None:
        subs = _remove_subs(subs, subs_to_remove)

    lines_to_remove = data.get("lines")
    if lines_to_remove is not None:
        lines = _remove_lines(lines, lines_to_remove)

    # Remove lines connected with the removed substations
    if subs_to_remove is not None:
        connected_lines = lines.substation_1.isin(subs_to_remove) | lines.substation_2.isin(subs_to_remove)
        lines = lines.drop(lines[connected_lines].index.to_list())

    # Remove now isolated substations (i.e, subs without any connected lines)
    all_connected_subs = [*lines.substation_1.to_list(), *lines.substation_2.to_list()]
    is_isolated_sub = ~subs.id.isin(all_connected_subs)
    subs = subs.drop(subs[is_isolated_sub].index.to_list())

    # Remove gens and cons connected with the removed substations
    removed_subs = model.subs.id[~model.subs.id.isin(subs.id.to_list())].to_list()
    connected_gens = gens.substation_id.isin(removed_subs)
    gens = gens.drop(gens[connected_gens].index)
    # connected_cons = cons.substation_id.isin(removed_subs)
    # cons = cons.drop(cons[connected_cons].index)

    return Model(subs, gens, lines)  # type: ignore[reportArgumentType]


def _remove_subs(subs: gpd.GeoDataFrame, subs_to_remove: list[int]) -> gpd.GeoDataFrame:
    if not (isinstance(subs_to_remove, list) and all([isinstance(sub, int)] for sub in subs_to_remove)):
        raise TypeError(f"Incorrect format for substations to remove (should be a list of ints): {subs_to_remove}")

    # Check that all subs listed are in the model
    all_ids = subs.id.to_list()
    missing_ids = [sub for sub in subs_to_remove if sub not in all_ids]
    if missing_ids:
        raise ValueError(f"Cannot find subs {missing_ids} to remove for attack scenario!")

    # Remove selected substations
    return subs.drop(subs[subs.id.isin(subs_to_remove)].index)  # type: ignore[reportArgumentType]


def _remove_lines(lines: gpd.GeoDataFrame, lines_to_remove: list[str]) -> gpd.GeoDataFrame:
    if not (isinstance(lines_to_remove, list) and all([isinstance(line, str)] for line in lines_to_remove)):
        raise TypeError(f"Incorrect format for lines to remove (should be a list of strings): {lines_to_remove}")

    # Check that all lines listed are in the model
    all_ids = lines.id.to_list()
    missing_ids = [line for line in lines_to_remove if line not in all_ids]
    if missing_ids:
        raise ValueError(f"Cannot find lines {missing_ids} to remove for attack scenario!")

    # Remove given lines
    return lines.drop(lines[lines.id.isin(lines_to_remove)].index.to_list())  # type: ignore[reportArgumentType]


def _remove_trafo_stations(trafo_stations: gpd.GeoDataFrame, ts_to_remove: list[int]) -> gpd.GeoDataFrame:
    if not (isinstance(ts_to_remove, list) and all([isinstance(ts, int)] for ts in ts_to_remove)):
        raise TypeError(f"Incorrect format for trafo stations to remove (should be a list of ints): {ts_to_remove}")

    # Check that all trafo stations listed are in the model
    all_ids = trafo_stations.index.to_list()
    missing_ids = [ts for ts in ts_to_remove if ts not in all_ids]
    if missing_ids:
        raise ValueError(f"Cannot find trafo stations {missing_ids} to remove for attack scenario!")

    # Remove selected trafo stations
    return trafo_stations.drop(ts_to_remove)  # type: ignore[reportArgumentType]


def _remove_trafo_station_sub_lines(trafo_station_sub_lines, lines_to_remove: list[int]) -> gpd.GeoDataFrame:
    if not (isinstance(lines_to_remove, list) and all([isinstance(group, int)] for group in lines_to_remove)):
        raise TypeError(
            f"Incorrect format for trafo station sub lines to remove (should be a list of ints, "
            f"representing the trafo staion group): {lines_to_remove}"
        )

    # Check that all trafo stations groups listed are in the model
    all_groups = trafo_station_sub_lines.group.to_list()
    missing_ids = [group for group in lines_to_remove if group not in all_groups]
    if missing_ids:
        raise ValueError(f"Cannot find trafo station group {missing_ids} to remove for attack scenario!")

    # Remove selected lines
    line_idx = trafo_station_sub_lines[trafo_station_sub_lines.group.isin(lines_to_remove)].index
    return trafo_station_sub_lines.drop(line_idx)
