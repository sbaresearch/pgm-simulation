from datetime import datetime

from attack_scenario.attack_scenario import remove_attacked_elements
from datasources.ds_builder import DSBuilder
from importers.model_import import load_model
from network.pre_processor import preprocess_network
from network.static_network_builder import build_network
from stats.output_writer_handler import create_output_writer
from stats.process_stats import process_stats
from stats.summarize_stats import summarize_stats
from util import config
from util.tqdm_logger import pbar_date_postfix
from util.utils import suppress_matrix_rank_warnings, vprint
from visualization.network_graphs import create_top_graph, create_voltage_rating_graph
from visualization.pre_graphs import create_total_power_graph
from visualization.result_graphs import create_result_graphs


def run_simulations(dates: list[datetime], model_path: str):
    time_steps = range(len(dates))

    vprint("Importing model")
    model = load_model(model_path)

    if config.ATTACK_SCENARIO:
        vprint("Attacking selected elements")
        model = remove_attacked_elements(model)

    ds_builder = DSBuilder(dates, model)
    con_elwog_subs = ds_builder.get_subs_with_con()
    local_gen_elwog_subs = ds_builder.get_subs_with_local_gen()
    use_import_export = ds_builder.use_import_export()

    vprint("Creating pandapower network")
    net = build_network(model, con_elwog_subs, local_gen_elwog_subs, use_import_export)

    if config.GENERATE_NETWORK_MAPS:
        vprint("Creating topology graph of the network")
        create_top_graph(net, model)

    vprint("Processing static network")
    net = preprocess_network(net)
    ds_builder.update_from_net()

    if config.GENERATE_NETWORK_MAPS:
        vprint("Creating graph of the network before simulation")
        create_voltage_rating_graph(net)

    vprint("Creating datasources for temporal simulation data")
    datasources = ds_builder.load_datasources(model)
    net, controllers = ds_builder.create_controllers_from_ds(net, datasources)

    if config.GENERATE_PRE_MAP:
        vprint("Creating graph of the total network load")
        create_total_power_graph(net, controllers, dates)

    vprint("Registering statistics to collect")
    ow = create_output_writer(net, time_steps)

    vprint("\nRunning simulation(s):")
    patch_run_time_step()
    from pandapower.timeseries import run_timeseries

    with suppress_matrix_rank_warnings():
        run_timeseries(
            net,
            time_steps,
            continue_on_divergence=True,
            enforce_q_lims=config.ENFORCE_REACTIVE_LIMITS,
            calculate_voltage_angles=True,
            progress_function=pbar_date_postfix,
            run_control=config.USE_CONTROLLERS,
        )

    vprint("\nProcessing statistics")
    process_stats(net, dates, ow, model)

    if config.GENERATE_RESULT_MAP:
        vprint("\nCreating result graphs")
        create_result_graphs(net, dates)

    summarize_stats(dates)

    # Cleanup raw stats directory to save some memory
    from shutil import rmtree

    rmtree(str(config.RAW_STATS_DIR))


def patch_run_time_step():
    # Currently, run_time_step does not reset the _ppc on a failed run.
    # This leads to a poor _ppc that means consecutive runs will also fail.
    # This can be avoided by setting recycle=None, but this means no data will be recycled, even on successful runs.
    # This wrapper checks if the network converged, and if it didn't, it resets the _ppc, preparing it for a new run.
    import pandapower.timeseries.run_time_series as rts

    original = rts.run_time_step

    def wrapped(*args, **kwargs):
        net = args[0]
        try:
            return original(*args, **kwargs)
        finally:
            if net._ppc is not None and not net._ppc.get("success", False):
                net._ppc = None

    rts.run_time_step = wrapped
