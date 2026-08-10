#!/usr/bin/env python3

import re
import shutil
import subprocess
import traceback
import signal
import sys
import os
import time
import atexit
import argparse

from collections import defaultdict
from pathlib import Path
from contextlib import contextmanager

# ============================================================
# COMMAND-LINE ARGUMENTS
# ============================================================

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="EHT PolConvert processing pipeline"
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Input EHT data directory"
    )
    parser.add_argument(
        "--qa2",
        type=Path,
        default=None,
        help=(
            "QA2 tables directory. "
            "If not provided, INPUT/QA2_tables is used."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output directory"
    )
    parser.add_argument(
        "--nproc",
        type=int,
        default=4,
        help="Number of processes for PolConvert (default: 4)"
    )
    args = parser.parse_args()

    # Convert paths to absolute paths
    args.input = args.input.resolve()
    args.output = args.output.resolve()

    # If QA2 directory is not specified, assume INPUT/QA2_tables
    if args.qa2 is None:
        args.qa2 = args.input / "QA2_tables"
    else:
        args.qa2 = args.qa2.resolve()

    return args

ARGS = parse_arguments()

INPUT_ROOT = ARGS.input
QA2_ROOT = ARGS.qa2
OUTPUT_ROOT = ARGS.output
NPROC = ARGS.nproc

# ============================================================
# SCRIPT LOCATIONS
# ============================================================
# The following scripts are expected to be in the same
# directory as this script.
#
# main.py
# polconvert_runTrack.py
# SWIN_CAL_PLOT.py
# polconvert_apply.py

SCRIPT_DIR = Path(__file__).resolve().parent

POLCONVERT_SCRIPT = SCRIPT_DIR / "polconvert_runTrack.py"
PLOT_SCRIPT = SCRIPT_DIR / "SWIN_CAL_PLOT.py"

# ============================================================
# STATUS / LOG FILES
# ============================================================

CRASH_REPORT_FILE = Path("CRASH_REPORT.txt")
WATCH_FILE = Path("script_is_running.lock")

# ============================================================
# ANTENNAS
# ============================================================

ANTENNAS = ["AX", "LM", "GL", "KT", "NN", "MG", "MM", "SW"]
REFANT = "AA"

# ============================================================
# FILE NAME REGEX
# ============================================================

FILE_REGEX = re.compile(
    r"^(?P<track>e\d+[a-z]\d+)"
    r"-\d+"
    r"-b(?P<band>\d+)"
    r"-(?P<calibrator>[^-]+)"
    r"-(?P<source>.+)"
    r"\.(?P<ext>swin|dxin)$"
)

VALID_SOURCE_REGEX = re.compile(r"^[A-Za-z0-9+\-_.]+$")

# ============================================================
# PROCESSING STATUS
# ============================================================

SUCCESS = []
FAILED = []
SKIPPED = []

# ============================================================
# OUTPUT DIRECTORY
# ============================================================

def safe_mkdir(path):
    path.mkdir(parents=True, exist_ok=True)

safe_mkdir(OUTPUT_ROOT)

ERROR_LOG = OUTPUT_ROOT / "errors.log"
ERROR_LOG.touch()

# ============================================================
# CRASH REPORT
# ============================================================

def write_crash_report(reason, details=""):
    with open(CRASH_REPORT_FILE, "w") as f:
        f.write(f"Crash report generated at {time.ctime()}\n")
        f.write(f"PID: {os.getpid()}\n")
        f.write(f"Reason: {reason}\n")
        f.write(f"Input directory: {INPUT_ROOT}\n")
        f.write(f"QA2 directory: {QA2_ROOT}\n")
        f.write(f"Output directory: {OUTPUT_ROOT}\n")
        f.write(f"NPROC: {NPROC}\n")
        if details:
            f.write(f"Details:\n{details}\n")
        f.write(f"Working directory: {os.getcwd()}\n")
        f.write(f"Command line: {' '.join(sys.argv)}\n")
    print(f"\n[CRASH] {reason}", flush=True)
    if details:
        # Also print details to stderr so the user can see the error immediately
        print(details, file=sys.stderr, flush=True)

def signal_handler(sig, frame):
    write_crash_report(f"Received signal {sig} ({signal.Signals(sig).name})")
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGHUP, signal_handler)

# ============================================================
# WATCH FILE
# ============================================================

WATCH_FILE.write_text(
    f"PID={os.getpid()}\n"
    f"START={time.ctime()}\n"
    f"INPUT={INPUT_ROOT}\n"
    f"QA2={QA2_ROOT}\n"
    f"OUTPUT={OUTPUT_ROOT}\n"
)

atexit.register(lambda: WATCH_FILE.unlink(missing_ok=True))

# ============================================================
# RUN EXTERNAL COMMAND
# ============================================================

def run(cmd, cwd=None, log=None):
    print("\nRUN:", " ".join(map(str, cmd)), flush=True)
    try:
        if log:
            log = Path(log)
            log.parent.mkdir(parents=True, exist_ok=True)
            log_handle = open(log, "a")
        else:
            log_handle = open(os.devnull, "w")

        with log_handle as lf:
            lf.write(f"\n{'='*80}\n")
            lf.write(f"START {time.ctime()}\n")
            lf.write(f"COMMAND:\n{' '.join(map(str, cmd))}\n")
            lf.write(f"CWD:\n{cwd}\n")
            lf.flush()

            result = subprocess.run(
                cmd,
                cwd=cwd,
                text=True,
                stdout=lf,
                stderr=subprocess.STDOUT
            )
            lf.write(f"\nRETURN CODE: {result.returncode}\n")

        return result.returncode == 0

    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        with open(ERROR_LOG, "a") as f:
            f.write(tb + "\n")
        return False

# ============================================================
# PLOT WITH REFERENCE ANTENNA FALLBACK
# ============================================================

def run_plot_with_fallback(datadir, plotdir, src, band, work_dir, log_file):
    # Try the preferred reference antenna first,
    # followed by all other configured antennas.
    refants = [REFANT] + [a for a in ANTENNAS if a != REFANT]

    for refant in refants:
        print(f"\nTrying REFANT={refant}", flush=True)

        success = run(
            [
                "python3",
                str(PLOT_SCRIPT),
                "--datadir", str(datadir),
                "--plotdir", str(plotdir),
                "--source", str(src),
                "--bands", str(band),
                "--antennas", *ANTENNAS,
                "--refant", str(refant)
            ],
            cwd=work_dir,
            log=log_file
        )

        pdir = Path(work_dir) / plotdir
        if success and pdir.exists() and any(pdir.rglob("*.png")):
            print(f"Plots created successfully with REFANT={refant}", flush=True)
            return True

        print(f"No plots found with REFANT={refant}", flush=True)

    return False

# ============================================================
# EXTRACT TRACK FROM QA2
# ============================================================

def extract_track_from_qa2(qa2_dir):
    qa2_dir = Path(qa2_dir)
    for f in qa2_dir.rglob("*"):
        if not f.is_file():
            continue
        if ".calibrated.ms." in f.name and ("ALMA" in f.name or "APP" in f.name):
            return f.name.split(".")[0]
    raise RuntimeError(f"No calibrated ALMA/APP file in {qa2_dir}")

# ============================================================
# FIND QA2 DIRECTORY
# ============================================================

def find_qa2(track):
    # Original robust search: recursively find all QA2 directories
    # and filter by track base name.
    base = track.split("-")[0]
    matches = []
    for q in QA2_ROOT.rglob("*APP_DELIVERABLES.QA2"):
        if base in q.name:
            matches.append(q)
    return matches

# ============================================================
# PREPARE QA2
# ============================================================

def prepare_qa2(track):
    qa2s = find_qa2(track)

    if not qa2s:
        raise RuntimeError(f"No QA2 found for track: {track}")

    results = []
    original_script = SCRIPT_DIR / "polconvert_apply.py"

    if not original_script.exists():
        raise RuntimeError(f"Required script not found: {original_script}")

    # Keep QA2 tables inside the output directory.
    qa2_output_root = OUTPUT_ROOT / "QA2_tables"
    safe_mkdir(qa2_output_root)

    for qa2 in qa2s:
        print(f"\nPreparing QA2:\n{qa2}", flush=True)

        base_track = extract_track_from_qa2(qa2)

        if "bandpassFixed" in qa2.name:
            full_track = f"{base_track}_bandpassFixed"
            suffix = "bandpassFixed"
        else:
            full_track = base_track
            suffix = ""

        dest = qa2_output_root / f"{full_track}_QA2"

        if not dest.exists():
            print(f"Copying QA2 to:\n{dest}", flush=True)
            shutil.copytree(qa2, dest)
        else:
            print(f"QA2 destination already exists:\n{dest}", flush=True)

        # Copy polconvert_apply.py into the prepared QA2 directory.
        dest_script = dest / f"{base_track}_polconvert_apply.py"
        shutil.copy2(original_script, dest_script)

        results.append((dest, base_track, full_track, suffix))

    return results

# ============================================================
# TEMPORARY WORKSPACE
# ============================================================

@contextmanager
def tmpws(path):
    path = Path(path)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)

# ============================================================
# SAFE COPY
# ============================================================

def safe_copy_tree(src, dst):
    src = Path(src)
    dst = Path(dst)

    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        shutil.copy2(src, dst)

# ============================================================
# VALIDATE INPUTS
# ============================================================

def validate_inputs():
    print("\nValidating directories and scripts...")

    if not INPUT_ROOT.exists():
        raise RuntimeError(f"Input directory does not exist:\n{INPUT_ROOT}")
    if not INPUT_ROOT.is_dir():
        raise RuntimeError(f"Input path is not a directory:\n{INPUT_ROOT}")

    if not QA2_ROOT.exists():
        raise RuntimeError(f"QA2 directory does not exist:\n{QA2_ROOT}")
    if not QA2_ROOT.is_dir():
        raise RuntimeError(f"QA2 path is not a directory:\n{QA2_ROOT}")

    if not POLCONVERT_SCRIPT.exists():
        raise RuntimeError(f"PolConvert script not found:\n{POLCONVERT_SCRIPT}")
    if not PLOT_SCRIPT.exists():
        raise RuntimeError(f"Plot script not found:\n{PLOT_SCRIPT}")

    apply_script = SCRIPT_DIR / "polconvert_apply.py"
    if not apply_script.exists():
        raise RuntimeError(f"Required script not found:\n{apply_script}")

    if NPROC < 1:
        raise RuntimeError("NPROC must be at least 1")

    print("Input directories and scripts validated successfully.")

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 60)
    print("EHT POLCONVERT PROCESSING PIPELINE")
    print("=" * 60)
    print(f"INPUT :  {INPUT_ROOT}")
    print(f"QA2   :  {QA2_ROOT}")
    print(f"OUTPUT:  {OUTPUT_ROOT}")
    print(f"NPROC :  {NPROC}")
    print("=" * 60 + "\n")

    validate_inputs()

    tracks = [
        x for x in INPUT_ROOT.iterdir()
        if x.is_dir() and x.name != "QA2_tables"
    ]

    if not tracks:
        print("WARNING: No track directories were found.")

    print(f"Found {len(tracks)} track(s).")

    for i, tr in enumerate(tracks, start=1):
        print("\n" + "=" * 60)
        print(f"TRACK {i}/{len(tracks)}: {tr.name}")
        print("=" * 60)

        try:
            qa2_info = prepare_qa2(tr.name)
        except Exception:
            with open(ERROR_LOG, "a") as f:
                f.write(f"\nQA2 ERROR: {tr.name}\n")
                f.write(traceback.format_exc() + "\n")
            FAILED.append(tr.name)
            continue

        for st in tr.iterdir():
            if not st.is_dir():
                continue

            print(f"\nObservation directory: {st.name}")

            grouped = defaultdict(dict)

            for e in st.iterdir():
                if not e.is_dir():
                    continue

                match = FILE_REGEX.match(e.name)
                if not match:
                    SKIPPED.append(e.name)
                    continue

                src = match["source"]
                band = match["band"]
                ext = match["ext"]

                if not VALID_SOURCE_REGEX.match(src):
                    FAILED.append(e.name)
                    continue

                grouped[(src, band)][ext] = e

            for (src, band), files in grouped.items():
                print(f"\nSource: {src} | Band: b{band}")

                if "swin" not in files or "dxin" not in files:
                    print(f"Missing swin/dxin for {src} b{band}")
                    FAILED.append(f"{src} b{band}")
                    continue

                swin = files["swin"]
                dxin = files["dxin"]

                try:
                    rel_obs = st.relative_to(INPUT_ROOT)
                except ValueError:
                    rel_obs = Path(st.name)

                work_dir = OUTPUT_ROOT / rel_obs / f"{src}_b{band}"
                safe_mkdir(work_dir)
                print(f"Working directory:\n{work_dir}")

                with tmpws(work_dir / "tmp") as tmp:
                    try:
                        print("\nCopying dxin data...")
                        for item in dxin.iterdir():
                            safe_copy_tree(item, tmp / item.name)

                        print("Copying swin data...")
                        for item in swin.iterdir():
                            safe_copy_tree(item, tmp / item.name)

                    except Exception:
                        with open(ERROR_LOG, "a") as f:
                            f.write(f"\nDATA COPY ERROR: {tr.name} {st.name} {src} b{band}\n")
                            f.write(traceback.format_exc() + "\n")
                        FAILED.append(f"{src} b{band}")
                        continue

                    # ==========================================
                    # ORIGINAL DATA PLOTS
                    # ==========================================
                    print("\nGenerating plots for original data...")
                    if not run_plot_with_fallback(
                        datadir=str(tmp),
                        plotdir=f"plots_{src}_Org",
                        src=src,
                        band=band,
                        work_dir=work_dir,
                        log_file=work_dir / "p1.log"
                    ):
                        print("WARNING: Could not generate original data plots.")

                    # ==========================================
                    # POLCONVERT FOR EACH QA2
                    # ==========================================
                    for qa2_dest, base_track, full_track, suffix in qa2_info:
                        print("\n" + "-" * 60)
                        print(f"Running PolConvert for {full_track}")
                        print("-" * 60)

                        pc_out = f"{swin.name}.{full_track}.PC"
                        plot_dir = f"plots_{src}_PC_{full_track}"
                        log_name = f"pol_{full_track}.log"

                        ok = run(
                            [
                                str(POLCONVERT_SCRIPT),
                                "--origdata", str(tmp),
                                "--qa2dir", str(qa2_dest),
                                "--destdata", pc_out,
                                "--track", base_track,
                                "--bands", str(band),
                                "--nproc", str(NPROC)
                            ],
                            cwd=work_dir,
                            log=work_dir / log_name
                        )

                        if not ok:
                            print(f"PolConvert FAILED for {src} b{band} {full_track}")
                            with open(ERROR_LOG, "a") as f:
                                f.write(f"Polconvert failed {src} {band} {full_track}\n")
                            FAILED.append(f"{src}|b{band}|{full_track}")
                            continue

                        print(f"PolConvert completed successfully for {full_track}")

                        print("\nGenerating plots for PolConverted data...")
                        if not run_plot_with_fallback(
                            datadir=pc_out,
                            plotdir=plot_dir,
                            src=src,
                            band=band,
                            work_dir=work_dir,
                            log_file=work_dir / "p2.log"
                        ):
                            print("WARNING: Could not generate PolConverted data plots.")

                        SUCCESS.append(f"{tr.name}|{st.name}|{src}|b{band}|{full_track}")

    # ============================================================
    # WRITE SUMMARY
    # ============================================================
    summary_file = OUTPUT_ROOT / "summary.txt"
    with open(summary_file, "w") as f:
        f.write("EHT POLCONVERT PROCESSING SUMMARY\n")
        f.write(f"Generated: {time.ctime()}\n")
        f.write(f"Input: {INPUT_ROOT}\n")
        f.write(f"QA2: {QA2_ROOT}\n")
        f.write(f"Output: {OUTPUT_ROOT}\n")
        f.write(f"NPROC: {NPROC}\n\n")

        f.write("=" * 60 + "\n")
        f.write("SUCCESS\n")
        f.write("=" * 60 + "\n")
        if SUCCESS:
            f.write("\n".join(SUCCESS))

        f.write("\n\n" + "=" * 60 + "\n")
        f.write("FAILED\n")
        f.write("=" * 60 + "\n")
        if FAILED:
            f.write("\n".join(FAILED))

        f.write("\n\n" + "=" * 60 + "\n")
        f.write("SKIPPED\n")
        f.write("=" * 60 + "\n")
        if SKIPPED:
            f.write("\n".join(SKIPPED))

        f.write("\n")

    # ============================================================
    # FINAL STATUS
    # ============================================================
    print("\n" + "=" * 60)
    print("PROCESSING COMPLETE")
    print("=" * 60)
    print(f"SUCCESS : {len(SUCCESS)}")
    print(f"FAILED  : {len(FAILED)}")
    print(f"SKIPPED : {len(SKIPPED)}")
    print(f"\nSummary:\n{summary_file}")
    print("=" * 60)


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception:
        tb = traceback.format_exc()
        # Print the full traceback to stderr so the user can see the error
        print(tb, file=sys.stderr, flush=True)
        write_crash_report("fatal", tb)
        sys.exit(1)
    finally:
        WATCH_FILE.unlink(missing_ok=True)
