import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import n60_5x12_beam_params as n60
import evaluate_n60_5x12 as eval_n60


class N60BeamParamsTest(unittest.TestCase):
    def test_geometry_channel_order(self):
        geometry = n60.build_geometry()
        self.assertEqual(len(geometry["positions"]), 60)
        self.assertEqual(len(geometry["normals"]), 60)
        for ch in range(60):
            self.assertEqual(int(geometry["unit_ids"][ch]), ch // 12)
            self.assertEqual(int(geometry["element_ids"][ch]), ch % 12)

    def test_normals_are_unit_length(self):
        geometry = n60.build_geometry()
        for normal in geometry["normals"]:
            self.assertAlmostEqual(float((normal * normal).sum()) ** 0.5, 1.0, places=6)

    def test_reverse_side_units_are_attenuated_for_positive_azimuth(self):
        gains = n60.unit_cosine_gains(30.0)
        self.assertGreater(gains[4], gains[0])
        self.assertGreater(gains[3], gains[1])

    def test_broadside_unit_gains_are_symmetric(self):
        gains = n60.unit_cosine_gains(0.0)
        self.assertAlmostEqual(gains[0], gains[4], places=6)
        self.assertAlmostEqual(gains[1], gains[3], places=6)

    def test_focus_params_ranges(self):
        for mode in (n60.MODE_UNIFORM, n60.MODE_UNIT_COSINE, n60.MODE_UNIT_COSINE_HAMMING):
            result = n60.calculate_focus_params(distance_mm=2000, az_deg=30, el_deg=0, mode=mode)
            self.assertEqual(len(result.amplitudes), 60)
            self.assertEqual(len(result.phases), 60)
            self.assertTrue(all(0 <= amp <= 255 for amp in result.amplitudes))
            self.assertTrue(all(0 <= phase < 2500 for phase in result.phases))
            self.assertLessEqual(result.combined_angle_deg, n60.MAX_STEER_DEG + 1e-6)

    def test_horizontal_optimization_case_count(self):
        self.assertEqual(len(eval_n60.DISTANCES_M) * len(eval_n60.AZIMUTHS_DEG) * len(eval_n60.ELEVATIONS_DEG), 65)
        self.assertEqual(eval_n60.ELEVATIONS_DEG, (0.0,))

    def test_optimized_dbc_margin_table_lookup(self):
        table = [{
            "distance_mm": 2000,
            "az_deg": 30.0,
            "el_deg": 0.0,
            "amplitudes": [i / 59.0 for i in range(60)],
        }]
        result = n60.calculate_focus_params(
            distance_mm=2000,
            az_deg=30,
            el_deg=0,
            mode=n60.MODE_OPTIMIZED_DBC_MARGIN,
            optimized_table=table,
        )
        self.assertEqual(result.amplitudes[0], 0)
        self.assertEqual(result.amplitudes[-1], 255)
        self.assertTrue(all(0 <= amp <= 255 for amp in result.amplitudes))
        self.assertTrue(all(0 <= phase < 2500 for phase in result.phases))

    def test_focus_limits(self):
        result = n60.calculate_focus_params(distance_mm=99999, az_deg=90, el_deg=90)
        self.assertEqual(result.distance_mm, n60.MAX_DISTANCE_MM)
        self.assertLessEqual(result.combined_angle_deg, n60.MAX_STEER_DEG + 1e-6)


if __name__ == "__main__":
    unittest.main()
