import pandapower as pp
from pandapower.auxiliary import pandapowerNet


def initialize_standard_types(net: pandapowerNet):
    trafo_380_220_data = {  # Taken from simbench
        "sn_mva": 600,
        "vn_hv_kv": 380,
        "vn_lv_kv": 220,
        "vk_percent": 14,  # Original value: 18.5. Changed because invalid in pandapower (has to be <15).
        "vkr_percent": 0.25,
        "pfe_kw": 250,
        "i0_percent": 0.04,
        "shift_degree": 0,
        # The following values are copied from built in standard types
        "tap_side": "hv",
        "tap_neutral": 0,
        "tap_min": -9,
        "tap_max": 9,
        "tap_step_percent": 1.5,
        "tap_step_degree": 0.0,
        "tap_pos": 0.0,
        "tap_changer_type": "Ratio",
        "tap_dependency_table": False,
        "parallel": 1,
        "df": 1.0,
        "in_service": True,
        "vector_group": "Yy0",
    }
    pp.create_std_type(net, name="simbench_380_220", element="trafo", data=trafo_380_220_data)

    line_380_data = {  # The average from the Static Grid Model data https://www.jao.eu/static-grid-model
        "r_ohm_per_km": 0.020,
        "x_ohm_per_km": 0.307,
        "c_nf_per_km": 12.68,
        "max_i_ka": 2.32,
    }
    pp.create_std_type(net, name="line_380", element="line", data=line_380_data)

    line_220_data = {  # The average from the Static Grid Model data https://www.jao.eu/static-grid-model
        "r_ohm_per_km": 0.053,
        "x_ohm_per_km": 0.328,
        "c_nf_per_km": 10.5,
        "max_i_ka": 1.39,
    }
    pp.create_std_type(net, name="line_220", element="line", data=line_220_data)
