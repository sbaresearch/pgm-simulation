from math import copysign
from typing import cast

import numpy as np
import pandapower as pp
from pandapower import control
from pandapower.auxiliary import pandapowerNet

from util import config
from util.name_types import Model
from util.utils import AUSTRIA_CRS, CRS, elwog_id_to_name

slack_substation_ids: list[int] = [
    138407044,  # Umspannwerk Simmering
    1051033055,  # Umspannwerk Pongau
]

# Taken from different sources
ssc_buses: list[tuple[int, int]] = [
    (105065132, 220),  # Salzburg
    (89985993, 220),  # Pyhrn
    (27795895, 380),  # Wien Südost
    (81540198, 380),  # St. Peter
    (101997887, 380),  # Bürs
]

transformer_std_type: dict[tuple[int, int], str] = {
    (380000, 220000): "simbench_380_220",
    (380000, 110000): "160 MVA 380/110 kV",
    (220000, 110000): "100 MVA 220/110 kV",
}

line_std_type: dict[int, str] = {
    110000: "490-AL1/64-ST1A 110.0",  # TODO: find better value. I just picked this one at random.
    220000: "line_220",
    380000: "line_380",
}

vm_setpoints = {110: 1.00, 220: 1.01, 380: 1.02}

elwog_id_to_bus_id = {}
elwog_id_to_load_id = {}
elwog_id_to_local_sgen_id = {}

line_osm_id_to_network_id = {}

sub_id_and_v_to_bus_id = {}

pv_gen_id_to_net_id = {}
pq_gen_id_to_net_id = {}
hydro_pump_osm_id_to_load_id = {}

export_country_to_load_ids = {}
export_country_to_gen_ids = {}

pv_gen_ids = []
pq_gen_ids = []


def build_network(
    model: Model, con_elwog_subs: list[int], local_gen_elwog_subs: list[int], use_import_export: bool
) -> pandapowerNet:
    _reset_network_data()

    net = pp.create_empty_network()

    from network.network_parameters import initialize_standard_types

    initialize_standard_types(net)

    # Create a bus for each voltage level in every sub.
    # Also creates a transformer between buses of different voltage levels on the same substation.
    net = _add_buses(net, model)

    # Adds a gen for the largest ten generators, and a sgen for the rest.
    # Connects to the bus with the highest voltage on the substation.
    net = _add_gens(net, model)

    # Adds a line connection for each line. Connects buses based on line voltage level.
    net = _add_lines(net, model)

    # Adds all consumers as loads
    net = _add_loads(net, con_elwog_subs)

    # Add local generators
    if local_gen_elwog_subs:
        net = _add_local_gens(net, local_gen_elwog_subs)

    # Adds import/export buses as both loads and gens
    if use_import_export:
        net = _add_import_export(net, model)

    # Adding sscs where they have been found (manually) to exist.
    net = _add_sscs(net, model)

    # Adding shunts to 380 buses with a 220 transformer, and to some 220 buses with a 110 transformer
    # net = _add_shunts(net, model)

    # Some shunts places simply based on looking where reactive load is often missing
    # net = _add_shunts_manual(net, model)

    # Sets the highest voltage bus on the substation with id=self.slack_substation_id to the
    # slack bus (or "external grid" in pandapower).
    net = _set_slack_bus(net, model)

    return net


def build_simple_network(model: Model) -> pandapowerNet:
    _reset_network_data()

    net = pp.create_empty_network()

    from network.network_parameters import initialize_standard_types

    initialize_standard_types(net)

    # Create a bus for each voltage level in every sub.
    # Also creates a transformer between buses of different voltage levels on the same substation.
    net = _add_buses(net, model)

    # Adds a line connection for each line. Connects buses based on line voltage level.
    net = _add_lines(net, model)

    return net


def _reset_network_data():
    elwog_id_to_bus_id.clear()
    elwog_id_to_load_id.clear()
    elwog_id_to_local_sgen_id.clear()
    line_osm_id_to_network_id.clear()
    sub_id_and_v_to_bus_id.clear()
    pv_gen_id_to_net_id.clear()
    pq_gen_id_to_net_id.clear()
    hydro_pump_osm_id_to_load_id.clear()
    export_country_to_load_ids.clear()
    export_country_to_gen_ids.clear()


def _add_buses(net: pandapowerNet, model: Model) -> pandapowerNet:
    subs = model.subs.copy()
    subs["voltage"] = subs.voltage.apply(sorted)
    # Explode into one row per voltage level (keeping old index as column "sub_index")
    buses = subs.explode("voltage").reset_index(drop=True)

    # Only keep elwog id for bus with lowest voltage
    lowest_voltage_elwog_buses = buses.groupby("elwog_id")["voltage"].idxmin()
    buses.loc[~buses.index.isin(lowest_voltage_elwog_buses), "elwog_id"] = None

    # Create unique names for the buses
    virtual_buses = buses[buses["type"].str.contains("virtual") | buses["type"].str.contains("missing")]
    virtual_buses_without_name = virtual_buses[virtual_buses.name.isna()]  # pyright: ignore[reportAttributeAccessIssue]
    buses.loc[virtual_buses_without_name.index, "name"] = "virtual_substation"  # pyright: ignore[reportAttributeAccessIssue]
    buses.loc[buses[buses.name.isna()].index, "name"] = "missing_name_substation"

    counts = buses.groupby("name").cumcount() + 1  # type: ignore
    counts = counts[buses.name.duplicated(keep=False)]
    buses.loc[counts.index, "name"] = buses.loc[counts.index].name.astype(str) + "_" + counts.astype(str)

    # Find centroid point of buses
    buses.to_crs(AUSTRIA_CRS, inplace=True)
    buses["geometry"] = buses.geometry.centroid
    buses.to_crs(CRS, inplace=True)
    buses["point"] = buses.geometry.apply(lambda x: x.coords[0])

    # Batch create buses (200x faster than iteration)
    buses["bus_index"] = pp.create_buses(
        net, len(buses), buses.voltage / 1000, name=buses.name, geodata=buses.point.to_list()
    )

    # Save which elwog id is represented by which bus
    for bus in buses.itertuples():
        if bus.elwog_id is None:  # pyright: ignore[reportAttributeAccessIssue]
            continue
        elwog_id_to_bus_id.update({elwog_id: bus.bus_index for elwog_id in bus.elwog_id})  # type: ignore

    _sub_id_and_v_to_bus_id = {
        (cast(int, bus.id), cast(int, bus.voltage)): cast(int, bus.bus_index)  # pyright: ignore[reportAttributeAccessIssue]
        for bus in buses.itertuples()  # pyright: ignore[reportAttributeAccessIssue]
    }

    # Create transformers between buses on the same substation  NOTE: batch creation does not work (does not properly initialize trafos)
    for sub in subs[subs.voltage.apply(len) > 1].itertuples():
        voltages = sorted(sub.voltage)  # type: ignore
        c = [(voltages[i], voltages[i + 1]) for i in range(len(voltages))[:-1]]
        for v1, v2 in c[:2]:  # on buses with 110, 220, and 380, do not create transformers between 380 and 220
            std_type = transformer_std_type[(v2, v1)]
            hv_bus = _sub_id_and_v_to_bus_id[cast(int, sub.id), v2]  # pyright: ignore[reportAttributeAccessIssue]
            lv_bus = _sub_id_and_v_to_bus_id[cast(int, sub.id), v1]  # pyright: ignore[reportAttributeAccessIssue]
            trafo = pp.create_transformer(net, hv_bus, lv_bus, std_type=std_type)

            # if v1==110000 and v2==220000:
            # control.ContinuousTapControl(net=self.net, element_index=trafo, vm_set_pu=1.01, side="hv", in_service=True)
            control.DiscreteTapControl(
                net=net, element_index=trafo, side="hv", vm_lower_pu=0.97, vm_upper_pu=1.03, level=1
            )

    sub_id_and_v_to_bus_id.update(_sub_id_and_v_to_bus_id)

    return net


def _add_shunts(net: pandapowerNet, model: Model) -> pandapowerNet:
    # Add shunts to 380kV buses with a transformer to a 220kV buses
    shunt_buses = net.trafo[((net.trafo.vn_hv_kv == 380) & (net.trafo.vn_lv_kv == 220))].hv_bus.to_list()
    # Do not include shunts on buses that already have a PV node
    shunt_buses = [bus for bus in shunt_buses if bus not in net.gen.bus]
    potential_shunt_buses = net.trafo[((net.trafo.vn_hv_kv == 220) & (net.trafo.vn_lv_kv == 110))].hv_bus.to_list()

    # Add shunts on 220 kV buses with a transformer to 110kV, that are (electrically) far away from other shunts
    import networkx as nx
    from pandapower.topology import create_nxgraph

    G = create_nxgraph(net, calc_branch_impedances=True)

    lengths = dict(nx.all_pairs_dijkstra_path_length(G, weight="z_ohm"))

    for bus in potential_shunt_buses:
        dist_to_shunt = min([lengths[bus][shunt_bus] for shunt_bus in shunt_buses])
        if dist_to_shunt > 40:
            shunt_buses.append(bus)

    names = net.bus.loc[shunt_buses].copy().name.to_list()
    absorber_names = [f"Shunt reactor on bus {name}" for name in names]
    injector_names = [f"Capacitor bank on bus {name}" for name in names]

    absorbers = pp.create_shunts(net, shunt_buses, q_mvar=10, max_step=50, step=0, name=absorber_names)
    injecters = pp.create_shunts(net, shunt_buses, q_mvar=-10, max_step=50, step=0, name=injector_names)

    for shunt in np.concat((absorbers, injecters)):
        v = vm_setpoints[net.bus.loc[shunt].vn_kv]
        control.DiscreteShuntController(net, shunt, vm_set_pu=v, tol=0.01, level=0)

    return net


def _add_shunts_manual(net: pandapowerNet, model: Model) -> pandapowerNet:
    # NOTE: these were chosen completely arbitrarily, because the sit at buses that normally have a low voltage level
    # and the q_mvar values are also just chosen to work
    shunt_subs = [
        (145583866, 220, -200),  # Umspannwerk Vill
        (33003245, 220, -200),  # Umspannwerk Hagenau
        (83529203, 380, -100),  # Umspannwerk Werben - Dornbirn
        (102151229, 110, -100),  # Umspannwerk Reitdorf
        (95743675, 110, -100),  # Umspannwerk Pfandl
        (27797285, 380, -100),  # Umspannwerk Pottenbrunn
        (27673934, 380, -100),  # Umspannwerk Kendlerstraße
        (83202471, 220, -200),  # Umspannwerk Ternitz
        (88680218, 220, -200),  # Umspannwerk Hessenberg
        #   (27763479,   110, -100),  # Ernsthofen
        #   (1371916408, 110, -200),  # Traunfall
        #   (24830381,   110, -100),  # Linz-Nord
        #   (93215114,   110, -50),   # Eichet
        #   (1413960985, 110, -50),   # Poysdorf
        #   (146978108,  110, -50),   # Graz Gösting/Nord
        #   (83823298,   110,  50),   # Außerfragant
        #   (1036849480, 110,  50),   # Bruckneudorf
        #   (1344305292, 110,  50),   # No name by Mistelbach
        #   (27719234,   110, -100),  # Baumkirchen
        #   (32674497,   110, -100),  # Umspannwerk Wilten
        #   (23899163,   110, -100),  # Umspannwerk Kirchbichl
        #   (97348720,   110, -100),  # Umspannwerk Treibach
        #   (146122262,  110, -100),  # Schaltwerk Schönberg
        #   (28596524,   220, -100),  # Schaltanlage Mayrhofen
        # Import/export support
        #   (82201785,   110, -50),   # Neusiedl
        #   (96616299,   110, -50),   # Neusiedl an der Zaya
        #   (59531071,   110, -50),   # Dürnrohr
        #   (95975628,   110, -50),   # Aigerding
        #   (26703085,   110, -50),   # Reutte
        #   (101997887,  110, -50),   # Bürs
    ]

    for sub, vol, q_mvar in shunt_subs:
        bus = sub_id_and_v_to_bus_id.get((sub, vol * 1000))
        if bus is None:
            continue
        name = f"Shunt at {net.bus.name.loc[bus]}, {vol}"
        step_size = copysign(10, q_mvar)

        shunt = pp.create_shunt(net, bus, q_mvar=step_size, max_step=50, step=int(q_mvar // step_size), name=name)
        control.DiscreteShuntController(
            net, shunt, vm_setpoints[vol], tol=0.04, check_step_bounds=False, bus_index=bus, name=name, level=1
        )

    return net


def _add_sscs(net: pandapowerNet, model: Model) -> pandapowerNet:
    # Add sscs at specified locations
    ssc_buses_in_net = [(ssc_bus, v) for (ssc_bus, v) in ssc_buses if ssc_bus in model.subs.id.to_list()]
    for sub, vol in ssc_buses_in_net:
        bus = sub_id_and_v_to_bus_id[sub, vol * 1000]

        sub_name = model.subs.set_index("id").loc[sub]["name"]

        # TODO: very random impedance values
        pp.create_ssc(
            net,
            bus,
            name=f"SSC at {sub_name} ({vol})",
            controllable=True,
            in_service=True,
            r_ohm=1.21,
            x_ohm=24.2,
            set_vm_pu=vm_setpoints[vol],
            vm_internal_pu=vm_setpoints[vol],
        )

    return net


def _add_gens(net: pandapowerNet, model: Model) -> pandapowerNet:
    gens = model.gens.copy()

    # Find generator voltage (max voltage of sub where gen is connected)
    def get_max_voltage_from_sub_id(sub_id):
        return max(model.subs[model.subs.id == sub_id].voltage.iloc[0])

    gens["voltage"] = gens.substation_id.apply(get_max_voltage_from_sub_id)

    # Find connecting bus
    def get_bus_from_gen(gen):
        return sub_id_and_v_to_bus_id[cast(int, gen.substation_id), cast(int, gen.voltage)]

    gens["bus"] = gens.apply(get_bus_from_gen, axis=1)

    # Set name for gens without a name
    gens.loc[gens[gens.name.isna()].index, "name"] = "no name generator"

    gens["output_mw"] = gens.output_w / 1e6
    gens["vm_pu"] = (gens.voltage / 1000).map(vm_setpoints)

    # Create loads for hydro pumped storage
    hydro_pump_storage_gens = gens[gens.source == "Hydro Pumped Storage"]
    names = [f"{name} hydro pump storage" for name in hydro_pump_storage_gens.name]  # pyright: ignore[reportGeneralTypeIssues]
    load_ids = pp.create_loads(net, hydro_pump_storage_gens.bus.to_list(), 0, q_mvar=0, name=names)
    hydro_pump_osm_id_to_load_id.update(
        {osm_id: load_id for osm_id, load_id in zip(hydro_pump_storage_gens.id.to_list(), load_ids)}
    )

    # Split generators into pv (gens), and pq (sgen). Only the largest generators and import are allowed to be pv
    v_controlled_subs = gens.substation_id.isin([*slack_substation_ids, *[sub for sub, v in ssc_buses]])
    non_v_controlled_gens = gens[~v_controlled_subs].sort_values("output_mw", ascending=False)  # pyright: ignore[reportCallIssue]
    non_v_controlled_gens = non_v_controlled_gens[~non_v_controlled_gens.substation_id.duplicated()]

    potential_pv_sources = [
        "Gas",
        "Hydro Run-of-river",
        "Hydro Water Reservoir",
        "Hydro Pumped Storage",
        "Waste",
        "Biomass",
    ]
    potential_gens = non_v_controlled_gens[non_v_controlled_gens.source.isin(potential_pv_sources)]

    largest_gens = potential_gens.index[: config.NUM_PV_GENS]  # pyright: ignore[reportAttributeAccessIssue]

    pv_gens = gens.loc[largest_gens].copy()
    pq_gens = gens[~gens.index.isin(largest_gens)].copy()
    pv_gen_ids.extend(pv_gens.id.to_list())
    pq_gen_ids.extend(pq_gens.id.to_list())

    ##### Set up PV gens (gens) #####

    # Set min_q_mvar and max_q_mvar paremters (unused normally)
    pv_gens["min_q_mvar"] = pv_gens.output_mw * -1
    pv_gens["max_q_mvar"] = pv_gens.output_mw * 1

    net_ids = pp.create_gens(
        net,
        pv_gens.bus.to_list(),
        p_mw=0,
        vm_pu=pv_gens.vm_pu,
        name=pv_gens.name,
        min_q_mvar=pv_gens.min_q_mvar,
        max_q_mvar=pv_gens.max_q_mvar,
    )

    pv_gen_id_to_net_id.update({gen_id: net_id for gen_id, net_id in zip(pv_gens.id.to_list(), net_ids)})

    ##### Set up PQ gens (sgens) #####

    net_ids = pp.create_sgens(net, pq_gens.bus.to_list(), p_mw=0, q_mvar=0, name=pq_gens.name)  # pyright: ignore[reportArgumentType]

    pq_gen_id_to_net_id.update({gen_id: net_id for gen_id, net_id in zip(pq_gens.id.to_list(), net_ids)})

    return net


def _add_lines(net: pandapowerNet, model: Model) -> pandapowerNet:
    """Adds all lines of each std_type in one command to improve performance."""
    lines = model.lines.copy()

    # Find connecting bus
    def get_bus_1_from_line(line):
        return sub_id_and_v_to_bus_id[cast(int, line.substation_1), cast(int, line.voltage)]

    def get_bus_2_from_line(line):
        return sub_id_and_v_to_bus_id[cast(int, line.substation_2), cast(int, line.voltage)]

    lines["from_bus"] = lines.apply(get_bus_1_from_line, axis=1)
    lines["to_bus"] = lines.apply(get_bus_2_from_line, axis=1)

    # Set name for gens without a name
    lines.loc[lines[lines.name.isna()].index, "name"] = "no name line"

    # Get geometry of line as a list of coordinates
    lines["point"] = lines.geometry.apply(lambda x: x.coords[:])

    # Fix line circuits
    lines["circuits"] = lines.circuits.fillna(1).astype(int)

    _line_osm_id_to_network_id = {}
    for voltage, group in lines.groupby("voltage"):
        std_type = line_std_type[cast(int, voltage)]
        line_ids = pp.create_lines(
            net,
            group.from_bus.to_list(),
            group.to_bus.to_list(),
            group["length"] / 1000,
            std_type,
            group.name,
            parallel=group.circuits,
            geodata=group.point.to_list(),
        )

        group_map = {osm_id: network_id for osm_id, network_id in zip(group.id.to_list(), line_ids)}
        _line_osm_id_to_network_id.update(group_map)

    line_osm_id_to_network_id.update(_line_osm_id_to_network_id)

    return net


def _add_loads(net: pandapowerNet, con_elwog_subs: list[int]) -> pandapowerNet:
    elwog_subs_in_net = [elwog_id for elwog_id in con_elwog_subs if elwog_id in elwog_id_to_bus_id]
    buses = [elwog_id_to_bus_id[elwog_id] for elwog_id in elwog_subs_in_net]
    names = [elwog_id_to_name[elwog_id] for elwog_id in elwog_subs_in_net]

    load_ids = pp.create_loads(net, buses, 0, q_mvar=0, name=names)

    # Save which load id represents each elwog id with consumption
    elwog_id_to_load_id.update({elwog_id: load_id for elwog_id, load_id in zip(elwog_subs_in_net, load_ids)})

    return net


def _add_local_gens(net: pandapowerNet, local_gen_elwog_subs: list[int]) -> pandapowerNet:
    elwog_subs_in_net = [elwog_id for elwog_id in local_gen_elwog_subs if elwog_id in elwog_id_to_bus_id]
    buses = [elwog_id_to_bus_id[elwog_id] for elwog_id in elwog_subs_in_net]
    names = [f"Solar and wind power at {elwog_id_to_name[elwog_id]}" for elwog_id in elwog_subs_in_net]

    sgen_ids = pp.create_sgens(net, buses, p_mw=0, q_mvar=0, name=names)

    # Save which sgen id represents each elwog id with generation
    elwog_id_to_local_sgen_id.update({elwog_id: load_id for elwog_id, load_id in zip(local_gen_elwog_subs, sgen_ids)})

    return net


def _add_import_export(net: pandapowerNet, model: Model) -> pandapowerNet:
    subs = model.subs

    for country, import_subs in subs.groupby("export_country"):
        if not isinstance(country, str):  # Skip None
            continue

        def find_import_buses(sub):
            return [sub_id_and_v_to_bus_id[sub.id, v] for v in sub.export_voltage]

        import_buses = import_subs.apply(find_import_buses, axis=1)
        import_buses = [bus for bus_list in import_buses.to_list() for bus in bus_list]

        gen_ids = pp.create_gens(net, import_buses, p_mw=0, name=f"IMPORT ({country})")

        load_ids = pp.create_loads(net, import_buses, p_mw=0, q_mvar=0, name=f"EXPORT ({country})")

        export_country_to_gen_ids[country] = list(gen_ids)
        export_country_to_load_ids[country] = list(load_ids)

    return net


def _set_slack_bus(net: pandapowerNet, model: Model) -> pandapowerNet:
    subs = model.subs.set_index("id")
    for slack_substation_id in slack_substation_ids:
        if slack_substation_id not in subs.index:
            continue

        slack_sub = subs.loc[slack_substation_id]
        voltage = max(slack_sub.voltage)
        bus = sub_id_and_v_to_bus_id[slack_sub.name, voltage]
        pp.create_ext_grid(net, bus, vm_pu=vm_setpoints[voltage / 1000])

    return net
