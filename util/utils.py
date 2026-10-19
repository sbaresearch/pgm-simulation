import warnings
from contextlib import contextmanager
from datetime import datetime
from os.path import exists

import git
import pandas as pd
from scipy.sparse.linalg import MatrixRankWarning
from tqdm import tqdm

from util import config

# Globals:
CRS = "EPSG:4326"  # lat lon (what OSM uses)
AUSTRIA_CRS = "EPSG:31287"  # Austria only

_elwog_names = pd.read_csv("data/consumption/ELWOG_plus-Datensatz_USPW.csv", sep=";")
elwog_id_to_name = _elwog_names.set_index("USPW-ID")["USPW-Name"].to_dict()

tabbed_tqdm_format = "        {l_bar}{bar}{r_bar}"
tabbed_tqdm_format_no_estimate = "        {l_bar}{bar}| {n_fmt}/{total_fmt}[{elapsed}]"


def vprint(msg: str, enabled: bool = True):
    if config.VERBOSE and enabled:
        tqdm.write(msg)


def get_model_path(model_path: str | None = None) -> str:
    """Finds latest model path if none is given, otherwise returns the path given."""
    if model_path is not None:
        return model_path
    from os import listdir

    dir_path = "data/Model/" + next(iter(sorted(listdir("data/Model"), reverse=True)))
    return dir_path


def is_wind_local(scenario_path: str) -> bool:
    return exists(f"{scenario_path}/stdWINDNetzbedarf_MW.csv") and exists(f"{scenario_path}/stdWINDNetzbedarf_MW.csv")


def create_results_dir(name: str | None):
    import os

    # Create general dirs
    if not os.path.isdir("results/graphs"):
        os.makedirs("results/graphs")
    if config.GENERATE_PRE_MAP and not os.path.isdir("results/graphs/total_power"):
        os.makedirs("results/graphs/total_power")

    # Delete old general files
    dirs_to_empty = [
        "results",
        "results/graphs",
        "results/graphs/total_power",
        "results/graphs/result_graphs",
    ]
    for dir in dirs_to_empty:
        if not os.path.isdir(dir):
            continue
        general_files = [os.path.join(dir, f) for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f))]
        for file in general_files:
            os.remove(file)

    # Create dirs for this specific run
    filename = "results/"
    if name is None:
        filename += datetime.now().strftime("%Y_%m_%d_%H_%M_%S")  # noqa: DTZ005
    else:
        filename += name
    config.EXPORT_DIR = filename

    if os.path.exists(filename):
        raise NameError("Stated path for result directory already exists")

    config.RAW_STATS_DIR = f"{filename}/stats/rawstats"
    os.makedirs(config.RAW_STATS_DIR)

    if config.GENERATE_NETWORK_MAPS or config.GENERATE_RESULT_MAP or config.GENERATE_PRE_MAP:
        # only create dir if any maps/graphs will be created
        os.makedirs(filename + "/graphs")
        if config.GENERATE_PRE_MAP:
            os.makedirs(filename + "/graphs/total_power")
        if config.GENERATE_RESULT_MAP:
            os.makedirs(filename + "/graphs/result_graphs")


def get_simulation_settings() -> list[str]:
    strings = []
    strings.append("===== Simulation Settings =====")
    try:
        branch = git.Repo().active_branch
        strings.append(f"Run on branch {branch.name} on commit {branch.commit.hexsha}")
    except:  # noqa: E722, S110
        pass

    strings.append("Austria-wide simulations.")
    strings.append(f"Model path: {config.MODEL_PATH}")
    strings.append(f"Scenario path: {config.SCENARIO_PATH}")
    strings.append(f"Enforce reactive limits: {config.ENFORCE_REACTIVE_LIMITS}")
    strings.append(f"Using controllers: {config.USE_CONTROLLERS}")
    strings.append(f"Number of PV generators: {config.NUM_PV_GENS}\n")

    return strings


def get_simulation_options() -> str:
    s = (
        f"Create network maps: {config.GENERATE_NETWORK_MAPS}\n"
        f"Create pre map: {config.GENERATE_PRE_MAP}\n"
        f"Create result map: {config.GENERATE_RESULT_MAP}\n"
    )

    return s


@contextmanager
def suppress_matrix_rank_warnings():
    # Remove warnings that might pop up when the network does not converge.
    # Does not actually produce any useful information, so might as well suppress them
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message="invalid value encountered in divide",
        )
        warnings.filterwarnings(
            "ignore",
            category=RuntimeWarning,
            message="overflow encountered in divide",
        )
        warnings.filterwarnings(
            "ignore",
            category=MatrixRankWarning,
        )
        yield
