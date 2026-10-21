from datetime import datetime

import numpy as np
import pandas as pd
from pandapower.auxiliary import pandapowerNet
from pandapower.control import ConstControl
from pandapower.timeseries.data_sources.frame_data import DFData

from util import config
from util.name_types import DataSources, Model
from util.power_factors import GENERATION_POWER_FACTOR
from util.utils import vprint


class DSBuilder:
    """
    Used for creating and handling the DataSources, which handle updating values for the different
    net elements when running a timeseries evaluation in pandapower.

    The class has grown to handle all data concerning consumption, generation, and import/export.
    It is also what keeps track of which elwog substations actually have consumption and generation.
    """

    dates: list[datetime]
    model: Model

    _con_data: pd.DataFrame
    _local_gen_data: pd.DataFrame
    _gen_profile: pd.DataFrame | None
    _import_export_profile: pd.DataFrame | None

    def __init__(self, dates: list[datetime], model: Model):
        self.dates = dates
        self.model = model

        vprint("Loading consumption and local power generation data")
        self._con_data = self._load_consumption()
        self._local_gen_data = self._load_local_gen()

        vprint("Loading generation and import/export profiles")
        self._gen_profile = self._load_gen_profile()
        self._import_export_profile = self._load_import_export_profile()

        vprint("Scaling load from actual APG load")
        scaled_load = self._scale_from_actual_load()
        if scaled_load is not None:
            self._con_data = scaled_load

    def get_subs_with_local_gen(self) -> list[int]:
        return self._local_gen_data.columns.astype("int").to_list()

    def get_subs_with_con(self) -> list[int]:
        return self._con_data.columns.astype("int").to_list()

    def use_import_export(self) -> bool:
        return self._import_export_profile is not None

    def update_from_net(self):
        # Remove consumers not in net
        from network.static_network_builder import elwog_id_to_load_id

        self._con_data = self._con_data[elwog_id_to_load_id.keys()]  # pyright: ignore[reportAttributeAccessIssue]

        # Remove local gens not in net
        from network.static_network_builder import elwog_id_to_local_sgen_id

        self._local_gen_data = self._local_gen_data[elwog_id_to_local_sgen_id.keys()]  # pyright: ignore[reportAttributeAccessIssue]

        # Only keep categories in the gen profile that the model actually contains
        if self._gen_profile is not None:
            from network.static_network_builder import pq_gen_ids, pv_gen_ids

            gens_in_net = self.model.gens.set_index("id").loc[[*pv_gen_ids, *pq_gen_ids]]
            self._gen_profile = self._gen_profile[gens_in_net.source.unique()]  # pyright: ignore[reportAttributeAccessIssue]

        # Remove countries that do not have any subs in the model
        if self._import_export_profile is not None:
            from network.static_network_builder import export_country_to_load_ids

            self._import_export_profile = self._import_export_profile[export_country_to_load_ids.keys()]  # pyright: ignore[reportAttributeAccessIssue]

    def load_datasources(self, model: Model) -> DataSources:
        load_real_ds, load_reactive_ds = self._get_con_ds()

        res = self._get_gen_ds(model)
        gen_ds, sgen_real_ds, sgen_reactive_ds, hydro_pump_real_load_df, hydro_pump_reactive_load_df = res

        # Update loads with hydro pump storage load
        load_real_ds = DFData(
            pd.merge(load_real_ds.df, hydro_pump_real_load_df.df, left_index=True, right_index=True).sort_index(axis=1)
        )
        load_reactive_ds = DFData(
            pd.merge(load_reactive_ds.df, hydro_pump_reactive_load_df.df, left_index=True, right_index=True).sort_index(
                axis=1
            )
        )

        if not self._local_gen_data.empty:
            local_sgen_real_ds, local_sgen_reactive_ds = self._get_local_ds()

            sgen_real_ds = DFData(pd.merge(sgen_real_ds.df, local_sgen_real_ds.df, left_index=True, right_index=True))
            sgen_reactive_ds = DFData(
                pd.merge(sgen_reactive_ds.df, local_sgen_reactive_ds.df, left_index=True, right_index=True)
            )

        if self._import_export_profile is not None:
            import_export_sources = self._get_import_export_ds(self._import_export_profile)
            exported_real_ds, exported_reactive_ds, imported_ds = import_export_sources

            # Update loads with export data
            load_real_ds = DFData(pd.merge(load_real_ds.df, exported_real_ds.df, left_index=True, right_index=True))
            load_reactive_ds = DFData(
                pd.merge(load_reactive_ds.df, exported_reactive_ds.df, left_index=True, right_index=True)
            )

            # Update gen with import data
            gen_ds = DFData(pd.merge(gen_ds.df, imported_ds.df, left_index=True, right_index=True))

        return DataSources(load_real_ds, load_reactive_ds, gen_ds, sgen_real_ds, sgen_reactive_ds)

    def create_controllers_from_ds(
        self, net: pandapowerNet, datasources: DataSources
    ) -> tuple[pandapowerNet, tuple[ConstControl, ...]]:
        load_real = ConstControl(
            net,
            element="load",
            element_index=net.load.index,
            variable="p_mw",
            data_source=datasources.load_real_ds,
            profile_name=net.load.index,
        )
        load_reactive = ConstControl(
            net,
            element="load",
            element_index=net.load.index,
            variable="q_mvar",
            data_source=datasources.load_reactive_ds,
            profile_name=net.load.index,
        )

        gen = ConstControl(
            net,
            element="gen",
            element_index=net.gen.index,
            variable="p_mw",
            data_source=datasources.gen_ds,
            profile_name=net.gen.index,
        )

        sgen_real = ConstControl(
            net,
            element="sgen",
            element_index=net.sgen.index,
            variable="p_mw",
            data_source=datasources.sgen_real_ds,
            profile_name=net.sgen.index,
        )
        sgen_reactive = ConstControl(
            net,
            element="sgen",
            element_index=net.sgen.index,
            variable="q_mvar",
            data_source=datasources.sgen_reactive_ds,
            profile_name=net.sgen.index,
        )

        return net, (load_real, load_reactive, gen, sgen_real, sgen_reactive)

    def _load_consumption(self) -> pd.DataFrame:
        if config.WIND_IS_LOCAL:
            con = pd.read_csv(f"{config.SCENARIO_PATH}/stdWINDNetzbedarf_MW.csv", parse_dates=["Zeitstempel"])
        else:
            con = pd.read_csv(f"{config.SCENARIO_PATH}/stdNetzbedarf_MW.csv", parse_dates=["Zeitstempel"])
        con = con.rename(columns={"Zeitstempel": "date"}).set_index("date").rename(columns=int)
        con.columns.name = "elwog_id"

        con = con.loc[self.dates]

        # Remove consumers with no consumption for the period
        con = con.loc[:, (con != 0).any()]

        return con

    def _load_local_gen(self) -> pd.DataFrame:
        if config.WIND_IS_LOCAL:
            local_gen = pd.read_csv(f"{config.SCENARIO_PATH}/stdWINDEinspeisung_MW.csv", parse_dates=["Zeitstempel"])
        else:
            local_gen = pd.read_csv(f"{config.SCENARIO_PATH}/stdEinspeisung_MW.csv", parse_dates=["Zeitstempel"])

        local_gen = local_gen.rename(columns={"Zeitstempel": "date"}).set_index("date").rename(columns=int)
        local_gen.columns.name = "elwog_id"

        local_gen = local_gen.loc[self.dates]

        # Remove columns only containing zeros (i.e, never generating any power)
        local_gen = local_gen.loc[:, (local_gen != 0).any()]

        return local_gen

    def _load_gen_profile(self) -> pd.DataFrame | None:
        try:
            gen = pd.read_csv(f"{config.SCENARIO_PATH}/generation_per_source.csv")
        except FileNotFoundError:
            vprint(f"\tNo generation profile found for scenario {config.SCENARIO_PATH}.")
            vprint("\tScaling generation to match consumption.")
            return None

        # Remove the unit from the column name
        gen = gen.rename(lambda s: s[: s.find("[") - 1], axis=1)

        # Create datetime object from the Time From string
        gen["date"] = pd.to_datetime(gen["Time from"])
        cols_to_drop = ["Time from", "Time to", "Solar"]
        if config.WIND_IS_LOCAL:
            cols_to_drop.append("Wind")
        gen = gen.drop(cols_to_drop, axis=1).set_index("date")

        gen = gen.loc[self.dates]

        # Sum columns that are translated into the same category
        from util.category_translations import generator_profile_translation_map

        gen = gen.rename(generator_profile_translation_map, axis=1)
        if "NAN" in gen.columns:
            gen = gen.drop(columns=["NAN"])

        for column in gen.columns.unique():
            if not isinstance(gen[column], pd.DataFrame):
                # Only sum over categories with multiple columns
                continue
            gen[column + "_sum"] = gen[column].sum(axis=1)  # type: ignore
            gen = gen.drop(columns=[column]).rename(columns={column + "_sum": column})

        return gen

    def _load_import_export_profile(self) -> pd.DataFrame | None:
        try:
            df = pd.read_csv(f"{config.SCENARIO_PATH}/power_import_export.csv")
        except FileNotFoundError:
            vprint(f"\tNo Import/Export profile found for scenario {config.SCENARIO_PATH}.")
            vprint("\tAssuming no import/export.")
            return None

        df["date"] = pd.to_datetime(df["Time from [CET/CEST]"])
        df = df.set_index("date")
        df = df.loc[self.dates]

        short_names_mapper = {
            "CZ>AT Power [MW]": "CZ",
            "HU>AT Power [MW]": "HU",
            "SI>AT Power [MW]": "SI",
            "IT>AT Power [MW]": "IT",
            "CH>AT Power [MW]": "CH",
            "DE>AT Power [MW]": "DE",
        }
        df = df.rename(short_names_mapper, axis=1)
        data_cols = ["CZ", "HU", "SI", "IT", "CH", "DE"]

        return df[data_cols]

    def _scale_from_actual_load(self) -> pd.DataFrame | None:
        try:
            actual_load = (
                pd.read_csv(f"{config.SCENARIO_PATH}/total_actual_load.csv", parse_dates=["Time from [CET/CEST]"])
                .rename(columns={"Time from [CET/CEST]": "date", "Power [MW]": "load"})
                .drop(columns="Time to [CET/CEST]")
                .set_index("date")
                .loc[self.dates]
            )
        except FileNotFoundError:
            vprint(f"\tNo actual load found for scenario {config.SCENARIO_PATH}.")
            vprint("\tNot scaling load.")
            return None

        try:
            local_power_cats = ["solar", "wind"] if config.WIND_IS_LOCAL else ["solar"]
            local_power = (
                pd.read_csv(f"{config.SCENARIO_PATH}/generation_per_source.csv", parse_dates=["Time from [CET/CEST]"])
                .rename(columns={"Time from [CET/CEST]": "date", "Solar [MW]": "solar", "Wind [MW]": "wind"})
                .drop(columns="Time to [CET/CEST]")
                .set_index("date")
                .loc[self.dates][local_power_cats]
            )
        except FileNotFoundError:
            vprint(f"\tNo generation per source found for scenario {config.SCENARIO_PATH}.")
            vprint("\tNot scaling load.")
            return None

        df = pd.DataFrame()

        df["actual_load"] = actual_load
        df["apg_local"] = local_power.solar
        if config.WIND_IS_LOCAL:
            df["apg_local"] = df.apg_local + local_power.wind

        df["con"] = self._con_data.sum(axis=1)
        df["local_gen"] = self._local_gen_data.sum(axis=1)

        # Calculate the scaling factor, which ensures that the load matches the "actual load"
        # for each time step
        con_scaling_factor = (df.actual_load - df.apg_local + df.local_gen) / df.con

        return self._con_data.mul(con_scaling_factor, axis=0)

    def _get_con_ds(self) -> tuple[DFData, DFData]:
        from network.static_network_builder import elwog_id_to_load_id

        df = self._con_data.rename(columns=elwog_id_to_load_id)
        real_load_df = df.reset_index(drop=True)

        from util.power_factors import CONSUMER_RP_FACTOR

        reactive_load_df = real_load_df.copy() * CONSUMER_RP_FACTOR

        return DFData(real_load_df), DFData(reactive_load_df)

    def _get_local_ds(self) -> tuple[DFData, DFData]:
        from network.static_network_builder import elwog_id_to_local_sgen_id

        df = self._local_gen_data.rename(columns=elwog_id_to_local_sgen_id)
        real_sgen_df = df.reset_index(drop=True)

        # TODO: random number
        from util.power_factors import LOCAL_WIND_RP_FACTOR

        reactive_gen_factor = LOCAL_WIND_RP_FACTOR if config.WIND_IS_LOCAL else 0
        reactive_sgen_df = real_sgen_df.copy() * reactive_gen_factor

        return DFData(real_sgen_df), DFData(reactive_sgen_df)

    def _get_gen_ds(self, model: Model) -> tuple[DFData, DFData, DFData, DFData, DFData]:
        gens = model.gens.copy()

        # Remove generators not in net
        from network.static_network_builder import pq_gen_ids, pv_gen_ids

        gens = gens.set_index("id").loc[[*pv_gen_ids, *pq_gen_ids]]

        gens["capacity_MW"] = gens.output_w / 1e6
        if self._gen_profile is None:
            # If there is no gen profile available, simply scale the generation to match the load.
            return self._scale_gens_to_match_load(gens)
        else:
            # If there is one, spread the generation per source over all gens with that source
            return self._scale_gens_from_profile(gens, self._gen_profile)

    def _scale_gens_to_match_load(self, gens: pd.DataFrame) -> tuple[DFData, DFData, DFData, DFData, DFData]:
        # TODO: also take import/export into account? (if somehow there is no gen profile, but there is an import_export_profile...)
        total_gen_capacity = gens.capacity_MW.sum()
        gen_capacities = gens.capacity_MW

        net_load_per_day = self._con_data.sum(axis=1) - self._local_gen_data.sum(axis=1)
        net_load_per_day[net_load_per_day < 0] = 0

        factor = net_load_per_day / total_gen_capacity

        scaled_gen = pd.DataFrame(
            factor.to_numpy()[:, None] * gen_capacities.to_numpy()[None, :],
            columns=gen_capacities.index,  # ids
        )

        from network.static_network_builder import pq_gen_ids, pv_gen_ids

        pv_mask = gens.index.isin(pv_gen_ids)
        pq_mask = gens.index.isin(pq_gen_ids)

        from network.static_network_builder import (
            hydro_pump_osm_id_to_load_id,
            pq_gen_id_to_net_id,
            pv_gen_id_to_net_id,
        )

        gen_df = scaled_gen[scaled_gen.columns[pv_mask]].rename(columns=pv_gen_id_to_net_id).sort_index(axis=1)  # pyright: ignore[reportCallIssue]
        sgen_real_df = scaled_gen[scaled_gen.columns[pq_mask]].rename(columns=pq_gen_id_to_net_id).sort_index(axis=1)  # pyright: ignore[reportCallIssue]
        sgen_reactive_df = sgen_real_df / 8  # TODO: make this dependant on source??

        # Assume no pumped storage load
        hydro_pumped_gens = gens[gens.source == "Hydro Pumped Storage"]
        num_hydro_pump_gens = len(hydro_pumped_gens)
        hydro_pump_real_load_df = (
            pd.DataFrame(np.zeros((len(gen_df), num_hydro_pump_gens)), columns=hydro_pumped_gens.index)
            .rename(columns=hydro_pump_osm_id_to_load_id)
            .sort_index(axis=1)
        )
        hydro_pump_reactive_load_df = hydro_pump_real_load_df.copy()

        return (
            DFData(gen_df),
            DFData(sgen_real_df),
            DFData(sgen_reactive_df),
            DFData(hydro_pump_real_load_df),
            DFData(hydro_pump_reactive_load_df),
        )

    def _scale_gens_from_profile(
        self, gens: pd.DataFrame, profile: pd.DataFrame
    ) -> tuple[DFData, DFData, DFData, DFData, DFData]:
        """Calculate scaling per gen based on total power generated by each time for each source"""
        total_capacity_per_cat = gens.groupby("source")["capacity_MW"].sum()
        profile_matrix = profile.loc[self.dates].to_numpy()  # shape: (n_dates, n_categories)

        cat_to_idx = {cat: i for i, cat in enumerate(profile.columns)}
        gen_cat_idx = gens["source"].map(cat_to_idx).to_numpy()  # pyright: ignore[reportArgumentType]

        # Get hydro pumped storage load
        # FIXME: if there are no hydro pumped storage gens that row is removed from the profile and this fails
        hydro_pump_load = profile_matrix.copy()[:, cat_to_idx["Hydro Pumped Storage"]]
        hydro_pump_load[hydro_pump_load > 0] = 0
        hydro_pump_load = -hydro_pump_load
        hydro_pumped_gens = gens[gens.source == "Hydro Pumped Storage"]
        num_hydro_pump_gens = len(hydro_pumped_gens)
        hydro_pump_load = hydro_pump_load / num_hydro_pump_gens
        hydro_pump_load = hydro_pump_load[:, None].repeat(num_hydro_pump_gens, axis=1)  # expand to one col per gen

        # Remove load from scaling matrix
        profile_matrix[profile_matrix < 0] = 0

        # Calculate the scaling matrix, where each value shows how much the generators of that source (column)
        # should be scaled at that time step (row).
        total_capacity_array = np.array([total_capacity_per_cat[cat] for cat in profile.columns])
        scaling_matrix = profile_matrix / total_capacity_array  # shape: (n_dates, n_categories)

        # Some fancy matrix operations gives us the matrix power, which contains one row per timestamp
        # and one column per generator, and each value is the amount of power generated by that
        # generator at that time step.
        gen_capacity = gens["capacity_MW"].to_numpy()
        power = scaling_matrix[:, gen_cat_idx] * gen_capacity  # shape: (n_dates, n_generators)

        # Now split the power into the pv and pq nodes
        from network.static_network_builder import pq_gen_ids, pv_gen_ids

        pv_mask = gens.index.isin(pv_gen_ids)
        pq_mask = gens.index.isin(pq_gen_ids)
        pv_power = power[:, pv_mask]
        pq_power = power[:, pq_mask]

        # Create the datasources
        from network.static_network_builder import (
            hydro_pump_osm_id_to_load_id,
            pq_gen_id_to_net_id,
            pv_gen_id_to_net_id,
        )

        gen_df = pd.DataFrame(pv_power, columns=pv_gen_ids).rename(columns=pv_gen_id_to_net_id).sort_index(axis=1)  # pyright: ignore[reportArgumentType]
        sgen_real_df = pd.DataFrame(pq_power, columns=pq_gen_ids).rename(columns=pq_gen_id_to_net_id).sort_index(axis=1)  # pyright: ignore[reportArgumentType]
        hydro_pump_real_load_df = (
            pd.DataFrame(hydro_pump_load, columns=hydro_pumped_gens.index)
            .rename(columns=hydro_pump_osm_id_to_load_id)
            .sort_index(axis=1)
        )
        from util.power_factors import HYDRO_PUMP_LOAD_RP_FACTOR

        hydro_pump_reactive_load_df = hydro_pump_real_load_df.copy() * HYDRO_PUMP_LOAD_RP_FACTOR

        # Scale reactive power generation based on source
        pq_gen_sources = gens.loc[pq_gen_ids].source.rename(index=pq_gen_id_to_net_id)
        pq_reactive_scaling = pq_gen_sources.map(GENERATION_POWER_FACTOR)
        sgen_reactive_df = sgen_real_df * pq_reactive_scaling

        return (
            DFData(gen_df),
            DFData(sgen_real_df),
            DFData(sgen_reactive_df),
            DFData(hydro_pump_real_load_df),
            DFData(hydro_pump_reactive_load_df),
        )

    def _get_import_export_ds(self, profile: pd.DataFrame) -> tuple[DFData, DFData, DFData]:
        countries = profile.columns

        profile_matrix = profile.to_numpy()  # shape: (n_dates, n_countries)

        from network.static_network_builder import export_country_to_gen_ids, export_country_to_load_ids

        all_load_ids = sorted({lid for c in countries for lid in export_country_to_load_ids[c]})
        all_gen_ids = sorted({gid for c in countries for gid in export_country_to_gen_ids[c]})

        # Go through each country and find how much each bus should take of the overall import/export
        # to that country.
        load_id_to_idx = {lid: i for i, lid in enumerate(all_load_ids)}
        country_to_bus_scaling_map = np.zeros((len(countries), len(all_load_ids)))
        for i, c in enumerate(countries):
            load_ids = export_country_to_load_ids[c]
            val = 1 / len(load_ids)
            for lid in load_ids:
                country_to_bus_scaling_map[i, load_id_to_idx[lid]] = val

        # Split into import/export based on sign
        import_mask = profile_matrix >= 0
        export_mask = profile_matrix < 0

        imported_power = profile_matrix * import_mask
        imported = imported_power @ country_to_bus_scaling_map

        exported_power = -profile_matrix * export_mask
        exported_real = exported_power @ country_to_bus_scaling_map

        from util.power_factors import EXPORTED_RP_FACTOR

        exported_reactive = exported_real * EXPORTED_RP_FACTOR

        exported_real_df = pd.DataFrame(exported_real, columns=all_load_ids)  # pyright: ignore[reportArgumentType]
        exported_reactive_df = pd.DataFrame(exported_reactive, columns=all_load_ids)  # pyright: ignore[reportArgumentType]
        imported_df = pd.DataFrame(imported, columns=all_gen_ids)  # pyright: ignore[reportArgumentType]

        return DFData(exported_real_df), DFData(exported_reactive_df), DFData(imported_df)
