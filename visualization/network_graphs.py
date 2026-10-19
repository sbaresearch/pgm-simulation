from shutil import copyfile

from pandapower.auxiliary import pandapowerNet
from pandapower.plotting.plotly import create_bus_trace
from pandapower.topology import connected_components, create_nxgraph

from util import config
from util.name_types import Model
from visualization.visualization_utils import (
    _create_branch_trace,
    bus_size,
    draw_traces,
    get_plotly_color_palette,
    line_width,
)


def create_top_graph(net: pandapowerNet, model: Model):
    """Plots the different disconencted islands in different colors."""

    mg = create_nxgraph(net)
    collections = []
    island_index = 0
    islands = list(connected_components(mg))  # getting connected components of a graph
    colors = get_plotly_color_palette(len(islands))  # getting a color for each connected component
    for color, area in zip(colors, islands):
        collections += create_bus_trace(net, area, size=int(bus_size), color=color, trace_name=f"island {island_index}")
        island_index += 1
    collections += _create_branch_trace(net, net.line.index, color="grey")

    if not net.ext_grid.empty:
        collections += create_bus_trace(
            net, net.ext_grid.bus.values, patch_type="square", size=17, color="yellow", trace_name="Slack Bus"
        )

    if isinstance(model, Model):
        external_buses = _get_external_buses(model)
        if external_buses:
            collections += create_bus_trace(
                net, external_buses, patch_type="square", color="cyan", size=17, trace_name="External Connection Points"
            )

    save_path = f"{config.EXPORT_DIR}/graphs/topology_graph.html"
    title = "Topology of model"
    draw_traces(collections, save_path, title, showlegend=True)

    # Copy to run specific folder
    copyfile(save_path, "results/graphs/topology_graph.html")


def _get_external_buses(model: Model) -> list[int]:
    from network.static_network_builder import sub_id_and_v_to_bus_id

    external_subs = model.subs[model.subs["type"].str.contains("import")]
    external_buses = []
    for sub in external_subs.itertuples():
        assert isinstance(sub.export_voltage, list)  # pyright: ignore[reportAttributeAccessIssue]
        for v in sub.export_voltage:  # pyright: ignore[reportAttributeAccessIssue]
            external_buses.append(sub_id_and_v_to_bus_id[sub.id, v])  # type: ignore

    return external_buses


def create_voltage_rating_graph(net: pandapowerNet):
    # ======= This was copied (and edited) from the pandapower function vlevel_plotly ======

    # getting connected componenets without consideration of trafos
    graph = create_nxgraph(net, include_trafos=False)
    vlev_buses = connected_components(graph)
    # getting unique sets of buses for each voltage level
    vlev_bus_dict = {}
    for vl_buses in vlev_buses:
        vn_kv = net.bus.loc[list(vl_buses), "vn_kv"].unique()[0]
        if vlev_bus_dict.get(vn_kv):
            vlev_bus_dict[vn_kv].update(vl_buses)
        else:
            vlev_bus_dict[vn_kv] = vl_buses

    # create a default colormap for voltage levels
    nvlevs = len(vlev_bus_dict)
    colors = get_plotly_color_palette(nvlevs)
    colors_dict = dict(zip(vlev_bus_dict.keys(), colors))
    bus_groups = [(buses, colors_dict[vlev], f"{vlev} kV") for vlev, buses in vlev_bus_dict.items()]

    # creating traces for buses and lines for each voltage level
    bus_traces = []
    line_traces = []
    traced_lines = set()
    for bus_group_legend in bus_groups:
        buses_vl, vlev_color, legend_group = bus_group_legend

        bus_trace_vlev = create_bus_trace(
            net,
            buses=buses_vl,
            size=bus_size,
            legendgroup=legend_group,
            color=vlev_color,
            trace_name=f"buses {legend_group}",
        )
        if bus_trace_vlev is not None:
            bus_traces += bus_trace_vlev

        vlev_lines = net.line[net.line.from_bus.isin(buses_vl) & net.line.to_bus.isin(buses_vl)].index.tolist()
        traced_lines |= set(vlev_lines)
        line_trace_vlev = _create_branch_trace(
            net,
            branches=vlev_lines,
            legendgroup=legend_group,
            color=vlev_color,
            width=line_width,
            trace_name=f"lines {legend_group}",
        )
        if line_trace_vlev is not None:
            line_traces += line_trace_vlev

    save_path = f"{config.EXPORT_DIR}/graphs/voltage_rating.html"
    title = "Voltage ratings of buses and lines"
    draw_traces(line_traces + bus_traces, save_path, title, showlegend=True)

    # Copy to run specific folder
    copyfile(save_path, "results/graphs/voltage_rating.html")
