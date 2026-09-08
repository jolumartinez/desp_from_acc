#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


DEFAULT_URL = (
    "https://www.kyoshin.bosai.go.jp/kyoshin/download/kik/data/2011/03/"
    "20110311144600/AKTH101103111446.EW2"
)


def parse_nied_ascii(path: Path) -> tuple[np.ndarray, np.ndarray, dict[str, str | float]]:
    lines = Path(path).read_text(encoding="ascii", errors="replace").splitlines()
    if len(lines) < 18:
        raise ValueError("El archivo no tiene una cabecera K-NET ASCII completa.")
    headers: dict[str, str] = {}
    for line in lines[:17]:
        headers[line[:18].strip()] = line[18:].strip()
    sampling_match = re.search(r"([0-9.]+)", headers.get("Sampling Freq(Hz)", ""))
    scale_match = re.search(r"([0-9.eE+-]+)\s*\(gal\)\s*/\s*([0-9.eE+-]+)", headers.get("Scale Factor", ""))
    if not sampling_match or not scale_match:
        raise ValueError("No se pudieron interpretar la frecuencia de muestreo o el factor de escala.")
    sampling_rate = float(sampling_match.group(1))
    scale_gal = float(scale_match.group(1)) / float(scale_match.group(2))
    raw = np.fromstring(" ".join(lines[17:]), sep=" ", dtype=float)
    if raw.size < 4:
        raise ValueError("El archivo no contiene suficientes muestras.")
    time_s = np.arange(raw.size, dtype=float) / sampling_rate
    acceleration_mps2 = raw * scale_gal * 0.01
    metadata: dict[str, str | float] = {
        **headers,
        "sampling_rate_hz": sampling_rate,
        "scale_gal_per_count": scale_gal,
        "acceleration_unit": "m/s2",
    }
    return time_s, acceleration_mps2, metadata


def download(url: str, target: Path, username: str, password: str) -> None:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {token}", "User-Agent": "DESP-Studio/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            target.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("NIED rechazó las credenciales o el acceso al registro.") from exc
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga y convierte el registro AKTH10 E-W de NIED.")
    parser.add_argument("--username", default=os.getenv("NIED_USERNAME", ""), help="Usuario registrado en NIED.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL K-NET ASCII, modificable si NIED cambia la ruta.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "validation_data" / "external" / "nied_akth10",
    )
    args = parser.parse_args()
    username = args.username.strip() or input("Usuario NIED: ").strip()
    password = os.getenv("NIED_PASSWORD") or getpass.getpass("Contraseña NIED: ")
    if not username or not password:
        parser.error("Se requieren las credenciales de una cuenta NIED autorizada.")

    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    raw_path = destination / "AKTH101103111446.EW2"
    download(args.url, raw_path, username, password)
    time_s, acceleration, metadata = parse_nied_ascii(raw_path)
    with (destination / "acceleration.txt").open("w", encoding="utf-8") as target:
        target.write(f"# SamplingRate = {metadata['sampling_rate_hz']}\n")
        target.write("time,acceleration_ew_surface\n")
        np.savetxt(
            target,
            np.column_stack((time_s, acceleration)),
            delimiter=",",
            fmt="%.10e",
        )
    provenance = {
        "source": "NIED K-NET/KiK-net",
        "url": args.url,
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "station": "AKTH10 Oodate",
        "component": "E-W surface (EW2)",
        "metadata": metadata,
    }
    (destination / "provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(destination / "acceleration.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
