"""Regression tests for the HTML/app and Gate 2 model catalog."""
import unittest
from pathlib import Path

import gate1_server as server

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent
EXERCISE_ROOT = HERE.parents[2]
DASHBOARD = (HERE / "pipeline_all_in_one.html").read_text(encoding="utf-8")
CATALOG = EXERCISE_ROOT / "HTML_AND_MODELS_CATALOG.md"

PACKAGE_MODEL_IDS = {
    "gate2v16", "gate2v18", "gate2v19", "gate2v19p", "gate2v21",
    "gate2v21p", "gate2v22", "gate2v22s",
}
SELECTOR_MODEL_IDS = PACKAGE_MODEL_IDS | {"gate2v2", "gate2v6_keras"}


class TestGate2ModelCatalog(unittest.TestCase):
    def test_all_shipped_tflite_packages_have_registered_runners_and_assets(self):
        missing = PACKAGE_MODEL_IDS - set(server.GATE2_PACKAGE_RUNNERS)
        self.assertEqual(missing, set(), f"unregistered Gate 2 package models: {sorted(missing)}")
        for model_id in PACKAGE_MODEL_IDS:
            package_dir, relative_model, _ = server.GATE2_PACKAGE_RUNNERS[model_id]
            self.assertTrue((package_dir / relative_model).is_file(), model_id)

    def test_dashboard_selector_lists_each_runtime_gate2_model(self):
        for model_id in SELECTOR_MODEL_IDS:
            self.assertIn(f'value="{model_id}"', DASHBOARD, model_id)
        self.assertIn('value="gate2v21p" selected', DASHBOARD)

    def test_flex_dependent_v6_tflite_asset_is_not_selectable_for_the_pi_runner(self):
        self.assertNotIn("gate2v6_tflite", server.GATE2_PACKAGE_RUNNERS)
        self.assertNotIn('value="gate2v6_tflite"', DASHBOARD)
        catalog = CATALOG.read_text(encoding="utf-8")
        self.assertIn("FlexTensorListReserve", catalog)
        self.assertIn("not Pi-compatible", catalog)

    def test_catalog_covers_every_html_page_and_gate2_package(self):
        self.assertTrue(CATALOG.is_file(), f"missing catalog: {CATALOG}")
        catalog = CATALOG.read_text(encoding="utf-8")
        html_pages = sorted(EXERCISE_ROOT.rglob("*.html"))
        for page in html_pages:
            relative = page.relative_to(EXERCISE_ROOT).as_posix()
            self.assertIn(relative, catalog, relative)
        self.assertIn("pipeline_all_in_one.thml", catalog)
        for package_name in (
            "Gate2V16_ship_20261017", "Gate2V18_ship_20261017",
            "Gate2V19_ship_20261017", "Gate2V19P_ship_EXPERIMENTAL_20261017",
            "Gate2V21_ship_20261017", "Gate2V21P_ship_EXPERIMENTAL_20261017",
            "Gate2V22_ship_20261017", "Gate2V22_SilenceNeg_ship_EXPERIMENTAL_20261017",
            "Gate2V6_ship_20261013",
        ):
            self.assertIn(package_name, catalog)


if __name__ == "__main__":
    unittest.main()
