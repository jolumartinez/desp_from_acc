from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from desp_desktop_app.tools.download_nied_akth10 import parse_nied_ascii


class NiedConverterTests(unittest.TestCase):
    def test_ascii_scale_and_time_axis(self) -> None:
        headers = [
            ("Origin Time", "2011/03/11 14:46:00"),
            ("Lat.", "38.103"),
            ("Lon.", "142.860"),
            ("Depth. (km)", "24"),
            ("Mag.", "9.0"),
            ("Station Code", "AKTH10"),
            ("Station Lat.", "40.3002"),
            ("Station Lon.", "140.5812"),
            ("Station Height(m)", "85"),
            ("Record Time", "2011/03/11 14:47:21"),
            ("Sampling Freq(Hz)", "100Hz"),
            ("Duration Time(s)", "0.04"),
            ("Dir.", "E-W"),
            ("Scale Factor", "2000(gal)/1000"),
            ("Max Acc. (gal)", "8"),
            ("Last Correction", "2011/03/11 14:47:06"),
            ("Memo.", "test"),
        ]
        content = "\n".join(f"{key:<18}{value}" for key, value in headers) + "\n1 2 3 4\n"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.EW2"
            path.write_text(content, encoding="ascii")
            time_s, acceleration, metadata = parse_nied_ascii(path)
        np.testing.assert_allclose(time_s, [0.0, 0.01, 0.02, 0.03])
        np.testing.assert_allclose(acceleration, [0.02, 0.04, 0.06, 0.08])
        self.assertEqual(metadata["Station Code"], "AKTH10")


if __name__ == "__main__":
    unittest.main()
