# See Kategorien.csv for descriptions of each category.
load_profile_categories_translation_map: dict[str, str] = {
    "H0": "wo_kl",  # Wohngebäuden, klassischen Haushalts-stromverbrauch
    "ULF": "wo_rw",  # Wohngebäuden, elektrische Heizung und Warmwasseraufbereitung
    "L0": "lw",  # Land- und Forstwirtschaft
    "G0": "ig",  # Industrie und Gewerbe
    "G4": "dl",  # Dienstleistungen
}

generator_source_translation_map: dict[str, str] = {
    "gas": "Gas",
    "hydro": "Hydro Run-of-river",
    "waste": "Waste",
    "biomass": "Biomass",
    "wind": "Wind",
    "solar": "Solar",
    "biogas": "Biomass",  # Only one generator
    "battery": "Hydro Run-of-river",  # Not sure what to choose, but does not exist in the gen profile data
    "gas;waste;biomass": "Gas",  # Fernheizkraftwerk Linz-Mitte, almost only gas
    "gas;waste": "Waste",  # Kraftwerk Dürnrohr, no gas nowadays
    "gas;biomass": "Gas",  # Kraftwerk Simmering, almost only gas
    "gas;oil;biomass": "Gas",  # Kraftwerk Simmering (2022), almost only gas
    "waste;gas": "Waste",  # Müllverbrennungsanlage Spittelau, almost only waste
    "biomass_solar": "Biomass",  # Solar & Biomasse Heizwerk Saxen, very small, guessing mostly solar
    "hydro;solar": "Hydro Run-of-river",  # Elektrizitätswerk Amstetten, small, mostly hydro
    "wind;solar": "Wind",  # Hybridkraftwerk Trumau/Tattendorf: Mostly wind in 2022, mostly solar after 2023
}

generator_profile_translation_map: dict[str, str] = {
    "Wind": "Wind",
    "Biomass": "Biomass",
    "Gas": "Gas",
    "Hydro Run-of-river and poundage": "Hydro Run-of-river",
    "Hydro Water Reservoir": "Hydro Water Reservoir",
    "Hydro Pumped Storage": "Hydro Pumped Storage",  # Can be negative (i.e. act as a load)
    "Waste": "Waste",  # always 100.0
    # always 0.072 MW. I chose Hydro, because OSM doesn't have any geothermal plants, and I am assuming they are quite spread out over the country
    "Geothermal": "Hydro Run-of-river",
    # always 22.0 MW. Don't know what this is. Chose Hydro because they are very spread out over the whole country.
    "Other": "Hydro Run-of-river",
    "Other renewable": "NAN",  # 0 all year
    "Coal": "NAN",  # 0 all year
    "Oil": "NAN",  # 0 all year
}
