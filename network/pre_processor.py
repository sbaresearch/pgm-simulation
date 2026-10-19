import pandapower as pp
from networkx import closeness_centrality
from pandapower.auxiliary import pandapowerNet
from pandapower.control import DiscreteShuntController, DiscreteTapControl
from pandapower.toolbox import drop_elements, select_subnet
from pandapower.topology import create_nxgraph

from network import static_network_builder
from network.static_network_builder import vm_setpoints


def preprocess_network(net: pandapowerNet) -> pandapowerNet:
    net = _remove_islands(net)

    _update_network_id_dicts(net)

    _reindex_buses(net)

    # Create at least one ext_grid if all were removed
    if net.ext_grid.empty:
        _add_slack(net)

    return net


def _remove_islands(net: pandapowerNet) -> pandapowerNet:
    """Keep only largest connected island"""
    from pandapower.topology import connected_components, create_nxgraph

    graph_representation = create_nxgraph(net)
    components = list(connected_components(graph_representation))

    # sort by size, largest first
    components_sorted = sorted(components, key=len, reverse=True)
    largest_component = components_sorted[0]

    # extract subnet corresponding to the largest cluster (options don't need to be true in this case, but doesn't hurt, I think.)
    largest_connected_subnet = select_subnet(
        net, buses=largest_component, include_switch_buses=True, include_results=True, keep_everything_else=True
    )

    net = largest_connected_subnet
    return net


def _update_network_id_dicts(net: pandapowerNet):
    # Update lists of pv gens and pq gens to only include gens in the network after removing islands
    pv_gen_ids, pv_gen_id_to_net_id = static_network_builder.pv_gen_ids, static_network_builder.pv_gen_id_to_net_id
    static_network_builder.pv_gen_ids = [pv_id for pv_id in pv_gen_ids if pv_gen_id_to_net_id[pv_id] in net.gen.index]
    pq_gen_ids, pq_gen_id_to_net_id = static_network_builder.pq_gen_ids, static_network_builder.pq_gen_id_to_net_id
    static_network_builder.pq_gen_ids = [pq_id for pq_id in pq_gen_ids if pq_gen_id_to_net_id[pq_id] in net.sgen.index]

    # Also remove missing loads
    static_network_builder.elwog_id_to_load_id = {
        elwog_id: load_id
        for elwog_id, load_id in static_network_builder.elwog_id_to_load_id.items()
        if load_id in net.load.index
    }

    # Also remove missing comunity solar generation
    static_network_builder.elwog_id_to_local_sgen_id = {
        elwog_id: sgen_id
        for elwog_id, sgen_id in static_network_builder.elwog_id_to_local_sgen_id.items()
        if sgen_id in net.sgen.index
    }

    # Also remove missing import/export
    export_country_to_load_ids = {
        country: [load_id for load_id in load_ids if load_id in net.load.index]
        for country, load_ids in static_network_builder.export_country_to_load_ids.items()
    }
    static_network_builder.export_country_to_load_ids = {
        country: load_ids for country, load_ids in export_country_to_load_ids.items() if load_ids
    }

    export_country_to_gen_ids = {
        country: [gen_id for gen_id in gen_ids if gen_id in net.gen.index]
        for country, gen_ids in static_network_builder.export_country_to_gen_ids.items()
    }
    static_network_builder.export_country_to_gen_ids = {
        country: gen_ids for country, gen_ids in export_country_to_gen_ids.items() if gen_ids
    }


def _reindex_buses(net: pandapowerNet):
    import pandapower.toolbox as tb

    tb.create_continuous_bus_index(net, store_old_index=True)

    # Update sub_id_and_vol_to_bus_id for new indicies
    new_index_to_old_index = net.bus.old_index.to_dict()
    old_to_new = {old: new for new, old in new_index_to_old_index.items()}

    # remove the id for buses that were removed from the network
    sub_id_and_v_to_bus_id = {
        key: old_id for key, old_id in static_network_builder.sub_id_and_v_to_bus_id.items() if old_id in old_to_new
    }
    static_network_builder.sub_id_and_v_to_bus_id = {
        (sub_id, vol): old_to_new[old_id] for (sub_id, vol), old_id in sub_id_and_v_to_bus_id.items()
    }

    # Update ssc buses (not updated automatically for some reason)
    net.ssc["bus"] = net.ssc.bus.map(old_to_new)
    removed_sscs = net.ssc[net.ssc.bus.isna()].index
    drop_elements(net, "ssc", removed_sscs)
    net.ssc["bus"] = net.ssc.bus.astype(int)

    # Also need to update the shunt controller buses and delete controllers on deleted trafos
    tap_controllers_to_remove = []
    for i, controller in enumerate(net.controller.object):
        if isinstance(controller, DiscreteShuntController):
            controller.controlled_bus = old_to_new[controller.controlled_bus]
        elif isinstance(controller, DiscreteTapControl) and controller.element_index not in net.trafo.index:
            tap_controllers_to_remove.append(i)

    drop_elements(net, "controller", tap_controllers_to_remove)


def _add_slack(net: pandapowerNet):
    # Find bus with highest closeness centrality value and set as slack
    G = create_nxgraph(net, calc_branch_impedances=True)
    cent = closeness_centrality(G, distance="z_ohm")

    potential_buses = _find_potential_slack_buses(net)
    cent = {bus: v for bus, v in cent.items() if bus in potential_buses}

    central_bus = max(cent, key=lambda k: cent[k])
    pp.create_ext_grid(net, central_bus, vm_pu=vm_setpoints[net.bus.vn_kv.max()])

    # Change any gens on this bus to sgens (don't want two voltage controlling elements on same bus)
    gens_on_bus = net.gen[net.gen.bus == central_bus].index
    if not gens_on_bus.empty:
        from pandapower.toolbox import replace_gen_by_sgen

        replace_gen_by_sgen(net, gens_on_bus)

        # update pv and pq lists
        osm_ids = gens_on_bus.map(
            {net_id: gen_id for gen_id, net_id in static_network_builder.pv_gen_id_to_net_id.items()}
        ).to_list()
        static_network_builder.pv_gen_ids = [
            pv_id for pv_id in static_network_builder.pv_gen_ids if pv_id not in osm_ids
        ]
        static_network_builder.pq_gen_ids.extend(osm_ids)


def _find_potential_slack_buses(net: pandapowerNet) -> list[int]:
    # Don't want to put slack on import buses, buses with sscs, or virtual buses
    import_buses = net.gen[net.gen.name.str.contains("IMPORT")].bus.to_list()
    ssc_buses = net.ssc.bus.to_list()
    virtual_buses = net.bus[net.bus.name.str.contains("virtual")].index.to_list()
    no_go_buses = [*import_buses, *ssc_buses, *virtual_buses]

    potential_buses = [bus for bus in net.bus.index if bus not in no_go_buses]
    potential_buses_df = net.bus.loc[potential_buses]

    # Only consider buses with highest voltage level
    potential_buses = potential_buses_df[potential_buses_df.vn_kv == potential_buses_df.vn_kv.max()].index

    return potential_buses
