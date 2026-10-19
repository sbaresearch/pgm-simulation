# NOTE: the scaling from real power to reactive power, not actual power factor
# (a value here of 0.3 represents a PF of about 0.95 (tan(arccos(0.95)) ~= 0.3))
GENERATION_POWER_FACTOR: dict[str, float] = {
    "Hydro Run-of-river": 0.3,
    "Hydro Water Reservoir": 0.3,
    "Hydro Pumped Storage": 0.3,
    "Gas": 0.3,
    "Waste": 0.3,
    "Biomass": 0.3,
    "Wind": 0.3,
}

# NOTE: Set by trail and error
CONSUMER_RP_FACTOR: float = 0.1

# NOTE: Set by trail and error
LOCAL_WIND_RP_FACTOR: float = 0.2

# NOTE: Set by trail and error
HYDRO_PUMP_LOAD_RP_FACTOR: float = 0.2

# NOTE: Set by trail and error
EXPORTED_RP_FACTOR: float = 0.15
