"""Coverage for the new shipped Gate2 options and the V56 champion adapter."""
import unittest
from pathlib import Path

import numpy as np

import gate1_server as server

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
HTML = (HERE / "pipeline_all_in_one.html").read_text(encoding="utf-8")
CATALOG = (ROOT / "HTML_AND_MODELS_CATALOG.md").read_text(encoding="utf-8")

SUPPORTED_NEW = {
    "gate2v20_aux", "gate2v23_crnn50x30", "gate2v24_crnn148x60",
    "gate2v25", "gate2v25_phraseconcat", "gate2v26", "gate2v26_phraseconcat_neg",
    "gate2v28a_5win", "gate2v28b_9win", "gate2v29_deep9", "gate2v29b_wide9",
    "gate2v34a_std", "gate2v34b_finehop", "gate2v36_17win", "gate2v37_9win_neg",
    "gate2v38_crnn9", "gate2v40b_9win_attention", "gate2v41_specaugmix", "gate2v42_reverb",
    "gate2v46_impwarp", "gate2v47_windrop_melwarp", "gate2v48_audiopack",
    "gate2v49_warpdilatedneg", "gate2v50_channelshuffle", "gate2v52_adjswap",
    "gate2v53_melbin_dropout", "gate2v56_v54", "gate2v56_v54b", "gate2v57_pidgate",
}
DISABLED_NEW = {
    "gate2v20_phonecascade", "gate2v27a_3winalign", "gate2v27c_meldelta",
    "gate2v39_36ch_derivcum", "gate2v40a_18ch_deriv", "gate2v40c_18ch_deriv_attention",
    "gate2v45_keywordpairs", "gate2v51_realchannel",
}
NEW_FOLDERS = (
    "Gate2V20_PhoneCascade_ship_EXPERIMENTAL_20261018",
    "Gate2V20_PhonemeAux_ship_EXPERIMENTAL_20261018",
    "Gate2V23_CRNN50x30_ship_EXPERIMENTAL_20261017",
    "Gate2V24_CRNN148x60_ship_EXPERIMENTAL_20261017",
    "Gate2V25_PhraseConcat_ship_EXPERIMENTAL_20261019",
    "Gate2V25_ship_EXPERIMENTAL_20261018",
    "Gate2V26_PhraseConcat_NEG_ship_EXPERIMENTAL_20261019",
    "Gate2V26_ship_EXPERIMENTAL_20261018",
    "Gate2V27A_3WinAlign_ship_EXPERIMENTAL_20261019",
    "Gate2V27C_MelDelta_ship_EXPERIMENTAL_20261019",
    "Gate2V28A_5WinSlide_ship_EXPERIMENTAL_20261019",
    "Gate2V28B_9WinSlide05_ship_EXPERIMENTAL_20261019",
    "Gate2V29_Deep9WinSlide_ship_EXPERIMENTAL_20261019",
    "Gate2V29B_Wide9WinSlide_ship_EXPERIMENTAL_20261019",
    "Gate2V34A_StdFrontend_ship_EXPERIMENTAL_20261019",
    "Gate2V34B_FineHop10ms5ms_ship_EXPERIMENTAL_20261019",
    "Gate2V36_17WinSlide4s_ship_EXPERIMENTAL_20261019",
    "Gate2V37_9WinSlide_NEG_ship_EXPERIMENTAL_20261019",
    "Gate2V38_CRNN_9WinSlide_ship_EXPERIMENTAL_20261019",
    "Gate2V39_36Ch_SlideDerivCum_ship_EXPERIMENTAL_20261019",
    "Gate2V40A_18ChDeriv_ship_EXPERIMENTAL_20261019",
    "Gate2V40B_9WinAttention_ship_EXPERIMENTAL_20261019",
    "Gate2V40C_18ChDerivAttention_ship_EXPERIMENTAL_20261019",
    "Gate2V41_SpecAugMix_ship_EXPERIMENTAL_20261019",
    "Gate2V42_ReverbMicSim_ship_EXPERIMENTAL_20261019",
    "Gate2V45_KeywordPairs_ship_EXPERIMENTAL_20261019",
    "Gate2V46_ImpWarp_ship_EXPERIMENTAL_20261020",
    "Gate2V47_WinDropout_MelWarp_ship_EXPERIMENTAL_20261020",
    "Gate2V48_AudioPack_ship_EXPERIMENTAL_20261020",
    "Gate2V49_WarpDilatedNEG_ship_EXPERIMENTAL_20261020",
    "Gate2V50_ChannelShuffle_ship_EXPERIMENTAL_20261020",
    "Gate2V51_RealChannel_ship_EXPERIMENTAL_20261020",
    "Gate2V52_AdjSwap_ship_EXPERIMENTAL_20261020",
    "Gate2V53_MelBinDropout_ship_EXPERIMENTAL_20261020",
    "Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020",
    "Gate2V57_PIDGate_ship_EXPERIMENTAL_20261021",
)


class TestNewGate2Options(unittest.TestCase):
    def test_verified_packages_are_registered_with_existing_float16_artifacts(self):
        self.assertTrue(SUPPORTED_NEW <= set(server.GATE2_PACKAGE_RUNNERS))
        for model_id in SUPPORTED_NEW:
            package_dir, relative_model, _ = server.GATE2_PACKAGE_RUNNERS[model_id]
            self.assertTrue((package_dir / relative_model).is_file(), model_id)

    def test_unadapted_candidates_are_disabled_but_visible(self):
        for model_id in DISABLED_NEW:
            self.assertIn(f'value="{model_id}" disabled', HTML, model_id)
            self.assertIn(model_id, server.GATE2_DISABLED_CANDIDATES)

    def test_every_new_shipping_folder_is_in_the_catalog(self):
        for folder in NEW_FOLDERS:
            self.assertIn(folder, CATALOG, folder)
        self.assertIn("V56", CATALOG)
        self.assertIn("V54b", CATALOG)

    def test_default_model_remains_v21p(self):
        self.assertIn('value="gate2v21p" selected', HTML)

    def test_slide_feature_builder_preserves_center_channel_and_pads_shift(self):
        base = np.zeros((148, 60), dtype=np.float32)
        offsets = (-50, -38, -25, -12, 0, 12, 25, 38, 50)
        pad = -0.14782163
        result = server._slide_window_features(base, offsets, pad)
        self.assertEqual(result.shape, (148, 60, 9))
        np.testing.assert_array_equal(result[:, :, 4], base)
        np.testing.assert_allclose(result[:50, :, 0], pad)

    def test_area_resize_uses_area_average(self):
        source = np.array([[1.0, 3.0], [5.0, 7.0]], dtype=np.float32)
        resized = server._resize_area(source, 1, 1)
        self.assertEqual(resized.shape, (1, 1))
        self.assertAlmostEqual(float(resized[0, 0]), 4.0)

    def test_v56_pid_profiles_expose_accuracy_and_rejection_champions(self):
        self.assertEqual(server.GATE2_PID_CONFIGS["gate2v56_v54"]["tau"], 0.4)
        self.assertFalse(server.GATE2_PID_CONFIGS["gate2v56_v54"]["margin_mode"])
        self.assertEqual(server.GATE2_PID_CONFIGS["gate2v56_v54b"]["kc"], 2.0)
        self.assertTrue(server.GATE2_PID_CONFIGS["gate2v56_v54b"]["margin_mode"])


if __name__ == "__main__":
    unittest.main()
