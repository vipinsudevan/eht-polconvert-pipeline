# EHT PolConvert Processing Pipeline

A Python-based processing pipeline for running [PolConvert](https://github.com/marti-vidal-i/PolConvert) on EHT data, generating calibration plots, and organizing QA2 calibration tables and processing outputs.

## Overview

This pipeline automates the following workflow:

1. Validates the EHT input data and required processing scripts.
2. Discovers observation/track directories.
3. Identifies matching `.swin` and `.dxin` data directories.
4. Copies the input data into a temporary processing workspace.
5. Generates plots for the original data.
6. Locates and prepares the appropriate QA2 calibration tables.
7. Runs PolConvert for each available QA2 dataset.
8. Generates plots for the PolConverted data.
9. Records successful, failed, and skipped processing jobs.
10. Writes processing logs and a final summary.

## PolConvert Dependencies

This pipeline is designed to run in an environment where **PolConvert is already installed and configured**.

The following scripts are required by this pipeline:

```text
polconvert_runTrack.py
SWIN_CAL_PLOT.py
polconvert_apply.py
```

These scripts are part of the PolConvert/EHT processing environment and are **not included in this repository**.

They must be available in the **same directory as `main.py`** when the pipeline is executed.

The repository therefore contains only the pipeline code and documentation; it does not attempt to install or configure PolConvert.

## Repository Structure

```text
eht-polconvert-pipeline/
├── main.py
├── README.md
└── .gitignore
```

The required PolConvert scripts should be present on the EHT processing server:

```text
<polconvert-pipeline-directory>/
├── main.py
├── polconvert_runTrack.py
├── SWIN_CAL_PLOT.py
└── polconvert_apply.py
```

## Requirements

### Software

* Python 3
* PolConvert installed and configured
* The EHT/PolConvert processing environment required by PolConvert
* Appropriate EHT input data
* QA2 calibration tables

### Python dependencies

The `main.py` pipeline uses only Python standard-library modules. No additional Python packages need to be installed with `pip`.

Therefore, **no `requirements.txt` file is required** for this repository.

The required PolConvert software and its dependencies should already be installed on the EHT processing server.

## Installation

Clone the repository onto the EHT processing server:

```bash
git clone https://github.com/vipinsudevan/eht-polconvert-pipeline.git
cd eht-polconvert-pipeline
```

Copy or place the required PolConvert scripts in the same directory:

```text
eht-polconvert-pipeline/
├── main.py
├── polconvert_runTrack.py
├── SWIN_CAL_PLOT.py
├── polconvert_apply.py
└── README.md
```

No Python package installation is required for `main.py`.

You can verify that the pipeline has valid Python syntax with:

```bash
python3 -m py_compile main.py
```

## Input Data

By default, the pipeline expects QA2 tables at:

```text
INPUT/QA2_tables
```

A separate QA2 directory can be supplied using `--qa2`.

The input directory should contain EHT track/observation directories containing matching `.swin` and `.dxin` datasets.

## Usage

The basic command is:

```bash
python3 main.py \
    --input /path/to/eht/input \
    --output /path/to/output
```

If the QA2 tables are stored separately:

```bash
python3 main.py \
    --input /path/to/eht/input \
    --qa2 /path/to/QA2_tables \
    --output /path/to/output
```

To specify the number of PolConvert processes:

```bash
python3 main.py \
    --input /path/to/eht/input \
    --qa2 /path/to/QA2_tables \
    --output /path/to/output \
    --nproc 8
```

## Command-Line Arguments

| Argument   | Required | Default            | Description                            |
| ---------- | -------- | ------------------ | -------------------------------------- |
| `--input`  | Yes      | —                  | Input EHT data directory               |
| `--qa2`    | No       | `INPUT/QA2_tables` | QA2 tables directory                   |
| `--output` | Yes      | —                  | Output directory                       |
| `--nproc`  | No       | `4`                | Number of processes used by PolConvert |

## Example

For example:

```bash
python3 main.py \
    --input /data/eht/experiment \
    --qa2 /data/eht/experiment/QA2_tables \
    --output /data/eht/polconvert_results \
    --nproc 8
```

The input data and output directories can be located anywhere accessible to the processing server. They do not need to be inside the Git repository.

## Processing Workflow

For each track and observation, the pipeline:

```text
Input EHT data
      |
      v
Find .swin / .dxin pairs
      |
      v
Copy data to temporary workspace
      |
      v
Generate original-data plots
      |
      v
Find matching QA2 directories
      |
      v
Prepare QA2 directory
      |
      v
Run PolConvert
      |
      v
Generate PolConverted-data plots
      |
      v
Record success/failure
```

## Output

The output directory contains processing results organized by observation and source.

A simplified example:

```text
output/
├── QA2_tables/
│   └── <track>_QA2/
│
├── <observation>/
│   └── <source>_b<band>/
│       ├── plots_<source>_Org/
│       ├── plots_<source>_PC_<track>/
│       ├── pol_<track>.log
│       ├── p1.log
│       └── p2.log
│
├── errors.log
└── summary.txt
```

Temporary processing directories are removed automatically after processing.

## Reference Antenna

The plotting stage attempts to use the preferred reference antenna:

```text
AA
```

If plotting fails to produce PNG output, the pipeline retries using the configured antennas until a working reference antenna is found.

The configured antennas are:

```text
AX
LM
GL
KT
NN
MG
MM
SW
```

## Logging

The pipeline produces several types of diagnostic information:

* `errors.log` — errors encountered during processing
* `summary.txt` — final list of successful, failed, and skipped jobs
* `p1.log` — original-data plotting log
* `p2.log` — PolConverted-data plotting log
* `pol_<track>.log` — PolConvert execution log
* `CRASH_REPORT.txt` — information recorded if the main process terminates unexpectedly

## Failure Handling

A failure for one source, band, or QA2 dataset does not necessarily stop the entire pipeline.

Failed jobs are recorded in the final summary:

```text
SUCCESS
============================================================
...

FAILED
============================================================
...

SKIPPED
============================================================
...
```

This allows individual processing failures to be investigated without losing the results from other successfully processed datasets.

## Important Notes

### Input Data

The pipeline expects the input data to follow the filename and directory conventions defined by `FILE_REGEX` in `main.py`.

### QA2 Data

The pipeline searches recursively for QA2 directories matching the expected naming convention and prepares copies inside the output directory.

### PolConvert Scripts

The following files must be available in the same directory as `main.py`:

```text
polconvert_runTrack.py
SWIN_CAL_PLOT.py
polconvert_apply.py
```

These files are expected to come from the PolConvert/EHT software environment and are not maintained in this repository.

### Large Data Files

EHT datasets can be very large. Input data, QA2 data, and generated processing products should **not** normally be committed to this Git repository.

The Git repository is intended to contain the pipeline code and documentation only.

## Development

Before committing changes, check the Python script for syntax errors:

```bash
python3 -m py_compile main.py
```

## License

Add the appropriate license for your project here.

If this software is associated with a research project or collaboration, make sure the selected license is compatible with the project's requirements.

## Author

Vipin SUdevan

## Citation

If this pipeline is used in research or publications, please cite the appropriate PolConvert/EHT software and methodology papers.

Add project-specific citation information here when available.

