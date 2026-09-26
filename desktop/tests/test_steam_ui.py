"""The Steam UI driver must select the installed Time Spy artwork only."""
import unittest
from unittest.mock import Mock, patch

import cv2
import numpy as np
from PIL import Image

import steam_ui


class SteamUiTests(unittest.TestCase):
    def test_card_match_handles_dpi_scale_and_ignores_similar_tile(self):
        rng = np.random.default_rng(42)
        art = rng.integers(0, 255, (160, 360, 3), dtype=np.uint8)
        canvas = np.full((650, 900, 3), 225, dtype=np.uint8)
        scaled = cv2.resize(art, None, fx=1.2, fy=1.2)
        canvas[250:442, 330:762] = scaled
        canvas[20:212, 20:452] = np.flip(scaled, axis=1)
        found = steam_ui._match_card(Image.fromarray(canvas), Image.fromarray(art))
        self.assertGreater(found[0], .95)
        self.assertAlmostEqual(found[1], 546, delta=5)
        self.assertAlmostEqual(found[2], 346, delta=5)

    def test_wait_route_never_accepts_extreme_preset(self):
        doc = Mock()
        doc.GetValuePattern.return_value.Value = "https://127.0.0.1/view.html#TEST_DETAILS/TIME_SPY_EXTREME"
        with patch.object(steam_ui, "_document", return_value=doc), \
             patch.object(steam_ui.time, "monotonic", side_effect=[0, 2]), \
             patch.object(steam_ui.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "이동하지 못"):
                steam_ui._wait_route(Mock(), steam_ui._DETAIL_ROUTE, 1)

    def test_detail_waits_for_controls_after_route_changes(self):
        loading, ready = Mock(), Mock()
        for document in (loading, ready):
            document.GetValuePattern.return_value.Value = "https://127.0.0.1/view.html" + steam_ui._DETAIL_ROUTE
        loading.TextControl.return_value.Exists.return_value = False
        ready.TextControl.return_value.Exists.return_value = True
        ready.HyperlinkControl.return_value.Exists.return_value = True
        with patch.object(steam_ui, "_document", side_effect=[loading, ready]), \
             patch.object(steam_ui.time, "monotonic", side_effect=[0, .5]), \
             patch.object(steam_ui.time, "sleep"):
            self.assertIs(steam_ui._wait_detail_ready(Mock(), 1), ready)

    def test_cancel_before_run_never_clicks_benchmark(self):
        window, document, control = Mock(), Mock(), Mock()
        control.Exists.return_value = True
        document.HyperlinkControl.return_value = control
        cancel = Mock()
        cancel.is_set.return_value = True
        with patch.object(steam_ui, "_find_window", return_value=window), \
             patch.object(steam_ui, "_document", return_value=document), \
             patch.object(steam_ui, "_route", return_value=steam_ui._DETAIL_ROUTE), \
             patch.object(steam_ui, "_wait_detail_ready", return_value=document):
            steam_ui.launch_timespy("C:\\3DMark.exe", cancel_event=cancel)
        control.Click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
