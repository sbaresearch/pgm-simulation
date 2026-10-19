import json
from datetime import datetime
from time import time

import git
import pandas as pd

from util import config
from util.utils import get_simulation_options, get_simulation_settings, vprint


def summarize_stats(dates: list[datetime]):
    res_dict = {}
    res_dict["run_time"] = f"{datetime.fromtimestamp(config.START_TIME).strftime('%y-%m-%dT%X')}"  # noqa: DTZ006
    res_dict["sim_start_date"] = f"{dates[0]}"
    res_dict["sim_end_date"] = f"{dates[-1]}"
    res_dict["total_sim_run_time"] = time() - config.START_TIME

    branch = git.Repo().active_branch
    res_dict["git_branch"] = branch.name
    res_dict["git_commit"] = branch.commit.hexsha

    res_dict["model_path"] = config.MODEL_PATH
    res_dict["num_pv_gens"] = config.NUM_PV_GENS
    res_dict["scenario_path"] = config.SCENARIO_PATH
    res_dict["enforce_reactive_limits"] = config.ENFORCE_REACTIVE_LIMITS
    res_dict["use_controllers"] = config.USE_CONTROLLERS

    from util import power_factors

    res_dict["power_factors"] = {
        "generation": power_factors.GENERATION_POWER_FACTOR,
        "consumer": power_factors.CONSUMER_RP_FACTOR,
        # NOTE: random
        "local_win": power_factors.LOCAL_WIND_RP_FACTOR,
        # NOTE: random
        "hydro_pump_load": power_factors.HYDRO_PUMP_LOAD_RP_FACTOR,
        # NOTE: random
        "export": power_factors.EXPORTED_RP_FACTOR,
    }

    msg: list[str] = []

    msg.append(
        f"Simulations run on {res_dict['run_time']}\n"
        f"Ran simulations starting on {res_dict['sim_start_date']} and ending on {res_dict['sim_end_date']}.\n"
        f"Total simulation time: {res_dict['total_sim_run_time']:.2f}s\n"
    )

    msg.extend(get_simulation_settings())
    msg.append(get_simulation_options())

    conv_res, conv_msg = _convergence_rate()
    res_dict.update(conv_res)
    msg.extend(conv_msg)

    power_res, power_msg = _total_power()
    res_dict["total_power"] = power_res
    msg.extend(power_msg)

    uo_voltages_res, uo_voltages_msg = _under_over_voltages()
    res_dict["under_over_voltages"] = uo_voltages_res
    msg.extend(uo_voltages_msg)

    losses_res, losses_msg = _losses()
    res_dict["losses"] = losses_res
    msg.extend(losses_msg)

    # Print messages
    vprint("")
    for s in msg:
        vprint(s)

    save_dirs = [config.EXPORT_DIR, "results"]
    for dir in save_dirs:
        txt_save_path = f"{dir}/text_summary.txt"
        with open(txt_save_path, "w") as file:
            for s in msg:
                file.write(s + "\n")

        res_save_path = f"{dir}/results.json"
        with open(res_save_path, "w") as file:
            json.dump(res_dict, file, indent=4)


def _convergence_rate() -> tuple[dict, list[str]]:
    msg = []
    res_dict = {}

    # Read some value that is never supposed to be all 0 to find runs that did not converge
    bus_vm_pu = pd.read_csv(f"{config.EXPORT_DIR}/stats/bus_vm_pu.csv", index_col=0).T
    # Find how many dates have all zeroes (=> failed run)
    res_dict["num_failed"] = sum(bus_vm_pu.sum(axis=1) == 0)
    res_dict["success_rate"] = 1 - res_dict["num_failed"] / len(bus_vm_pu)

    msg.append("N.o. failed runs")
    msg.append(f"{res_dict['num_failed']} ({res_dict['success_rate']:.0%} success rate)")

    return res_dict, msg


def _under_over_voltages() -> tuple[dict, list[str]]:
    msg = []
    msg.append("\nN.o. under/over voltages")
    under_over_voltages = pd.read_csv(f"{config.EXPORT_DIR}/stats/under_over_voltages.csv", index_col=0).T
    msg.append(str(under_over_voltages.describe()))

    return under_over_voltages.describe().to_dict(), msg


def _total_power() -> tuple[dict, list[str]]:
    msg = []
    msg.append("\nTotal power [MW]")

    total_power = pd.read_csv(f"{config.EXPORT_DIR}/stats/total_power.csv", index_col=0).T
    total_power["diff"] = total_power.generation + total_power["import"] - total_power.load - total_power.export
    msg.append(str(total_power.describe()))

    return total_power.describe().to_dict(), msg


def _losses() -> tuple[dict, list[str]]:
    msg = []
    msg.append("\nTotal losses [MW]")

    losses = pd.DataFrame()

    losses["real"] = pd.read_csv(f"{config.EXPORT_DIR}/stats/line_pl_mw.csv", index_col=0).T.sum(axis=1)
    losses["reactive"] = pd.read_csv(f"{config.EXPORT_DIR}/stats/line_ql_mvar.csv", index_col=0).T.sum(axis=1)
    msg.append(str(losses.describe()))

    return losses.describe().to_dict(), msg
