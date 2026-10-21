from pandapower.auxiliary import pandapowerNet
from pandapower.timeseries import OutputWriter

from util import config


def create_output_writer(net: pandapowerNet, time_steps: list | range) -> OutputWriter:
    export_dir = config.RAW_STATS_DIR

    ow = OutputWriter(net, time_steps, output_path=export_dir, output_file_type=".csv", log_variables=[])

    # Register basic stats
    ow.log_variable("load", "p_mw")
    ow.log_variable("gen", "p_mw")
    ow.log_variable("sgen", "p_mw")
    ow.log_variable("res_bus", "vm_pu")
    ow.log_variable("res_bus", "va_degree")
    ow.log_variable("res_line", "loading_percent")
    ow.log_variable("res_line", "i_to_ka")
    ow.log_variable("res_line", "i_from_ka")
    ow.log_variable("res_line", "i_ka")
    ow.log_variable("res_line", "pl_mw")
    ow.log_variable("res_line", "ql_mvar")
    ow.log_variable("res_line", "va_from_degree")
    ow.log_variable("res_line", "va_to_degree")
    ow.log_variable("res_line", "p_to_mw")
    ow.log_variable("res_line", "q_to_mvar")
    ow.log_variable("res_line", "p_from_mw")
    ow.log_variable("res_line", "q_from_mvar")

    # Register under/overvoltages
    def num_undervoltages(vm_pu):
        return sum(vm_pu < 0.95)

    ow.log_variable("res_bus", "vm_pu", eval_function=num_undervoltages, eval_name="num_undervoltages")

    def num_extreme_undervoltages(vm_pu):
        return sum(vm_pu < 0.90)

    ow.log_variable("res_bus", "vm_pu", eval_function=num_extreme_undervoltages, eval_name="num_extreme_undervoltages")

    def num_overvoltages(vm_pu):
        return sum(vm_pu > 1.05)

    ow.log_variable("res_bus", "vm_pu", eval_function=num_overvoltages, eval_name="num_overvoltages")

    def num_extreme_overvoltages(vm_pu):
        return sum(vm_pu > 1.1)

    ow.log_variable("res_bus", "vm_pu", eval_function=num_extreme_overvoltages, eval_name="num_extreme_overvoltages")

    return ow
