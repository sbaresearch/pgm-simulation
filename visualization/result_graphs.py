from datetime import datetime
from shutil import copyfile

from pandapower.auxiliary import pandapowerNet
from pandapower.plotting.plotly import create_bus_trace
import pandas as pd

from util import config
from util.utils import vprint
from visualization.visualization_utils import _create_branch_trace, draw_traces, line_width, bus_size


def create_result_graphs(net: pandapowerNet, dates: list[datetime]):
    res_map_maker = ResultGraphsMaker(net, dates)
    res_map_maker.create_result_graphs()


class ResultGraphsMaker():
    net: pandapowerNet
    dates: list[datetime]
    time_range_str = str
    broken_sim: bool

    graph_data: dict[str, pd.Series]

    precision = 3

    required_data_names = [
        "bus_vm_pu",
        "bus_va_degree",
        "line_loading_percent",
        "line_ql_mvar",
        "line_va_from",
        "line_va_to",
    ]

    def __init__(self, net: pandapowerNet, dates: list[datetime]):
        self.broken_sim = False

        self.net = net
        self.time_range_str = f"{dates[0]}-{dates[-1]}"

        stat_dirs = f"{config.EXPORT_DIR}/stats"
        self.graph_data = {}
        for data_name in self.required_data_names:
            df = pd.read_csv(f"{stat_dirs}/{data_name}.csv", index_col=0).T.rename(columns=int)

            df = df[~(df.sum(axis=1) == 0)]
            if df.empty:
                self.broken_sim = True
                vprint("Cannot create result maps for simulation where all runs failed!")
                return

            # average data for all dates
            df = df.mean()

            self.graph_data[data_name] = df

    def create_result_graphs(self):
        if self.broken_sim:
            return

        vprint("\tCreating graph visualizing the voltage levels from the simulation results")
        self._create_vol_mag_graph()
        vprint("\tCreating graph visualizing voltage angle difference and voltage angle")
        self._create_vol_ang_graph()
        vprint("\tCreating graph visualizing the reactive power losses and voltage angle")
        self._create_reac_loss_graph()

    def _create_vol_mag_graph(self):
        vm = self.graph_data["bus_vm_pu"]
        va = self.graph_data["bus_va_degree"]

        loading = self.graph_data["line_loading_percent"]

        hoverinfo = (
            self.net.bus.name.astype(str) + '<br />' +
            'V_m = ' + vm.round(self.precision).astype(str) + ' pu' + '<br />' +
            'V_a = ' + va.round(self.precision).astype(str) + ' deg').tolist()
        hoverinfo = pd.Series(index=self.net.bus.index, data=hoverinfo)

        bus_trace = create_bus_trace(self.net, self.net.bus.index, cmap_vals=vm, size=bus_size, infofunc=hoverinfo,
                                     cmap="Jet", cbar_title='Bus Voltage [pu]', cmin=0.9, cmax=1.1)

        # ----- Lines ------
        hoverinfo = (self.net.line.name.astype(str) + '<br />' +
                     'I = ' + loading.round(self.precision).astype(str) + ' %' + '<br />').tolist()
        hoverinfo = pd.Series(index=self.net.line.index, data=hoverinfo)

        line_trace = _create_branch_trace(self.net, width=line_width, infofunc=hoverinfo, cmap="jet", cmap_vals=loading,
                                          cmin=0, cmax=100, cbar_title='Line Loading [%]', show_colorbar=True)

        # ----- Ext grid ------
        ext_grid_trace = create_bus_trace(self.net, buses=self.net.ext_grid.bus, color='grey', size=bus_size*2, trace_name='external_grid',
                                          patch_type='square')

        save_path = f"{config.EXPORT_DIR}/graphs/result_graphs/vol_mag_graph_{self.time_range_str}.html"
        title = f"Voltage levels and loading percentage {self.time_range_str}"
        draw_traces(line_trace+bus_trace+ext_grid_trace, save_path, title)

        # Copy to run specific folder
        copyfile(save_path, f"results/graphs/result_graphs/vol_mag_graph_{self.time_range_str}.html")

    def _create_reac_loss_graph(self):
        """Shows reactive loads on lines and voltage angle on buses."""
        vm = self.graph_data["bus_vm_pu"]
        va = self.graph_data["bus_va_degree"]

        loading = self.graph_data["line_loading_percent"]
        ql = self.graph_data["line_ql_mvar"]

        # ----- Buses ------
        hoverinfo = (
            self.net.bus.name.astype(str) + '<br />' +
            'V_m = ' + vm.round(self.precision).astype(str) + ' pu' + '<br />' +
            'V_m = ' + (vm * self.net.bus.vn_kv.round(2)).round(self.precision).astype(str) + ' kV' + '<br />' +
            'V_a = ' + va.round(self.precision).astype(str) + ' deg').tolist()
        hoverinfo = pd.Series(index=self.net.bus.index, data=hoverinfo)

        bus_trace = create_bus_trace(self.net, self.net.bus.index, cmap_vals=va, size=bus_size, infofunc=hoverinfo,
                                     cmap="Jet", cbar_title='Voltage angle [degrees]', cmax=45, cmin=-45)

        # ----- Lines ------
        hoverinfo = ('Q loss = ' + ql.round(self.precision).astype(str) + 'MVAR' + '<br />' +
                     'I = ' + loading.round(self.precision).astype(str) + ' %' + '<br />').tolist()
        hoverinfo = pd.Series(index=self.net.line.index, data=hoverinfo)

        line_trace = _create_branch_trace(self.net, width=line_width, infofunc=hoverinfo, cmap="jet", cmap_vals=ql,
                                          cbar_title='Reactive Power Loss [MVAR]', cmax=100, cmin=-100, show_colorbar=True)

        save_path = f"{config.EXPORT_DIR}/graphs/result_graphs/reac_loss_graph_{self.time_range_str}.html"
        title = f"Reactive loss and voltage angles on {self.time_range_str}"
        draw_traces(line_trace+bus_trace, save_path, title)

        # Copy to run specific folder
        copyfile(save_path, f"results/graphs/result_graphs/reac_loss_graph_{self.time_range_str}.html")

    def _create_vol_ang_graph(self):
        """Shows voltage angle change on lines and voltage angle on buses."""
        vm = self.graph_data["bus_vm_pu"]
        va = self.graph_data["bus_va_degree"]

        loading = self.graph_data["line_loading_percent"]
        ql = self.graph_data["line_ql_mvar"]
        va_to = self.graph_data["line_va_from"]
        va_from = self.graph_data["line_va_to"]

        # ----- Buses ------
        hoverinfo = (
            self.net.bus.name.astype(str) + '<br />' +
            'V_m = ' + vm.round(self.precision).astype(str) + ' pu' + '<br />' +
            'V_m = ' + (vm * self.net.bus.vn_kv.round(2)).round(self.precision).astype(str) + ' kV' + '<br />' +
            'V_a = ' + va.round(self.precision).astype(str) + ' deg').tolist()
        hoverinfo = pd.Series(index=self.net.bus.index, data=hoverinfo)

        bus_trace = create_bus_trace(self.net, self.net.bus.index, cmap_vals=va, size=bus_size, infofunc=hoverinfo,
                                     cmap="Jet", cbar_title='Voltage angle [degrees]', cmax=45, cmin=-45)

        # ----- Lines ------
        vol_ang_diff = (va_to-va_from).abs()
        hoverinfo = ('V_a diff = ' + vol_ang_diff.round(self.precision).astype(str) + 'degrees' + '<br />' +
                     'V_a to = ' + va_to.round(self.precision).astype(str) + 'degrees' + '<br />' +
                     'V_a from = ' + va_from.round(self.precision).astype(str) + 'degrees' + '<br />' +
                     'Q loss = ' + ql.round(self.precision).astype(str) + 'MVAR' + '<br />' +
                     'I = ' + loading.round(self.precision).astype(str) + ' %' + '<br />').tolist()
        hoverinfo = pd.Series(index=self.net.line.index, data=hoverinfo)

        line_trace = _create_branch_trace(self.net, width=line_width, infofunc=hoverinfo, cmap="YlOrRd", cmap_vals=vol_ang_diff,
                                          cbar_title='Voltage angle difference [degrees]', show_colorbar=True, cmin=0, cmax=15)

        save_path = f"{config.EXPORT_DIR}/graphs/result_graphs/vol_ang_graph_{self.time_range_str}.html"
        title = f"Voltage angles on {self.time_range_str}"
        draw_traces(line_trace+bus_trace, save_path, title)

        # Copy to run specific folder
        copyfile(save_path, f"results/graphs/result_graphs/vol_ang_graph_{self.time_range_str}.html")
