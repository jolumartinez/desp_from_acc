from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from desp_desktop_app.core.io import available_channels, crop_signal, load_signal, scan_txt_files


class TextInputTests(unittest.TestCase):
    def test_multichannel_comma_file_and_unit_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.txt"
            path.write_text(
                "# SamplingRate = 20\n"
                "time,ax,ay\n"
                "0.00,100,0\n0.05,200,1\n0.10,300,2\n0.15,400,3\n",
                encoding="utf-8",
            )
            self.assertEqual(available_channels(path), ["ax", "ay"])
            record = load_signal(path, "ax", "cm/s²")
            np.testing.assert_allclose(record.acceleration_mps2, [1.0, 2.0, 3.0, 4.0])
            self.assertEqual(record.sampling_rate_hz, 20.0)
            self.assertEqual(scan_txt_files(Path(temp)), [path])

    def test_headerless_whitespace_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.txt"
            path.write_text("0 0.1\n1 0.2\n2 0.3\n3 0.4\n", encoding="utf-8")
            record = load_signal(path, "channel_1", "g", 10.0)
            self.assertAlmostEqual(record.acceleration_mps2[0], 0.980665)
            self.assertEqual(record.sampling_rate_hz, 10.0)
            np.testing.assert_allclose(record.time_s, [0.0, 0.1, 0.2, 0.3])
            self.assertTrue(record.metadata["time_axis_reconstructed"])

    def test_irregular_time_requires_explicit_sampling_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.txt"
            path.write_text("time,ax\n0.0,0\n0.1,1\n0.2,2\n0.5,3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "muestreo uniforme"):
                load_signal(path, "ax", "m/s²")

    def test_crop_signal_uses_real_samples_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.txt"
            rows = ["time,ax", *(f"{index / 10:.1f},{index}" for index in range(11))]
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            record = load_signal(path, "ax", "m/s²")

            cropped = crop_signal(record, 0.15, 0.65)

            np.testing.assert_allclose(cropped.time_s, [0.0, 0.1, 0.2, 0.3, 0.4])
            np.testing.assert_allclose(cropped.acceleration_mps2, [2.0, 3.0, 4.0, 5.0, 6.0])
            self.assertAlmostEqual(cropped.metadata["crop_start_s"], 0.2)
            self.assertAlmostEqual(cropped.metadata["crop_end_s"], 0.6)
            self.assertEqual(cropped.metadata["original_samples"], 11)
            self.assertEqual(record.time_s.size, 11)

    def test_crop_signal_rejects_too_short_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.txt"
            path.write_text("time,ax\n0,0\n1,1\n2,2\n3,3\n4,4\n", encoding="utf-8")
            record = load_signal(path, "ax", "m/s²")
            with self.assertRaisesRegex(ValueError, "cuatro muestras"):
                crop_signal(record, 1.0, 2.0)


if __name__ == "__main__":
    unittest.main()
