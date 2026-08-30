#!/usr/bin/env python3
"""Generate the 80289 VFO frequency-plan, coverage, and FFT study.

The script exports the saved KiCad schematic, runs the low, center, and high
PTO points for every documented band segment, writes the coverage CSV, and
exports band-center FFT data and figures. Generated netlists, raw files, and
logs remain below spice/generated.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import ngspice_raw


ROOT = Path(__file__).resolve().parents[2]
SPICE_DIR = ROOT / "spice"
STUDY_DIR = SPICE_DIR / "studies" / "80289" / "frequency-plan"
DATA_DIR = STUDY_DIR / "data"
FIGURE_DIR = STUDY_DIR / "figures"
GENERATED_DIR = SPICE_DIR / "generated" / "80289-frequency-plan"
RUN_DIR = GENERATED_DIR / "runs"
BASE_NETLIST = GENERATED_DIR / "80289-vfo-frequency-plan-base.cir"
OUTPUT_CSV = DATA_DIR / "80289-vfo-frequency-plan-coverage.csv"
FFT_CSV = DATA_DIR / "80289-vfo-band-center-fft.csv"
FFT_HF_PNG = FIGURE_DIR / "80289-vfo-band-center-fft-3p5-21mhz.png"
FFT_10M_PNG = FIGURE_DIR / "80289-vfo-band-center-fft-10m.png"

KICAD_CLI = Path(r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe")
NGSPICE = Path(r"C:\Tools\ngspice-46\Spice64\bin\ngspice_con.exe")
SCHEMATIC = ROOT / "triton_540.kicad_sch"
OUT_VECTOR = "v(/vfo-80289/out)"
VECTORS = {
    "mixer_positive_v": "v(net-_s89-1c-c-com_)",
    "mixer_negative_v": "v(net-_r89-13-pad2_)",
    "filter_output_v": "v(net-_q89-1-g_)",
    "vfo_out_v": OUT_VECTOR,
}


@dataclass(frozen=True)
class BandSegment:
    dial_band: str
    s4_pos: int
    s5_pos: int | None
    conversion: str
    crystal_mhz: float | None
    corrected_pto: bool
    expected_low_mhz: float
    expected_high_mhz: float
    source_note: str


@dataclass(frozen=True)
class CenterSpectrum:
    segment: BandSegment
    pto_mhz: float
    frequency_hz: np.ndarray
    mixer_raw_vpp: np.ndarray
    filter_output_vpp: np.ndarray
    vfo_out_vpp: np.ndarray


SEGMENTS = (
    BandSegment("3.5-4.0 MHz", 1, None, "PTO + crystal", 7.50, False, 12.50, 13.00, "Y89-1"),
    BandSegment("7.0-7.5 MHz", 2, None, "PTO + crystal", 11.00, False, 16.00, 16.50, "Y89-2"),
    BandSegment("14.0-14.5 MHz", 3, None, "direct PTO", None, False, 5.00, 5.50, "direct"),
    BandSegment("21.0-21.5 MHz", 4, None, "PTO + crystal", 6.99, True, 12.00, 12.50, "Y89-3"),
    BandSegment("28.0-28.5 MHz", 5, 1, "PTO + crystal", 13.99, True, 19.00, 19.50, "Y1/S5"),
    BandSegment("28.5-29.0 MHz", 5, 2, "PTO + crystal", 14.49, True, 19.50, 20.00, "Y2/S5"),
    BandSegment("29.0-29.5 MHz", 5, 3, "PTO + crystal", 14.99, True, 20.00, 20.50, "Y3/S5"),
    BandSegment("29.5-30.0 MHz", 5, 4, "PTO + crystal", 15.49, True, 20.50, 21.00, "Y4/S5"),
)


def run_checked(command: list[str], description: str) -> None:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        print(completed.stdout, end="")
        print(completed.stderr, end="")
        raise SystemExit(
            f"{description} failed with exit code {completed.returncode}"
        )


def export_netlist() -> str:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    run_checked(
        [
            str(KICAD_CLI),
            "sch",
            "export",
            "netlist",
            "--format",
            "spice",
            "-o",
            str(BASE_NETLIST),
            str(SCHEMATIC),
        ],
        "KiCad netlist export",
    )
    return BASE_NETLIST.read_text(encoding="utf-8")


def format_frequency_mhz(frequency_mhz: float) -> str:
    return f"{frequency_mhz:.6f}".rstrip("0").rstrip(".")


def make_netlist(
    base_text: str,
    segment: BandSegment,
    pto_frequency_mhz: float,
) -> str:
    text, position_count = re.subn(
        r"(?m)^\.param S4_POS=\S+\s*$",
        f".param S4_POS={segment.s4_pos}",
        base_text,
    )
    if position_count != 1:
        raise ValueError(f"Expected one S4_POS parameter; found {position_count}")
    text, s5_position_count = re.subn(
        r"(?m)^\.param S5_POS=\S+\s*$",
        f".param S5_POS={segment.s5_pos or 1}",
        text,
    )
    if s5_position_count != 1:
        raise ValueError(
            f"Expected one S5_POS parameter; found {s5_position_count}"
        )

    pto_line = (
        "V_PTO_IDEAL net-_Q89-5-E_ 0 DC 1.7 "
        f"SIN(1.7 300m {format_frequency_mhz(pto_frequency_mhz)}Meg)"
    )
    text, pto_count = re.subn(
        r"(?m)^V_PTO_IDEAL\s+.*$",
        pto_line,
        text,
    )
    if pto_count != 1:
        raise ValueError(f"Expected one PTO source; found {pto_count}")

    fixture = ".save " + " ".join(VECTORS.values()) + "\n"
    text, end_count = re.subn(
        r"(?m)^\.end\s*$",
        fixture + ".end",
        text,
    )
    if end_count != 1:
        raise ValueError(f"Expected one .end directive; found {end_count}")
    return text


def run_case(
    tag: str, netlist_text: str
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    netlist_path = RUN_DIR / f"{tag}.cir"
    raw_path = RUN_DIR / f"{tag}.raw"
    log_path = RUN_DIR / f"{tag}.log"
    netlist_path.write_text(netlist_text, encoding="utf-8")
    run_checked(
        [
            str(NGSPICE),
            "-b",
            "-D",
            "ngbehavior=ltpsa",
            "-r",
            str(raw_path),
            "-o",
            str(log_path),
            str(netlist_path),
        ],
        f"ngspice run {tag}",
    )
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    row_match = re.search(r"No\. of Data Rows\s*:\s*(\d+)", log_text)
    if not row_match or int(row_match.group(1)) < 20_000:
        raise ValueError(f"{tag} did not produce at least 20,000 saved rows")
    if "error" in log_text.lower():
        raise ValueError(f"{tag} reported an error; see {log_path}")

    names, rows = ngspice_raw.parse_ascii_raw(raw_path)
    indices = {name: index for index, name in enumerate(names)}
    missing = {"time", *VECTORS.values()} - indices.keys()
    if missing:
        raise ValueError(f"{tag} is missing vectors: {sorted(missing)}")
    time_s = np.asarray([row[indices["time"]].real for row in rows])
    uniform_time_s = 60e-6 + np.arange(20_000) * 2e-9
    traces = {
        label: np.interp(
            uniform_time_s,
            time_s,
            np.asarray([row[indices[vector]].real for row in rows]),
        )
        for label, vector in VECTORS.items()
    }
    traces["mixer_raw_v"] = (
        traces["mixer_positive_v"] - traces["mixer_negative_v"]
    )
    return uniform_time_s, traces


def dominant_frequency_hz(time_s: np.ndarray, values: np.ndarray) -> float:
    selected = values - np.mean(values)
    delta_t = float(np.median(np.diff(time_s)))
    spectrum = np.abs(np.fft.rfft(selected * np.hanning(selected.size)))
    frequencies = np.fft.rfftfreq(selected.size, delta_t)
    valid = (frequencies >= 4e6) & (frequencies <= 25e6)
    valid_indices = np.flatnonzero(valid)
    return float(frequencies[valid_indices[int(np.argmax(spectrum[valid]))]])


def fitted_tone_vpp(
    time_s: np.ndarray, values: np.ndarray, frequency_hz: float
) -> float:
    angle = 2.0 * np.pi * frequency_hz * time_s
    design = np.column_stack(
        (np.sin(angle), np.cos(angle), np.ones(time_s.size))
    )
    coefficients, *_ = np.linalg.lstsq(design, values, rcond=None)
    return float(2.0 * np.hypot(coefficients[0], coefficients[1]))


def fft_vpp(
    time_s: np.ndarray, values: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return a Hann-windowed, one-sided FFT in volts peak-to-peak per bin."""
    centered = values - np.mean(values)
    window = np.hanning(centered.size)
    spectrum = np.fft.rfft(centered * window)
    frequency_hz = np.fft.rfftfreq(
        centered.size, float(np.median(np.diff(time_s)))
    )
    amplitude_vpp = 4.0 * np.abs(spectrum) / np.sum(window)
    amplitude_vpp[0] = 0.0
    return frequency_hz, amplitude_vpp


def make_center_spectrum(
    segment: BandSegment,
    pto_mhz: float,
    time_s: np.ndarray,
    traces: dict[str, np.ndarray],
) -> CenterSpectrum:
    frequency_hz, mixer_raw_vpp = fft_vpp(
        time_s, traces["mixer_raw_v"]
    )
    filter_frequency_hz, filter_output_vpp = fft_vpp(
        time_s, traces["filter_output_v"]
    )
    out_frequency_hz, vfo_out_vpp = fft_vpp(
        time_s, traces["vfo_out_v"]
    )
    if not (
        np.array_equal(frequency_hz, filter_frequency_hz)
        and np.array_equal(frequency_hz, out_frequency_hz)
    ):
        raise ValueError("FFT frequency grids do not match")
    return CenterSpectrum(
        segment=segment,
        pto_mhz=pto_mhz,
        frequency_hz=frequency_hz,
        mixer_raw_vpp=mixer_raw_vpp,
        filter_output_vpp=filter_output_vpp,
        vfo_out_vpp=vfo_out_vpp,
    )


def run_segment(
    base_text: str, segment: BandSegment
) -> tuple[dict[str, str | int | float], CenterSpectrum]:
    nominal_pto_points = (5.00, 5.25, 5.50)
    correction_mhz = 0.01 if segment.corrected_pto else 0.0
    actual_pto_points = tuple(
        frequency + correction_mhz for frequency in nominal_pto_points
    )
    expected_points = (
        segment.expected_low_mhz,
        (segment.expected_low_mhz + segment.expected_high_mhz) / 2.0,
        segment.expected_high_mhz,
    )
    dominant_points: list[float] = []
    desired_vpp_points: list[float] = []
    total_vpp_points: list[float] = []
    center_spectrum: CenterSpectrum | None = None

    segment_tag = (
        segment.dial_band.lower()
        .replace(" ", "")
        .replace(".", "p")
        .replace("-", "_")
    )
    for point_name, pto_mhz, expected_mhz in zip(
        ("low", "mid", "high"), actual_pto_points, expected_points
    ):
        tag = f"{segment_tag}_{point_name}"
        netlist_text = make_netlist(base_text, segment, pto_mhz)
        time_s, traces = run_case(tag, netlist_text)
        output_v = traces["vfo_out_v"]
        dominant_points.append(dominant_frequency_hz(time_s, output_v) / 1e6)
        desired_vpp_points.append(
            fitted_tone_vpp(time_s, output_v, expected_mhz * 1e6)
        )
        total_vpp_points.append(float(np.ptp(output_v)))
        if point_name == "mid":
            center_spectrum = make_center_spectrum(
                segment, pto_mhz, time_s, traces
            )

    frequency_errors_khz = [
        1e3 * (simulated - expected)
        for simulated, expected in zip(dominant_points, expected_points)
    ]
    maximum_frequency_error_khz = max(
        abs(error) for error in frequency_errors_khz
    )
    row: dict[str, str | int | float] = {
        "dial_band": segment.dial_band,
        "s4_pos": segment.s4_pos,
        "s5_pos": segment.s5_pos or "",
        "conversion": segment.conversion,
        "crystal_or_path": (
            f"{segment.crystal_mhz:.2f} MHz ({segment.source_note})"
            if segment.crystal_mhz is not None
            else segment.source_note
        ),
        "pto_source_range_mhz": (
            "5.01-5.51 corrected"
            if segment.corrected_pto
            else "5.00-5.50"
        ),
        "manual_output_range_mhz": (
            f"{segment.expected_low_mhz:.2f}-{segment.expected_high_mhz:.2f}"
        ),
        "simulated_low_mhz": dominant_points[0],
        "simulated_mid_mhz": dominant_points[1],
        "simulated_high_mhz": dominant_points[2],
        "coverage_result": (
            "PASS"
            if maximum_frequency_error_khz <= 25.0
            else "FAIL - unwanted product is dominant"
        ),
        "maximum_frequency_error_khz": maximum_frequency_error_khz,
        "desired_output_low_mvpp": 1e3 * desired_vpp_points[0],
        "desired_output_mid_mvpp": 1e3 * desired_vpp_points[1],
        "desired_output_high_mvpp": 1e3 * desired_vpp_points[2],
        "minimum_desired_output_mvpp": 1e3 * min(desired_vpp_points),
        "total_output_low_mvpp": 1e3 * total_vpp_points[0],
        "total_output_mid_mvpp": 1e3 * total_vpp_points[1],
        "total_output_high_mvpp": 1e3 * total_vpp_points[2],
    }
    if center_spectrum is None:
        raise ValueError(f"{segment.dial_band} center spectrum was not captured")
    return row, center_spectrum


def write_csv(rows: list[dict[str, str | int | float]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    frequency_columns = {
        "simulated_low_mhz",
        "simulated_mid_mhz",
        "simulated_high_mhz",
    }
    amplitude_columns = {
        "desired_output_low_mvpp",
        "desired_output_mid_mvpp",
        "desired_output_high_mvpp",
        "minimum_desired_output_mvpp",
        "total_output_low_mvpp",
        "total_output_mid_mvpp",
        "total_output_high_mvpp",
    }
    formatted_rows: list[dict[str, str | int | float]] = []
    for row in rows:
        formatted: dict[str, str | int | float] = {}
        for key, value in row.items():
            if key in frequency_columns:
                formatted[key] = f"{float(value):.6f}"
            elif key == "maximum_frequency_error_khz":
                formatted[key] = f"{float(value):.3f}"
            elif key in amplitude_columns:
                formatted[key] = f"{float(value):.3f}"
            else:
                formatted[key] = value
        formatted_rows.append(formatted)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(formatted_rows)


def write_fft_csv(spectra: list[CenterSpectrum]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FFT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "dial_band",
                "s4_pos",
                "s5_pos",
                "pto_mhz",
                "crystal_mhz",
                "wanted_mhz",
                "frequency_hz",
                "mixer_raw_vpp",
                "filter_output_vpp",
                "vfo_out_vpp",
            ]
        )
        for result in spectra:
            mask = (
                (result.frequency_hz >= 0.5e6)
                & (result.frequency_hz <= 25.0e6)
            )
            wanted_mhz = (
                result.pto_mhz + result.segment.crystal_mhz
                if result.segment.crystal_mhz is not None
                else result.pto_mhz
            )
            for index in np.flatnonzero(mask):
                writer.writerow(
                    [
                        result.segment.dial_band,
                        result.segment.s4_pos,
                        result.segment.s5_pos or "",
                        f"{result.pto_mhz:.6f}",
                        (
                            f"{result.segment.crystal_mhz:.6f}"
                            if result.segment.crystal_mhz is not None
                            else ""
                        ),
                        f"{wanted_mhz:.6f}",
                        f"{result.frequency_hz[index]:.6f}",
                        f"{result.mixer_raw_vpp[index]:.12e}",
                        f"{result.filter_output_vpp[index]:.12e}",
                        f"{result.vfo_out_vpp[index]:.12e}",
                    ]
                )


def plot_fft_group(
    spectra: list[CenterSpectrum], output: Path, title: str
) -> None:
    os.environ.setdefault(
        "MPLCONFIGDIR", str(GENERATED_DIR / "matplotlib")
    )
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(
        2,
        2,
        figsize=(12.5, 8.0),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    stage_lines = (
        ("mixer_raw_vpp", "MC1496 raw differential output", "#9467bd"),
        ("filter_output_vpp", "Selected filter / Q89-1 gate", "#1f77b4"),
        ("vfo_out_vpp", "Loaded VFO OUT (50 Ω)", "#d62728"),
    )
    for axis, result in zip(axes.flat, spectra):
        mask = (
            (result.frequency_hz >= 0.5e6)
            & (result.frequency_hz <= 25.0e6)
        )
        frequency_mhz = result.frequency_hz[mask] / 1e6
        for attribute, label, color in stage_lines:
            amplitude_vpp = getattr(result, attribute)[mask]
            amplitude_dbvpp = 20.0 * np.log10(
                np.maximum(amplitude_vpp, 1e-12)
            )
            axis.plot(
                frequency_mhz,
                amplitude_dbvpp,
                color=color,
                linewidth=0.9,
                label=label,
            )

        if result.segment.crystal_mhz is None:
            markers = ((result.pto_mhz, "PTO / direct"),)
        else:
            markers = (
                (
                    abs(result.segment.crystal_mhz - result.pto_mhz),
                    "difference",
                ),
                (result.pto_mhz, "PTO"),
                (result.segment.crystal_mhz, "crystal"),
                (
                    result.segment.crystal_mhz + result.pto_mhz,
                    "wanted sum",
                ),
            )
        for frequency_mhz_value, marker_label in markers:
            axis.axvline(
                frequency_mhz_value,
                color="#555555",
                linewidth=0.7,
                alpha=0.55,
            )
            axis.text(
                frequency_mhz_value + 0.08,
                -4.0,
                f"{marker_label}\n{frequency_mhz_value:.2f}",
                rotation=90,
                va="top",
                ha="left",
                fontsize=7.5,
                color="#333333",
            )
        axis.set_title(
            f"{result.segment.dial_band} dial — S4={result.segment.s4_pos}"
            + (
                f", S5={result.segment.s5_pos}"
                if result.segment.s5_pos is not None
                else ""
            ),
            loc="left",
        )
        axis.set_xlim(0.5, 25.0)
        axis.set_ylim(-120.0, 0.0)
        axis.grid(True, alpha=0.25)
        axis.set_ylabel("FFT amplitude (dBVpp/bin)")
        axis.set_xlabel("Frequency (MHz)")

    handles, labels = axes.flat[0].get_legend_handles_labels()
    figure.legend(handles, labels, loc="outside lower center", ncols=3)
    figure.suptitle(
        f"{title}\n"
        "Band-center transient, 60–100 µs; Hann-window one-sided FFT"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=180)
    plt.close(figure)


def plot_fft_figures(spectra: list[CenterSpectrum]) -> None:
    if len(spectra) != 8:
        raise ValueError(f"Expected eight band segments; found {len(spectra)}")
    plot_fft_group(
        spectra[:4],
        FFT_HF_PNG,
        "80289 VFO mixing and switched-filter selection: 80–15 meters",
    )
    plot_fft_group(
        spectra[4:],
        FFT_10M_PNG,
        "80289 VFO mixing and switched-filter selection: 10-meter segments",
    )


def main() -> None:
    base_text = export_netlist()
    results = [run_segment(base_text, segment) for segment in SEGMENTS]
    rows = [row for row, _ in results]
    spectra = [spectrum for _, spectrum in results]
    write_csv(rows)
    write_fft_csv(spectra)
    plot_fft_figures(spectra)
    for row in rows:
        print(
            f"{row['dial_band']}: "
            f"{row['simulated_low_mhz']:.3f}/"
            f"{row['simulated_mid_mhz']:.3f}/"
            f"{row['simulated_high_mhz']:.3f} MHz, "
            f"min desired {row['minimum_desired_output_mvpp']:.1f} mVpp"
        )
    print(f"Coverage CSV: {OUTPUT_CSV.relative_to(ROOT)}")
    print(f"FFT CSV: {FFT_CSV.relative_to(ROOT)}")
    print(f"FFT figures: {FIGURE_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
