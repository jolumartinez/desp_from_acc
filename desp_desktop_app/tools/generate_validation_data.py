#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _write_case(
    root: Path,
    name: str,
    time_s: np.ndarray,
    acceleration_mps2: np.ndarray,
    truth_displacement_m: np.ndarray,
    description: str,
) -> None:
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    sampling_rate = 1.0 / float(np.median(np.diff(time_s)))
    second_channel = 0.35 * acceleration_mps2
    with (case_dir / "acceleration.txt").open("w", encoding="utf-8") as target:
        target.write(f"# SamplingRate = {sampling_rate:.12g}\n")
        target.write("time,acceleration_x,acceleration_y\n")
        np.savetxt(
            target,
            np.column_stack((time_s, acceleration_mps2, second_channel)),
            delimiter=",",
            fmt="%.10e",
        )
    np.savetxt(
        case_dir / "truth_displacement.csv",
        np.column_stack((time_s, truth_displacement_m)),
        delimiter=",",
        header="time_s,displacement_m",
        comments="",
        fmt="%.10e",
    )
    manifest = {
        "name": name,
        "description": description,
        "sampling_rate_hz": sampling_rate,
        "samples": int(time_s.size),
        "acceleration_unit": "m/s2",
        "truth_displacement_unit": "m",
        "generated": True,
    }
    (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def generate(root: Path) -> None:
    harmonic_fs = 100.0
    harmonic_time = np.arange(0.0, 40.0, 1.0 / harmonic_fs)
    angular_frequency = 2.0 * np.pi * 1.5
    harmonic_displacement = np.zeros_like(harmonic_time)
    harmonic_acceleration = np.zeros_like(harmonic_time)
    active = (harmonic_time >= 5.0) & (harmonic_time < 35.0)
    active_time = harmonic_time[active] - 5.0
    harmonic_displacement[active] = 0.006 * (1.0 - np.cos(angular_frequency * active_time))
    harmonic_acceleration[active] = 0.006 * angular_frequency**2 * np.cos(angular_frequency * active_time)
    _write_case(
        root,
        "synthetic_harmonic",
        harmonic_time,
        harmonic_acceleration,
        harmonic_displacement,
        "Movimiento armónico de 1.5 Hz entre ventanas en reposo de 5 s; desplazamiento final cero.",
    )

    residual_fs = 100.0
    residual_time = np.arange(0.0, 30.0, 1.0 / residual_fs)
    start_s, duration_s, permanent_m = 5.0, 5.0, 0.04
    phase = (residual_time - start_s) / duration_s
    active = (phase >= 0.0) & (phase <= 1.0)
    residual_displacement = np.zeros_like(residual_time)
    residual_displacement[active] = 0.5 * permanent_m * (1.0 - np.cos(np.pi * phase[active]))
    residual_displacement[phase > 1.0] = permanent_m
    residual_acceleration = np.zeros_like(residual_time)
    residual_acceleration[active] = 0.5 * permanent_m * (np.pi / duration_s) ** 2 * np.cos(np.pi * phase[active])
    _write_case(
        root,
        "synthetic_residual",
        residual_time,
        residual_acceleration,
        residual_displacement,
        "Transición cosenoidal suave hacia un desplazamiento permanente de 40 mm.",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera los casos sintéticos reproducibles de DESP Studio.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "validation_data" / "generated",
        help="Directorio de salida.",
    )
    args = parser.parse_args()
    generate(args.output.resolve())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
