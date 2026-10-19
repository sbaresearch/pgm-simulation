import json

import geopandas as gpd

from util import config
from util.name_types import Model
from util.utils import vprint


def load_model(model_path: str) -> Model:
    try:
        subs = gpd.read_file(f"{model_path}/substations.gpkg")
        lines = gpd.read_file(f"{model_path}/lines.gpkg")
        gens = gpd.read_file(f"{model_path}/generators.gpkg")
    except FileNotFoundError as e:
        vprint(
            f"Could not load model from model path '{model_path}'. Does it contain the files:"
            "\n\tsubstations.gpkg"
            "\n\tlines.gpkg"
            "\n\tgenerators.gpkg"
        )
        raise FileNotFoundError(e)

    # Clean up data formats
    subs["voltage"] = subs.voltage.apply(json.loads)
    subs["export_voltage"] = subs.export_voltage.apply(lambda x: json.loads(x) if x is not None else None)
    subs["elwog_id"] = subs.elwog_id.apply(lambda x: tuple(json.loads(x)) if x is not None else None)

    from util.category_translations import generator_source_translation_map

    gens["source"] = gens.source.map(generator_source_translation_map)

    # Change the source for hydro pumps that are not run-of-river
    gens.loc[gens[gens.method == "water-pumped-storage"].index, "source"] = "Hydro Pumped Storage"
    gens.loc[gens[gens.method == "water-storage"].index, "source"] = "Hydro Water Reservoir"
    gens = gens.drop(columns="method")

    # Remove PV generators, which are already included in consumption data from BOKU
    gens = gens[~(gens["source"] == "Solar")]
    if config.WIND_IS_LOCAL:
        gens = gens[~(gens["source"] == "Wind")]

    assert isinstance(gens, gpd.GeoDataFrame)

    # Make sure all generator sources could be mapped
    from util.category_translations import generator_profile_translation_map

    if any(gens.source.isna()) or not all(gens.source.isin(generator_profile_translation_map.values())):
        raise ValueError("A generator had a source that could not be mapped!")

    return Model(subs, gens, lines)
