from datetime import datetime

from simulation import run_simulations
from util import config
from util.utils import (
    create_results_dir,
    get_model_path,
    get_simulation_options,
    get_simulation_settings,
    is_wind_local,
    vprint,
)

# TODO: remove any reference to nurzu!


def profile_simulations(dates: list[datetime], model_path: str):
    import cProfile
    import io
    import pstats

    pr = cProfile.Profile()
    pr.enable()

    run_simulations(dates, model_path)

    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).strip_dirs().sort_stats("cumtime")
    ps.print_stats(30)  # Only print top 30 lines
    print(s.getvalue())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Perform a load flow analysis using a Model object created using "pgm-model-builder"'
        + "Can run simulations on the high and extra high voltage grid of Austria."
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Prints extra information about the process. Only prints warnings if false.",
    )
    parser.add_argument(
        "-d",
        "--date",
        type=str,
        help="Specify a date or time range. Format YYYY-MM-DDTHH. Only 2022 dates are available.\n"
        + "Specify a specific hour to run a single simulation. "
        + 'To run multiple simulations, specify a day, month or year, or supply an end date, separated with "/".\n'
        + "Examples:\n"
        + "Single simulation: 2022-03-17T06, 2022-08-25T14\n"
        + "Multiple simulations: 2022, 2022-08, 2022-08-25, 2022-08-24T18/2022-08-25T06 (2022-08 is the same as 2022-08/2022-09)\n"
        + "Default: 2022-03-17T06",
        default="2022-03-17T06",
    )
    parser.add_argument(
        "-s",
        "--scenario",
        type=str,
        help="Path to scenario folder containing AT LEAST the files:\n"
        + "'stdEinspeisung_MW.csv' describing the generation at the ELWOG substations for each hour in MW.\n"
        + "'stdNetzbedarf_MW.csv' describing the consumption at the ELWOG substations for each hour in MW.\n"
        + "Additionally, if data is available, the following files can also be provided:\n"
        "'total_actual_load.csv' describing the total load for each hour in MW. \n"
        + "'generation_per_source.csv' describing the total actual power generation per generation source per hour in MW. \n"
        + "'power_import_export.csv' describing the total import/export per country per hour in MW. \n"
        + "Default: data/scenarios/status_quo_2022.",
        default="",
    )
    parser.add_argument(
        "-a",
        "--attack_path",
        type=str,
        help="Set to enable an attack scenario. Leave empty to run a normal (non-attack) scenario. \n"
        + "Should be a path to a file describing the scenario, in a .json format. "
        "Can remove:"
        " substations using OSM ID"
        " lines using modified OSM ID in the model file",
        default="",
    )
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        help="Name of the directory where the results are placed. The directory is put in the results folder. "
        "Default: time of execution.",
        default=None,
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        help="Path to model file to use. Default: Most recent model in the data/model dir (based on model name).",
    )
    parser.add_argument("-p", "--profile", action="store_true", help="Enable profiling with cProfile")
    parser.add_argument(
        "-rl",
        "--reac_lims",
        action="store_true",
        help="Enforce reactive limits on generators if enabled. (Although the limits are kind of random)",
    )
    parser.add_argument(
        "-xc",
        "--no_controllers",
        action="store_true",
        help="Whether to not use controllers (automatic tap change, automatic phase shift, etc.).",
    )
    parser.add_argument(
        "-nm",
        "--network_maps",
        action="store_true",
        help="Creates maps showing the topology of the model as well as the lines and buses of the main island.",
    )
    parser.add_argument(
        "-pm",
        "--pre_maps",
        action="store_true",
        help="Creates a map showing the total load on the loads.",
    )
    parser.add_argument(
        "-rm",
        "--result_map",
        action="store_true",
        help="Creates a map showing the voltage level of the buses and the load level of the lines.",
    )
    parser.add_argument(
        "-npv",
        "--number_pv_gens",
        type=int,
        help="How many of the generators in Austria that should be modeled as PV generators (the rest are)"
        " modeled as PQ buses.\n" + "Default: 100",
        default=100,
    )
    parser.add_argument(
        "-va",
        "--vulnerability_analysis",
        nargs="?",
        const="ALL",
        choices=["ALL", "current_flow_betweeness_centrality", "line_loading", "random"],
        help="Run a vulnerability analysis, and optionally run a simulation by attacking the "
        "discovered vulnerabilities. "
        "If no additional argument (or 'ALL') is given, ignore other options (except --number_remove_elements, "
        "--vul_anal_res_dir, --model, and --verbose) and run analysis to find most vulnerable substations"
        " and print the results. "
        "If a specific analysis is chosen, that analysis is run and an attack scenario is created, after "
        "which an attack simulation is run using the created scenario. As such, the --attack_path argument"
        " is ignored.",
    )
    parser.add_argument(
        "-nva",
        "--number_remove_elements",
        type=int,
        help="How many elements to remove when running vulnerability analysis. "
        "Does nothing when -va is not selected.\n"
        "Default: 10",
        default=10,
    )
    parser.add_argument(
        "-vard",
        "--vul_anal_res_dir",
        type=str,
        help="The path to the result directory to use for the vulnerability analysis when "
        "using method 'line_loading'. Must contain the file '/stats/line_loading_percent.csv'. "
        "Ignored if -va is not set.\n"
        "Default: latest modified directory in 'results'.",
    )

    args = parser.parse_args()

    profile = args.profile
    model = get_model_path(args.model)
    config.MODEL_PATH = model

    config.VERBOSE = args.verbose

    config.ATTACK_SCENARIO = args.attack_path

    if args.vulnerability_analysis is not None:
        vprint("Running vulnerability analysis...\n")

        from vulnerability_analysis.vulnerability_analysis import run_vulnerability_analysis

        attack_scenario = run_vulnerability_analysis(
            args.vulnerability_analysis,
            model,
            args.number_remove_elements,
            args.vul_anal_res_dir,
        )

        if attack_scenario is None:
            import sys

            sys.exit()

        config.ATTACK_SCENARIO = attack_scenario

    from util.date_handler import generate_dates

    dates = generate_dates(args.date)

    config.GENERATE_NETWORK_MAPS = args.network_maps
    config.GENERATE_PRE_MAP = args.pre_maps
    config.GENERATE_RESULT_MAP = args.result_map

    config.ENFORCE_REACTIVE_LIMITS = args.reac_lims
    config.USE_CONTROLLERS = not args.no_controllers

    config.NUM_PV_GENS = args.number_pv_gens

    scenario_path = args.scenario
    if scenario_path == "":
        scenario_path = "data/scenarios/status_quo_2022"

    config.SCENARIO_PATH = scenario_path

    from os.path import isdir

    if not isdir(config.SCENARIO_PATH):
        raise FileNotFoundError(f"Could not find scenario folder for path {config.SCENARIO_PATH}")

    create_results_dir(args.name)

    config.WIND_IS_LOCAL = is_wind_local(scenario_path)

    from time import time

    config.START_TIME = time()

    from util import tqdm_logger

    tqdm_logger.set_logger()
    tqdm_logger.dates = dates

    vprint("Running Simulation with the following settings:")
    for s in get_simulation_settings():
        vprint(s)
    vprint("With the following additional options:")
    vprint(get_simulation_options())

    if len(dates) > 1:
        vprint(f"Running a total of {len(dates)} simulations, starting on {dates[0]} and ending on {dates[-1]}.")
    else:
        vprint(f"Running a simulation for {dates[0]}.")
    vprint("")

    if profile:
        print("Profiling enabled...")
        profile_simulations(dates, model)

    run_simulations(dates, model)
