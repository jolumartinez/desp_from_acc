from __future__ import annotations

import unittest

from desp_desktop_app.core.catalog import METHOD_BY_ID, METHOD_SPECS
from desp_desktop_app.core.engine import default_parameters
from desp_desktop_app.core.signal_ops import butterworth_order_from_specs


class ThesisPresetTests(unittest.TestCase):
    def test_appendix_pdf_destinations_are_physical_pages(self) -> None:
        destinations = {
            spec.method_id: (spec.thesis_page_label, spec.thesis_pdf_page)
            for spec in METHOD_SPECS
            if spec.reference_basis == "tesis"
        }
        self.assertEqual(
            destinations,
            {
                "trifunac_lee": ("43", 59),
                "chiu": ("58", 74),
                "converse_brady": ("71", 87),
                "boore": ("83", 99),
                "wang": ("96", 112),
                "darragh": ("110", 126),
                "park": ("122", 138),
            },
        )

    def test_filter_defaults_match_matlab_scripts(self) -> None:
        tl = default_parameters("trifunac_lee")
        self.assertEqual(
            (tl["filter_family"], tl["filter_phase"], tl["lowpass_order"], tl["lowpass_hz"], tl["highpass_order"], tl["highpass_hz"]),
            ("butterworth", "zero_phase", 1, 25.0, 1, 0.07),
        )

        chiu = default_parameters("chiu")
        self.assertEqual(chiu["highpass_design"], "specifications")
        self.assertEqual(
            (chiu["passband_hz"], chiu["stopband_hz"], chiu["passband_ripple_db"], chiu["stopband_attenuation_db"]),
            (0.25, 0.017, 0.5, 55.0),
        )
        self.assertEqual((chiu["lowpass_order"], chiu["lowpass_hz"]), (2, 30.0))
        self.assertEqual((chiu["acceleration_degree"], chiu["final_degree"], chiu["drift_correction"]), (1, 1, "velocity"))

        converse = default_parameters("converse_brady")
        self.assertEqual(converse["highpass_design"], "specifications")
        self.assertEqual(
            (converse["passband_hz"], converse["stopband_hz"], converse["passband_ripple_db"], converse["stopband_attenuation_db"]),
            (0.20, 0.0085, 0.5, 55.0),
        )
        self.assertEqual((converse["lowpass_order"], converse["lowpass_hz"]), (2, 25.0))
        self.assertEqual((converse["initial_pad_s"], converse["high_pad_factor"]), (2.0, 1.5))

        boore = default_parameters("boore")
        self.assertEqual((boore["filter_phase"], boore["velocity_degree"]), ("zero_phase", 2))
        self.assertEqual((boore["use_highpass"], boore["highpass_order"], boore["highpass_hz"]), (False, 4, 0.07))

        darragh = default_parameters("darragh")
        self.assertEqual((darragh["filter_phase"], darragh["lowpass_order"], darragh["lowpass_hz"]), ("zero_phase", 2, 25.0))

    def test_non_filter_defaults_match_matlab_scripts(self) -> None:
        wang = default_parameters("wang")
        self.assertEqual((wang["noise_metric"], wang["noise_multiplier"]), ("mean_abs", 1.03))
        self.assertEqual((wang["energy_fraction"], wang["post_degree"], wang["limit_post_event"]), (0.90, 2, True))
        self.assertEqual((wang["grid_points"], wang["step_search_mode"], wang["step_increment_fraction"]), (100, "analytic", 0.025))
        for spec in METHOD_SPECS:
            if spec.reference_basis != "tesis":
                continue
            self.assertEqual(default_parameters(spec.method_id)["integration"], "simpson")
        bunce = default_parameters("bunce_bridge")
        self.assertEqual(bunce["integration"], "trapezoid")
        self.assertEqual(bunce["quality_mode"], "shoulders")
        self.assertEqual(bunce["train_peak_source"], "geometry")
        self.assertEqual(
            (
                bunce["minimum_peak_spacing_s"],
                bunce["minimum_peak_width_s"],
                bunce["minimum_peak_prominence_mm"],
            ),
            (1.5, 1.5, 1.0),
        )

    def test_buttord_reproduces_thesis_design(self) -> None:
        order, cutoff = butterworth_order_from_specs(200.0, 0.25, 0.017, 0.5, 55.0)
        self.assertEqual(order, 3)
        self.assertAlmostEqual(cutoff, 0.1760673, places=6)
        self.assertEqual(METHOD_BY_ID["chiu"].thesis_page_label, "58")


if __name__ == "__main__":
    unittest.main()
