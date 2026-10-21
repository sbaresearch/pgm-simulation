# Power Grid simulation
A simulation framework for running load-flow analyses on the Austrian power grid using models created with the [pgm-model-builder](https://github.com/sbaresearch/pgm-model-builder) repository.

This (along with [pgm-model-builder](https://github.com/sbaresearch/pgm-model-builder) and [pgm-gather-osm-data](https://github.com/sbaresearch/pgm-gather-osm-data/tree/main)) were created as part of the Nurzu! project.

## Overview
* Uses a Model object along with additional information (such as consumption and generation profiles) to run load flow analyses on the Austrian transmission grid using pandapower.
* Can run simulations on a one-hour basis.
* Includes advanced elements, such as automatically controlled tap changers on transformers and statcoms.
* Supports adding future scenarios, with differing amounts of consumption and local-level generation.
* Supports attack scenarios, whereby some parts of the network are removed. Can also run multiple vulnerability analyses to find the most vulnerable parts of the grid.
* Creates maps of the topology of the network, the total load on the buses, and the resulting voltage levels, angles, and line loading.

## Results
Each run creates a directory with the results of the run. The directory is places in results/ and the name is specified with the `--name` flag (defaults to current date). The results are based on the options used.

Always creates a text_summary.txt summary of the run, including information on the settings used, the convergence rate, and some voltage information. Also always creates a stats dir, containing csvs with data for each time step and geopackages with information on the elements of the model.

Can also optionally create maps and geojson visualizations. Use
```bash
python main.py --help
```
for more details.

## Installation

### 1. Install Python

Required version: **Python 3.13**  
Download from: [https://www.python.org/downloads/](https://www.python.org/downloads/)

### 2. Install dependencies

Navigate to the project folder and create a virtual environment. Then install the dependencies using
```bash
pip install -r requirements.txt
```


## Usage

```bash
python main.py [options]
```

### Available options
Run 
```bash
python main.py --help
```
for more detailed descriptions of each of the options.

| Option                             | Description                                                      |
| ---------------------------------- | ---------------------------------------------------------------- |
| `-h`, `--help`                     | Show help message and exit                                       |
| `-v`, `--verbose`                  | Print additional information (recommended to keep active)        |
| `-d`, `--date`                     | Specify a date or time range                                     |
| `-s`, `--scenario`                 | Path to the scenario to run                                      |
| `-a`, `--attack_path`              | Path to an attack scenario                                       | 
| `-n`, `--name`                     | Name of result directory                                         | 
| `-m`, `--model`                    | Path to model to use                                             | 
| `-rl`, `--reac_lims`               | Enable reactive limits on generators                             |
| `-xc`, `--no_controllers`          | Disable controllers                                              |
| `-npv`, `--number_pv_gens`         | Number of generators to model as pv nodes                        |
| `-nm`, `--network_maps`            | Creates maps showing the topology of the model                   |
| `-pm`, `--pre_maps`                | Creates a map showing the total load on the loads                |
| `-rm`, `--result_map`              | Creates a map showing the average voltage level other results    |
| `-rm`, `--result_map`              | Creates maps showing the average voltage level and other results |
| `-va`, `--vulnerability_analysis`  | Run the chosen vulnerability analysis                            |
| `-nva`, `--number_remove_elements` | How many elements to remove when running vulnerability analysis  |
| `-vard`, `--vul_anal_res_dir`      | Path to result dir to use when running `-va line_loading`        |

### Example commands
* Run a full year simulation using the (default) 2022 status quo scenario (and print additional information):

  ```bash
  python main.py -d 2022 -v
  ```

* Run simulations for each hour of the day 2022-06-15 using a custom scenario and create result maps:

  ```bash
  python main.py -d 2022-06-15 -s data/scenarios/scenario_2 --result_map
  ```

* Run all vulnerability analyses:

  ```bash
  python main.py -va
  ```

* Run a vulnerability analysis finding the 25 substations with the highest current flow betweeness centrality and run a simulation with these substations removed:

  ```bash
  python main.py -va current_flow_betweeness_centrality -nva 25
  ```


## How It Works
Using the model object (which contains substations, lines, and generators), and the files "stdEinspeisung_MW.csv" and "stdNetzbedarf_MW.csv" in the scenario path (which contain the local generation and consumption respectively), a pandapower network is created. Transformers with tap controllers are automatically placed on substations with multiple voltage levels, and statcoms are placed in specified places. This grid is then used for load flow simulations for the specified dates, one simulation per hour. The results are recorded and stored, along with some summaries.

Additional information can be included in the scenario directory. These are:
* "generation_per_source.csv", which allows the power plant generation to be scaled based on the data provided.
* "power_import_export.csv", which creates loads and generators at substations specified as import/export substations in the model, and creates loads/generation based on the information in this file.
* "total_actual_load.csv", which, when combined with "generation_per_source.csv", allows the consumption data to be scaled to match these values.



## Related Projects
* **[pgm-model-builder](https://github.com/sbaresearch/pgm-model-builder)**\
  Builds the Model object used in this project.

* **[pgm-gather-osm-data](https://github.com/sbaresearch/pgm-gather-osm-data/tree/main)**\
  Collects power grid infrastructure data from OSM.
