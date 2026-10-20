from datetime import datetime
from math import sqrt
from shutil import copyfile

import pandas as pd
from pandapower.auxiliary import pandapowerNet
from pandapower.control import ConstControl
from pandapower.plotting.plotly import create_bus_trace
from tqdm import tqdm

from util import config
from visualization.visualization_utils import _create_branch_trace, draw_traces, line_width


def create_total_power_graph(net: pandapowerNet, controllers: tuple[ConstControl, ...], dates: list[datetime]):
    # Confirm creating multiple maps for many dates
    if len(dates) > 4:
        print(f"\tMany dates were entered ({len(dates)}),")
        response = ""
        while response.lower() != "y":
            response = input("\tAre you sure you want to create total power graphs for each date? (y/n)\n")
            if response == "n":
                print("\tNot creating total load graphs")
                return

    line_trace = _create_branch_trace(net, net.line.index, width=line_width)  # Line trace does not change

    for i, date in tqdm(enumerate(dates)):
        # Apply network values for time step
        for controller in controllers:
            controller.time_step(net, i)

        from collections import defaultdict

        bus_data_by_geo: dict[object, list[BusData]] = defaultdict(list)

        # Reset bus data
        for bus in net.bus.itertuples():
            bus_data_by_geo[bus.geo].append(BusData(bus.Index))  # type: ignore

        # Add color and power to buses
        for buses in bus_data_by_geo.values():
            for bus in buses:
                connected_loads = net.load[net.load.bus == bus.index]
                if not connected_loads.empty:
                    power = connected_loads.p_mw.sum()
                    if power != 0:
                        bus.color += 0xFF0000
                        bus.power += power

                connected_sgens = net.sgen[net.sgen.bus == bus.index]
                if not connected_sgens.empty:
                    power = connected_sgens.p_mw.sum()
                    if power != 0:
                        bus.color += 0x00FF00
                        bus.power += power

                connected_gens = net.gen[net.gen.bus == bus.index]
                if not connected_gens.empty:
                    power = connected_gens.p_mw.sum()
                    if power != 0:
                        bus.color += 0x0000FF
                        bus.power += power

                # Gray out shunts
                connected_shunts = net.shunt[net.shunt.bus == bus.index]
                if not connected_shunts.empty:
                    bus.color |= 0x999999

                if bus.index in net.ext_grid.bus.values:
                    bus.color = 0x333333

        # Merge buses on same location
        bus_data: list[BusData] = [combine_buses(buses) for buses in bus_data_by_geo.values()]

        # Create groups of buses with same power and color
        from collections import defaultdict

        size_and_color_groups = defaultdict(list)
        for bus in bus_data:
            size_and_color_groups[(bus.color_to_str(), bus.power_to_size(), bus.power)].append(bus.index)

        # Now create one trace for each group of buses
        bus_traces = []
        for (color, size, power), bus_indices in size_and_color_groups.items():
            bus_names = net.bus.loc[bus_indices].name
            hoverinfo = (bus_names.astype(str) + "<br />" + f"Total load: {power:.2f}").tolist()
            hoverinfo = pd.Series(index=bus_indices, data=hoverinfo)
            bus_traces += create_bus_trace(net, bus_indices, size=size, color=color, infofunc=hoverinfo)

        save_path = f"{config.EXPORT_DIR}/graphs/total_power/total_power_{date}.html"
        title = "Total power and connected elements. RED=LOAD, GREEN=SGEN, BLUE=GEN, GRAY=SLACK\n" + f"Date: {date}"
        draw_traces(line_trace + bus_traces, save_path, title)

        # Copy to run specific folder
        copyfile(save_path, f"results/graphs/total_power/total_power_{date}.html")


class BusData:
    """
    Helper class for storing information about substations.
    """

    index: int
    color: int
    power: float

    def __init__(self, index: int):
        self.index = index
        self.color = 0
        self.power = 0.0

    def color_to_str(self) -> str:
        # slightly cryptic was of getting a leading zeros hex value without 0x
        hex_value_as_str = f"{self.color:#0{8}x}"[2:]
        return f"#{hex_value_as_str}"

    def power_to_size(self) -> int:
        return max(4, 2 * int(sqrt(self.power)))
        # return max(4, min(40, int(self.power//10)))


def combine_buses(buses: list[BusData]) -> BusData:
    if len(buses) == 1:
        return buses[0]

    new_bus = BusData(buses[0].index)
    for bus in buses:
        if bus.color == 0x333333:  # Keep slack buses gray only
            new_bus.color = bus.color
            break

        new_bus.color |= bus.color

    new_bus.power = sum([bus.power for bus in buses])

    return new_bus
