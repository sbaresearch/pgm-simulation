from datetime import datetime

import pandas as pd
from pandapower.auxiliary import pandapowerNet
from pandapower.timeseries import OutputWriter

from network.static_network_builder import line_osm_id_to_network_id, sub_id_and_v_to_bus_id
from util import config
from util.name_types import Model


def process_stats(net: pandapowerNet, dates: list[datetime], ow: OutputWriter, model: Model):
    raw_stats_dir = str(ow.output_path)
    stat_processor = StatProcessor(net, dates, raw_stats_dir)

    # Save geopackages with information on the different elements from the model, including
    # a mapping from the element to the network ids
    if isinstance(model, Model):
        stat_processor.save_substations(model)
        stat_processor.save_lines(model)
        # stat_processor.save_cons(model)

    # Also process the network elements
    stat_processor.process_buses()
    stat_processor.process_lines()
    stat_processor.process_power()


class StatProcessor:
    net: pandapowerNet
    dates: list[datetime]
    raw_stats_dir: str

    def __init__(self, net: pandapowerNet, dates: list[datetime], raw_stats_dir: str):
        self.net = net
        self.dates = dates
        self.raw_stats_dir = raw_stats_dir

    def save_substations(self, model: Model):
        subs = model.subs[["id", "voltage", "type", "name", "operator", "elwog_id", "geometry"]]
        subs = subs.explode("voltage").reset_index(drop=True)  # pyright: ignore[reportArgumentType]

        subs_idx_to_bus_id = {}
        for idx, sub in subs.iterrows():
            bus_id = sub_id_and_v_to_bus_id.get((sub.id, sub.voltage))
            bus_id = bus_id if bus_id in self.net.bus.index else None
            subs_idx_to_bus_id[idx] = bus_id

        subs["network_id"] = subs.index.map(subs_idx_to_bus_id).astype("Int16")

        subs.to_file(f"{config.EXPORT_DIR}/stats/substations.gpkg", driver="GPKG")

    def save_lines(self, model: Model):
        lines = model.lines.copy()

        subs = model.subs.set_index("id")

        lines["sub_1_name"] = lines.substation_1.apply(lambda s: subs.loc[s]["name"])
        lines["sub_2_name"] = lines.substation_2.apply(lambda s: subs.loc[s]["name"])

        lines["network_id"] = lines.id.map(line_osm_id_to_network_id)

        lines[~lines.network_id.isin(self.net.line.index)] = None

        lines.to_file(f"{config.EXPORT_DIR}/stats/lines.gpkg", driver="GPKG")

    # def save_cons(self, model: Model):
    #     # Also save relevant consumer data
    #     cons = model.cons[["gkz", "name", "geometry"]].set_index("gkz")
    #     cons.to_file(f"{config.EXPORT_DIR}/stats/consumers.gpkg", driver="GPKG")

    def process_buses(self):
        # Bus voltage
        bus_vm_pu = pd.read_csv(f"{self.raw_stats_dir}/res_bus/vm_pu.csv", sep=";", index_col=0)
        self._set_index_to_date(bus_vm_pu)

        buses = self.net.bus.index.astype(str)
        bus_vm = bus_vm_pu[buses]
        self._save_df(bus_vm, "bus_vm_pu.csv", "network_id")  # pyright: ignore[reportArgumentType]

        # Under/over voltages
        under_over_voltage_labels = [
            "num_undervoltages",
            "num_extreme_undervoltages",
            "num_overvoltages",
            "num_extreme_overvoltages",
        ]

        under_over_voltages = bus_vm_pu[under_over_voltage_labels]
        self._save_df(under_over_voltages, "under_over_voltages.csv", "category")  # pyright: ignore[reportArgumentType]

        # Bus voltage angle
        self._simple_process("res_bus/va_degree.csv", "bus_va_degree.csv", "network_id")

    def process_lines(self):
        self._simple_process("res_line/loading_percent.csv", "line_loading_percent.csv", "network_id")

        # Line current from
        # self._simple_process(f"res_line/i_from_ka.csv", "line_i_from_ka.csv", "network_id")

        # # Line current to
        # self._simple_process(f"res_line/i_to_ka.csv", "line_i_to_ka.csv", "network_id")

        # Line reactive loss
        self._simple_process("res_line/pl_mw.csv", "line_pl_mw.csv", "network_id")

        # Line reactive loss
        self._simple_process("res_line/ql_mvar.csv", "line_ql_mvar.csv", "network_id")

        # Line degree from
        self._simple_process("res_line/va_from_degree.csv", "line_va_from.csv", "network_id")

        # Line degree to
        self._simple_process("res_line/va_to_degree.csv", "line_va_to.csv", "network_id")

        # Line power to
        # self._simple_process(f"res_line/p_to_mw.csv", "line_p_to_mw.csv", "network_id")

        # # Line reactive power to
        # self._simple_process(f"res_line/q_to_mvar.csv", "line_q_to_mvar.csv", "network_id")

        # # Line power from
        # self._simple_process(f"res_line/p_from_mw.csv", "line_p_from_mw.csv", "network_id")

        # # Line reactive power from
        # self._simple_process(f"res_line/q_from_mvar.csv", "line_q_from_mvar.csv", "network_id")

    def process_power(self):
        # Load data
        total_load = pd.read_csv(f"{self.raw_stats_dir}/load/p_mw.csv", sep=";", index_col=0)
        total_load.rename(columns=int, inplace=True)
        self._set_index_to_date(total_load)

        total_gen = pd.read_csv(f"{self.raw_stats_dir}/gen/p_mw.csv", sep=";", index_col=0)
        total_gen.rename(columns=int, inplace=True)
        total_gen.rename(columns=self.net.gen.name.to_dict(), inplace=True)
        self._set_index_to_date(total_gen)

        total_sgen = pd.read_csv(f"{self.raw_stats_dir}/sgen/p_mw.csv", sep=";", index_col=0)
        total_sgen.rename(columns=int, inplace=True)
        total_sgen.rename(columns=self.net.sgen.name.to_dict(), inplace=True)
        self._set_index_to_date(total_sgen)

        # Seperate consumer load and export load
        is_export_load = self.net.load.name.str.contains("EXPORT")
        export_load_indices = is_export_load[is_export_load].index
        con_load_indices = is_export_load[~is_export_load].index

        # Save consumer load
        con_load = total_load[con_load_indices].copy()
        # load_id_to_gkz = {load_id: gkz for gkz, load_id in utils.gkz_to_load_id.items()}
        # con_load.rename(columns=load_id_to_gkz, inplace=True)
        # self._save_df(con_load, "consumer_load.csv", "gkz")

        # Save export
        export_load = total_load[export_load_indices].copy()
        export_load.rename(columns=self.net.load.name.to_dict(), inplace=True)  # pyright: ignore[reportCallIssue]
        export_load.rename(columns=lambda name: name.removeprefix("EXPORT (").removesuffix(")"), inplace=True)  # pyright: ignore[reportCallIssue]
        if not export_load_indices.empty:
            self._save_df(export_load, "export.csv", "country")  # pyright: ignore[reportArgumentType]

        # Seperate import from large generators
        import_gen_columns = list({c for c in total_gen.columns if "IMPORT" in c})
        large_gen_columns = list({c for c in total_gen.columns if "IMPORT" not in c})

        # Save import
        import_gen = total_gen[import_gen_columns].copy()
        if not import_gen.empty:
            import_gen.rename(columns=lambda name: name.removeprefix("IMPORT (").removesuffix(")"), inplace=True)  # pyright: ignore[reportCallIssue]
            self._save_df(import_gen, "import.csv", "country")  # pyright: ignore[reportArgumentType]

        # Merge large gen and sgen
        large_gen = total_gen[large_gen_columns].copy()
        all_gens = pd.concat([large_gen, total_sgen], axis=1)
        self._save_df(all_gens, "generation.csv", "generator_name")

        # Summary for each time stamp
        summary = pd.DataFrame(index=self.dates)  # pyright: ignore[reportArgumentType]
        summary["load"] = con_load.sum(axis=1)
        summary["export"] = export_load.sum(axis=1)
        summary["generation"] = all_gens.sum(axis=1)
        summary["import"] = import_gen.sum(axis=1)
        self._save_df(summary, "total_power.csv", "category")

    def _simple_process(self, filename: str, save_name: str, index_name: str) -> pd.DataFrame:
        filename = f"{self.raw_stats_dir}/{filename}"
        df = pd.read_csv(filename, sep=";", index_col=0)
        self._set_index_to_date(df)
        self._save_df(df, save_name, index_name)

        return df

    def _set_index_to_date(self, df: pd.DataFrame):
        df.index = df.index.map({i: date for i, date in enumerate(self.dates)})

    @staticmethod
    def _save_df(df: pd.DataFrame, name: str, index_name: str):
        df = df.T

        df.index.name = index_name

        save_dirs = [f"{config.EXPORT_DIR}/stats"]
        for dir in save_dirs:
            save_path = f"{dir}/{name}"
            df.to_csv(save_path)
