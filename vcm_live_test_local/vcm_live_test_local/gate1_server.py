"""VCM monitor server: HTTP + WebSocket + exact TFLite inference for Gate 1v8,
Gate 2 v2 (combined), and the full pipeline (Gate 1 -> Gate 2 -> specialists).

Pages served:
  /                    -> vcm_monitor.html  (Gate 1 / Gate 2 / Pipeline tabs)
  /gate1_monitor.html  -> legacy single-page Gate 1 monitor

Browser captures 16 kHz mic and streams PCM over WebSocket. The server keeps a
rolling 5.92 s window per connection and, every 1 s, scores the active mode:
  gate1 : gate1v8 (148-frame)                -> Nova/Piattos/Negative probs
  gate2 : active gate2 model (148-frame)     -> 19-intent probs
  both  : gate1v8 -> (wake?) -> gate2 model -> routed specialist (gateN/gate4/gate5)

Gate 2 model is selectable per connection via {type:"g2model", model}:
  gate2v2       gate2v2_float16.tflite (default, Pi-compatible)
  gate2v6_keras packaged Gate2V6 Keras source via the package infer.py preprocess
Fully local - no cloud.

Run:  python gate1_server.py   (default http://127.0.0.1:8765/)
"""

import asyncio
import base64
import contextlib
import csv
import importlib
import importlib.util
import json
import mimetypes
import os
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import librosa
import numpy as np
from aiohttp import WSMsgType, web

# Local modules: nc_dsp (noise canceller shared with the lab replay) and the
# recording lab (minute-long takes + whole-Gate-2 replays).
import nc_dsp
import recording_lab

mimetypes.add_type("text/html", ".thml")

HERE = Path(__file__).parent
PORT = 8765

SR = 16000
N_FFT = 1024
HOP = 640
N_MELS = 60
TARGET_74 = 74
TARGET_148 = 148
WIN_S = 5.92
WIN_SAMPLES = int(WIN_S * SR)

# Packaged Gate2V6 Keras source (reference runner: DemoApp/demo_server.py Gate2V6Runner).
GATE2V6_PKG = HERE.parents[1] / "Shipping" / "Gate2V6_ship_20261013"
SHIP_DIR = HERE.parents[1] / "Shipping"

# Assistant response audio packs. The 2026-10-22 ONEWORD pack ships a one-word
# reply for every Gate 2 intent plus a wake-ack pair per persona ("Yes?" / "Hi");
# the 2026-10-17 pack is the verbose CosyVoice3 persona bank. VCM_ASSISTANT_PACK
# (absolute path or folder name under Shipping/) selects a different pack first.
ASSISTANT_PACK_NAMES = (
    "Gate2_AssistantResponses_ONEWORD_20261022",
    "Gate2_AssistantResponses_20261017",
)


def _select_assistant_pack() -> Path:
    requested = os.environ.get("VCM_ASSISTANT_PACK", "").strip()
    names = ((requested,) + ASSISTANT_PACK_NAMES) if requested else ASSISTANT_PACK_NAMES
    for name in names:
        candidate = Path(name)
        if not candidate.is_absolute():
            candidate = SHIP_DIR / name
        if (candidate / "audio").is_dir():
            return candidate
    return SHIP_DIR / ASSISTANT_PACK_NAMES[0]


def _load_assistant_pack(
    pack: Path,
) -> tuple[set[tuple[str, str, int]], dict[tuple[str, str, int], str]]:
    """Index a pack's clips (persona, intent/wake slug, variant) and their text.

    Clip names are the contract: resp_<persona>_<slug>_<variant>.wav, where the
    slug itself contains underscores (play_music). Text comes from the pack's
    responses_manifest.csv when present, so the dashboard can caption what it
    actually speaks; a missing or differently-shaped CSV costs captions only.
    """
    clips: set[tuple[str, str, int]] = set()
    audio = pack / "audio"
    if audio.is_dir():
        for entry in audio.glob("resp_*.wav"):
            head, _, variant_text = entry.stem[len("resp_") :].rpartition("_")
            persona, _, slug = head.partition("_")
            if not (variant_text.isdigit() and persona and slug):
                continue
            clips.add((persona.lower(), slug.lower(), int(variant_text)))
    texts: dict[tuple[str, str, int], str] = {}
    try:
        with (pack / "responses_manifest.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            for row in csv.DictReader(handle):
                fields = {
                    (key or "").strip().lower(): (value or "").strip()
                    for key, value in row.items()
                }
                variant_text = fields.get("variant_index", "")
                persona = fields.get("persona", "").lower()
                slug = fields.get("intent", "").lower()
                if persona and slug and variant_text.isdigit():
                    texts[(persona, slug, int(variant_text))] = fields.get("text", "")
    except (OSError, csv.Error, UnicodeDecodeError):
        texts = {}
    return clips, texts


ASSISTANT_PACK = _select_assistant_pack()
ASSISTANT_AUDIO = ASSISTANT_PACK / "audio"
ASSISTANT_CLIPS, ASSISTANT_TEXTS = _load_assistant_pack(ASSISTANT_PACK)
ASSISTANT_PERSONAS = ("nova", "piattos")


def assistant_clip(persona: str | None, slug: str) -> dict[str, str] | None:
    """First shipped reply for a persona + intent-or-wake slug (variant 1, then 2).

    Falls back across personas so a missing clip for the latched wake profile
    still speaks; returns None when the pack has no such reply at all.
    """
    wanted = slug.strip().lower()
    spoken = (persona or "").strip().lower()
    order = [spoken] + [name for name in ASSISTANT_PERSONAS if name != spoken]
    for who in order:
        for variant in (1, 2):
            if (who, wanted, variant) in ASSISTANT_CLIPS:
                name = f"resp_{who}_{wanted}_{variant}.wav"
                return {
                    "url": "/assistant-responses/" + name,
                    "persona": who,
                    "text": ASSISTANT_TEXTS.get((who, wanted, variant), ""),
                }
    return None


# Shipped Gate2 TFLite packages (2026-10-17 upload). The P variants ship no
# preprocessing_spec.json; their manifests document the base version's scalar
# statistics as identical, so the runner falls back to the base package spec.
GATE2_PACKAGE_RUNNERS = {
    "gate2v16": (
        SHIP_DIR / "Gate2V16_ship_20261017",
        "tflite/gate2v16_float16.tflite",
        None,
    ),
    "gate2v18": (
        SHIP_DIR / "Gate2V18_ship_20261017",
        "tflite/gate2v18_float16.tflite",
        None,
    ),
    "gate2v19": (
        SHIP_DIR / "Gate2V19_ship_20261017",
        "tflite/gate2v19_float16.tflite",
        None,
    ),
    "gate2v19p": (
        SHIP_DIR / "Gate2V19P_ship_EXPERIMENTAL_20261017",
        "tflite/gate2v19p_float16.tflite",
        SHIP_DIR / "Gate2V19_ship_20261017",
    ),
    "gate2v20_aux": (
        SHIP_DIR / "Gate2V20_PhonemeAux_ship_EXPERIMENTAL_20261018",
        "tflite/gate2v20_phoneme_aux_intent_float16.tflite",
        None,
    ),
    "gate2v21": (
        SHIP_DIR / "Gate2V21_ship_20261017",
        "tflite/gate2v21_float16.tflite",
        None,
    ),
    "gate2v21p": (
        SHIP_DIR / "Gate2V21P_ship_EXPERIMENTAL_20261017",
        "tflite/gate2v21p_float16.tflite",
        SHIP_DIR / "Gate2V21_ship_20261017",
    ),
    "gate2v22": (
        SHIP_DIR / "Gate2V22_ship_20261017",
        "tflite/gate2v22_float16.tflite",
        None,
    ),
    "gate2v22s": (
        SHIP_DIR / "Gate2V22_SilenceNeg_ship_EXPERIMENTAL_20261017",
        "tflite/gate2v22s_float16.tflite",
        None,
    ),
    "gate2v23_crnn50x30": (
        SHIP_DIR / "Gate2V23_CRNN50x30_ship_EXPERIMENTAL_20261017",
        "tflite/gate2v23_crnn50x30_float16.tflite",
        None,
    ),
    "gate2v24_crnn148x60": (
        SHIP_DIR / "Gate2V24_CRNN148x60_ship_EXPERIMENTAL_20261017",
        "tflite/gate2v24_crnn148x60_float16.tflite",
        None,
    ),
    "gate2v25": (
        SHIP_DIR / "Gate2V25_ship_EXPERIMENTAL_20261018",
        "tflite/gate2v25_float16.tflite",
        SHIP_DIR / "Gate2V19_ship_20261017",
    ),
    "gate2v25_phraseconcat": (
        SHIP_DIR / "Gate2V25_PhraseConcat_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v25_phrase_concat_float16.tflite",
        None,
    ),
    "gate2v26": (
        SHIP_DIR / "Gate2V26_ship_EXPERIMENTAL_20261018",
        "tflite/gate2v26_float16.tflite",
        None,
    ),
    "gate2v26_phraseconcat_neg": (
        SHIP_DIR / "Gate2V26_PhraseConcat_NEG_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v26_phrase_concat_negclass_float16.tflite",
        None,
    ),
    "gate2v28a_5win": (
        SHIP_DIR / "Gate2V28A_5WinSlide_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v28a_float16.tflite",
        None,
    ),
    "gate2v28b_9win": (
        SHIP_DIR / "Gate2V28B_9WinSlide05_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v28b_float16.tflite",
        None,
    ),
    "gate2v29_deep9": (
        SHIP_DIR / "Gate2V29_Deep9WinSlide_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v29_deep9win_float16.tflite",
        None,
    ),
    "gate2v29b_wide9": (
        SHIP_DIR / "Gate2V29B_Wide9WinSlide_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v29b_wide9win_float16.tflite",
        None,
    ),
    "gate2v34a_std": (
        SHIP_DIR / "Gate2V34A_StdFrontend_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v34_std_float16.tflite",
        None,
    ),
    "gate2v34b_finehop": (
        SHIP_DIR / "Gate2V34B_FineHop10ms5ms_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v34_fine_float16.tflite",
        None,
    ),
    "gate2v36_17win": (
        SHIP_DIR / "Gate2V36_17WinSlide4s_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v36_17win_float16.tflite",
        None,
    ),
    "gate2v37_9win_neg": (
        SHIP_DIR / "Gate2V37_9WinSlide_NEG_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v37_slide_neg_float16.tflite",
        None,
    ),
    "gate2v38_crnn9": (
        SHIP_DIR / "Gate2V38_CRNN_9WinSlide_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v38_crnn9win_float16.tflite",
        None,
    ),
    "gate2v40b_9win_attention": (
        SHIP_DIR / "Gate2V40B_9WinAttention_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v40b_float16.tflite",
        None,
    ),
    "gate2v41_specaugmix": (
        SHIP_DIR / "Gate2V41_SpecAugMix_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v41_specaug_float16.tflite",
        None,
    ),
    "gate2v42_reverb": (
        SHIP_DIR / "Gate2V42_ReverbMicSim_ship_EXPERIMENTAL_20261019",
        "tflite/gate2v42_reverb_float16.tflite",
        None,
    ),
    "gate2v46_impwarp": (
        SHIP_DIR / "Gate2V46_ImpWarp_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v46_warp_float16.tflite",
        None,
    ),
    "gate2v47_windrop_melwarp": (
        SHIP_DIR / "Gate2V47_WinDropout_MelWarp_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v47_windrop_float16.tflite",
        None,
    ),
    "gate2v48_audiopack": (
        SHIP_DIR / "Gate2V48_AudioPack_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v48_audiopack_float16.tflite",
        None,
    ),
    "gate2v49_warpdilatedneg": (
        SHIP_DIR / "Gate2V49_WarpDilatedNEG_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v49_warp_dilated_neg_float16.tflite",
        None,
    ),
    "gate2v50_channelshuffle": (
        SHIP_DIR / "Gate2V50_ChannelShuffle_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v50_chshuffle_float16.tflite",
        None,
    ),
    "gate2v52_adjswap": (
        SHIP_DIR / "Gate2V52_AdjSwap_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v52_adjswap_float16.tflite",
        None,
    ),
    "gate2v53_melbin_dropout": (
        SHIP_DIR / "Gate2V53_MelBinDropout_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v53_melbin_dropout_float16.tflite",
        None,
    ),
    "gate2v56_v54": (
        SHIP_DIR / "Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v46_warp_float16.tflite",
        None,
    ),
    "gate2v56_v54b": (
        SHIP_DIR / "Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020",
        "tflite/gate2v46_warp_float16.tflite",
        None,
    ),
    "gate2v57_pidgate": (
        SHIP_DIR / "Gate2V57_PIDGate_ship_EXPERIMENTAL_20261021",
        "tflite/gate2v57_pidgate_float16.tflite",
        None,
    ),
    "gate2v58_smooth_pidgate": (
        SHIP_DIR / "Gate2V58_SmoothPIDGate_ship_EXPERIMENTAL_20261022",
        "gate2v58_smooth_pidgate_float16.tflite",
        None,
    ),
    "gate2v59_focal_warp": (
        SHIP_DIR / "Gate2V59_FocalLabelWarp_ship_EXPERIMENTAL_20261021",
        "tflite/gate2v59_focal_warp_float16.tflite",
        None,
    ),
    "gate2v60_phone_warp": (
        SHIP_DIR / "Gate2V60_PhoneWarp_ship_EXPERIMENTAL_20261021",
        "tflite/gate2v60_phone_warp_float16.tflite",
        None,
    ),
    "gate2v61_keyword_mix": (
        SHIP_DIR / "Gate2V61_KeywordMix_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v61_keyword_mix_float16.tflite",
        None,
    ),
    "gate2v62_speechtrim": (
        SHIP_DIR / "Gate2V62_SpeechTrim_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v62_speechtrim_float16.tflite",
        None,
    ),
    "gate2v63_pca_frontend": (
        SHIP_DIR / "Gate2V63_PCAFrontend_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v63_pca_frontend_float16.tflite",
        None,
    ),
    "gate2v64_paired_negatives": (
        SHIP_DIR / "Gate2V64_PairedNegatives_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64_paired_negatives_float16.tflite",
        None,
    ),
    "gate2v64c_stochmel": (
        SHIP_DIR / "Gate2V64C_StochMelNEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64c_stochmel_float16.tflite",
        None,
    ),
    "gate2v64d_expandedneg": (
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64c_stochmel_float16.tflite",
        None,
    ),
    "gate2v64p_paired_owner": (
        SHIP_DIR / "Gate2V64P_PairedOwner_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64p_paired_owner_float16.tflite",
        None,
    ),
    "gate2v65_stoch15k": (
        SHIP_DIR / "Gate2V65_StochNEG15K_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v65_stoch15k_float16.tflite",
        None,
    ),
    "gate2v66_clean_only": (
        SHIP_DIR / "Gate2V66_CleanOnly_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v66_clean_only_float16.tflite",
        None,
    ),
    # v66a_3extra / v66d_2extra / v66c_4extra are NOT listed here: their specs declare 12-, 11-
    # and 13-channel frontends (9 slide views plus AR(1) / log-cumulative-energy channels built by
    # the DGX-side extra_channels_a / _d / _c configs, which the packages do not ship). Feeding them
    # anything else would silently produce meaningless scores, so they are documented in
    # GATE2_DISABLED_CANDIDATES until those definitions arrive.
    "gate2v66m_mutation": (
        SHIP_DIR / "Gate2V66M_Mutation_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v66m_mutation_float16.tflite",
        None,
    ),
    "gate2v67_timeshift_only": (
        SHIP_DIR / "Gate2V67_TimeShiftOnly_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v67_timeshift_only_float16.tflite",
        None,
    ),
    "gate2v68_timeshift_neg": (
        SHIP_DIR / "Gate2V68_TIMESHIFT_NEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v68_timeshift_neg_float16.tflite",
        None,
    ),
    # v7x layered stacks: one base TFLite + one inference-time layer. The base
    # packages ship spec+labels; the layer parameters live in
    # GATE2_PID_CONFIGS / GATE2_TR_CONFIGS below (handoff 2026-10-22 ships).
    "gate2v72_v64d_pid": (
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64c_stochmel_float16.tflite",
        None,
    ),
    "gate2v76_v64d_tr": (
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v64c_stochmel_float16.tflite",
        None,
    ),
    # V77 (2026-10-24 ship): the NEG class retrained on SPEECH-OOS (LibriSpeech
    # + non-command word clips) over the V64d recipe. Its 20th class is named
    # NEG (not NEGATIVE) and is masked like NEGATIVE in the scoring paths.
    "gate2v77_speech_neg": (
        SHIP_DIR / "Gate2V77_SpeechOOS_NEG_ship_EXPERIMENTAL_20261022",
        "tflite/gate2v77_speech_neg_float16.tflite",
        None,
    ),
    # 2026-10-25/26 DGX batch: V64d-derived experiments that ship TFLite but no spec/labels.json.
    # Their manifests record "base: V64d weights" and their tensors are identical to V64d's
    # (1x148x60x9 -> 20 classes), so they reuse the V64d package's spec and label order.
    "gate2v81_timeshift_add": (
        SHIP_DIR / "Gate2V81_TimeShiftAdd_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v81_timeshift_add_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v82_speechoos2": (
        SHIP_DIR / "Gate2V82_SpeechOOS2_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v82_speechoos2_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v82b_speechoos2_w035": (
        SHIP_DIR / "Gate2V82B_SpeechOOS2_w035_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v82b_speechoos2_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v84_phonemeaux2": (
        SHIP_DIR / "Gate2V84_PhonemeAux2_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v84_phoneme_aux_intent_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v85_keywordsonly": (
        SHIP_DIR / "Gate2V85_KeywordsOnly_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v85_keywords_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v96a_confweight2x": (
        SHIP_DIR / "Gate2V96A_ConfWeight2x_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v96a_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v96c_v93b_rerun": (
        SHIP_DIR / "Gate2V96C_V93bReRun_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v96c_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v97d_warmuplr": (
        SHIP_DIR / "Gate2V97D_WarmupLR_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v97d_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v108_ownerft_v93b": (
        SHIP_DIR / "Gate2V108_OwnerFT_V93b_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v108_v93b_owner_ft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v109_ownerft_v96c": (
        SHIP_DIR / "Gate2V109_OwnerFT_V96c_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v109_v96c_owner_ft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v110_ownerft_aggr": (
        SHIP_DIR / "Gate2V110_OwnerFT_Aggr_ship_EXPERIMENTAL_20261026",
        "tflite/gate2v110_v93b_owner_ft_high_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    # V124 is the 2026-10-27 deploy stack: a softmax-average of V96c + V93b + V81
    # (nine-window members) and V20-PhonemeAux (center channel), with its own runner
    # class. The tflite path is a placeholder for the tuple shape; the ensemble loads
    # all four member weights itself from the package directory.
    "gate2v124_ensemble4way": (
        SHIP_DIR / "Gate2V124_Ensemble4way_ship_DEPLOY_20261027",
        "tflite/gate2v96c_float16.tflite",
        None,
    ),
    # 2026-10-27 sweep of every shipping package with weights: six more loadable
    # intent heads. V69/V70/V71 carry their own 19-class labels and spec; the
    # V86/V86B/V87-combo fine-tunes inherit the V64D spec and label order.
    "gate2v69": (
        SHIP_DIR / "Gate2V69_ship_EXPERIMENTAL_20261022",
        "tflite/v69_float16.tflite",
        None,
    ),
    "gate2v70": (
        SHIP_DIR / "Gate2V70_ship_EXPERIMENTAL_20261022",
        "tflite/v70_float16.tflite",
        None,
    ),
    "gate2v71": (
        SHIP_DIR / "Gate2V71_ship_EXPERIMENTAL_20261022",
        "tflite/v71_float16.tflite",
        None,
    ),
    "gate2v86_speechoos_mid": (
        SHIP_DIR / "Gate2V86_SpeechOOSMid_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v86_speechoos_mid_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v86b_v77mix": (
        SHIP_DIR / "Gate2V86B_V77mix_from_V64d_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v86b_v77mix_from_v64d_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v87_combo_intent": (
        SHIP_DIR / "Gate2V87_Combo_ship_EXPERIMENTAL_20261025",
        "tflite/gate2v87_combo_intent_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    # 2026-10-28 sweep of the v100+ packages: seven of them are standard
    # 20-class, 148x60x9 heads that ship weights only, so they inherit the V64D
    # spec and label order (the same fallback the other fine-tunes use). The
    # rest either ship no tflite or a shape this adapter cannot feed; those are
    # documented in GATE2_DISABLED_CANDIDATES below.
    "gate2v111c_bcresnet": (
        SHIP_DIR / "Gate2V111C_BCResNet_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v111c_bcresnet_softmax_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v112c_gmlp": (
        SHIP_DIR / "Gate2V112C_GMLP_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v112c_gmlp_softmax_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v113c_matchbox": (
        SHIP_DIR / "Gate2V113C_Matchbox_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v113c_matchbox_softmax_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v117a_miniecho": (
        SHIP_DIR / "Gate2V117A_MiniEcho_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v117a_mini_echo_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v118_ambienttail": (
        SHIP_DIR / "Gate2V118_AmbientTail_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v118_ambient_tail_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v119a_speedwide": (
        SHIP_DIR / "Gate2V119A_SpeedWide_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v119a_speed_wide_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v119b_speedbounded": (
        SHIP_DIR / "Gate2V119B_SpeedBounded_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v119b_speed_bounded_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    # 2026-10-29 batch: the v120-v142 runs, including the owner fine-tunes that were
    # sitting in the nested "Shipping Container 1" drop. Intents-only packages ship
    # their own 19-label list (the runner appends NEG); the fine-tunes inherit the
    # V64D spec and label order.
    "gate2v120_timewarp": (
        SHIP_DIR / "Gate2V120_TimeWarp_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v120_time_warp_float16.tflite",
        None,
    ),
    "gate2v121b_specaugonly": (
        SHIP_DIR / "Gate2V121B_SpecAugOnly_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v121b_specaug_only_float16.tflite",
        None,
    ),
    "gate2v126_mels180": (
        SHIP_DIR / "Gate2V126_Mels180_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v126_mels180_float16.tflite",
        None,
    ),
    "gate2v129_kw": (
        SHIP_DIR / "Gate2V129_KW_ship_EXPERIMENTAL_20261029",
        "tflite/gate2v129_kw_float16.tflite",
        None,
    ),
    "gate2v131_multiscaleauxkw": (
        SHIP_DIR / "Gate2V131_MultiScaleAuxKW_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v131_multiscale_aux_kw_intent_float16.tflite",
        None,
    ),
    "gate2v132_singlewordmassive": (
        SHIP_DIR / "Gate2V132_SingleWordMassive_ship_EXPERIMENTAL_20261027",
        "tflite/gate2v132_singleword_float16.tflite",
        None,
    ),
    "gate2v19p2_owner_vc": (
        SHIP_DIR / "Gate2V19P2_OwnerVC_ship_EXPERIMENTAL_20261029",
        "tflite/gate2v19p2_owner_vc_finetune_float16.tflite",
        SHIP_DIR / "Gate2V69_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v21p2_owner_vc": (
        SHIP_DIR / "Gate2V21P2_OwnerVC_ship_EXPERIMENTAL_20261029",
        "tflite/gate2v21p2_owner_vc_finetune_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v142_121b_ownerft": (
        SHIP_DIR / "Gate2v142_121b_specaug_only_OwnerFT_ship_EXPERIMENTAL_20261028",
        "tflite/gate2v142_121b_specaug_only_ownerft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v142_129_kw_ownerft": (
        SHIP_DIR / "Gate2v142_129_kw_OwnerFT_ship_EXPERIMENTAL_20261028",
        "tflite/gate2v142_129_kw_ownerft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v142_132_singleword_ownerft": (
        SHIP_DIR / "Gate2v142_132_singleword_OwnerFT_ship_EXPERIMENTAL_20261028",
        "tflite/gate2v142_132_singleword_ownerft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
    "gate2v142_135_distilled_ownerft": (
        SHIP_DIR / "Gate2v142_135_distilled_OwnerFT_ship_EXPERIMENTAL_20261028",
        "tflite/gate2v142_135_distilled_ownerft_float16.tflite",
        SHIP_DIR / "Gate2V64D_ExpandedNEG_ship_EXPERIMENTAL_20261022",
    ),
}

GATE2_DISABLED_CANDIDATES = {
    # 2026-10-29 batch: shipped but not feedable / not an intent head.
    "gate2v130_groupmultihot": "250 outputs (group multi-hot aux head): no decoding spec for the intent logits.",
    "gate2v66b_18extra": "27-channel frontend (1,148,60,27): needs the 18-extra channel builder the package does not ship.",
    "gate2v88_finegrained_d02": "94 outputs (fine-grained aux head), not a 19/20-class intent head.",
    "gate2v88b_finegrained_d005": "94 outputs (fine-grained aux head), not a 19/20-class intent head.",
    "gate2v88c_leakykw": "109 outputs (leaky-keyword aux head), not a 19/20-class intent head.",
    "gate2v89_multihot": "128 outputs (multi-hot aux head), not a 19/20-class intent head.",
    "gate2v126_mels180": "180-mel frontend whose filterbank recipe is not shipped. Loads and runs, but scores near chance (1-3/20 real clips) under every mel variant tried (librosa default, fmin/fmax variants, htk=True), so its features do not match training.",
    "gate2v121_specaugmixup": "Package ships no tflite (docs only).",
    "gate2v122_v20pamodern": "Package ships no tflite (docs only).",
    "gate2v138_doubledescent": "Analysis package (double-descent trajectory study): no tflite by design.",
    "gate2v111b_bcresnetfix": "INVALID run (training broken: missing softmax); superseded by v111c.",
    "gate2v112b_gmlpfix": "INVALID run (training broken: missing softmax); superseded by v112c.",
    # v100+ packages that cannot be fed or scored by this adapter:
    "gate2v102_distance": "18-channel frontend (1,148,60,18): needs the distance-channel builder the package does not ship.",
    "gate2v114_phonemeslots": "245 outputs (phoneme slot logits): no decoding spec shipped for the intent head.",
    "gate2v116_groupdistance": "5 group-distance outputs, not a 19/20-class intent head.",
    "gate2v115_discslotlogits": "Void run - no tflite (string-vs-int bug, fix queued upstream).",
    "gate2v20_phonecascade": "Two-stage phone-posterior cascade needs a custom cascade adapter.",
    "gate2v27a_3winalign": "Three-window alignment frontend needs a custom aligner.",
    "gate2v27c_meldelta": "Mel/delta/delta-delta frontend needs a custom feature builder.",
    "gate2v39_36ch_derivcum": "36-channel slide/derivative/cumulative frontend needs derived-stat handling.",
    "gate2v40a_18ch_deriv": "18-channel derivative frontend needs derived-stat handling.",
    "gate2v40c_18ch_deriv_attention": "18-channel derivative/attention frontend needs derived-stat handling.",
    "gate2v45_keywordpairs": "Package is missing labels.json and preprocessing_spec.json.",
    "gate2v51_realchannel": "Package is missing preprocessing_spec.json; channel recipe is unverified.",
    "gate2v66a_3extra": "12-channel frontend: 9 slide views plus 3 AR(1) coefficient channels from the DGX extra_channels_a config, which the package does not ship.",
    "gate2v66c_4extra": "13-channel frontend: 9 slide views plus 4 channels from the DGX extra_channels_c config, which the package does not ship.",
    "gate2v66d_2extra": "11-channel frontend: 9 slide views plus 2 log-cumulative-energy channels from the DGX extra_channels_d config, which the package does not ship.",
    "gate2v66c_partial": "Partial training run; package has no usable preprocessing spec.",
    "gate2v64dlc_partial": "Partial run (no preprocessing_spec.json).",
    "gate2v64pt_tempscaled": "Temperature-scaling calibration artefact, not a standalone model.",
    "gate2v55_sarimax_prior": "SARIMAX prior artefact, not a standalone model.",
    "gate2v80_conv3d": "Rank-5 input (1x148x60x9x1); needs a Conv3D adapter.",
    "gate2v83_oosbinarycascade": "Single binary output: a cascade rejection head, not a 19-class classifier.",
    "gate2v90_phonememultihot": "167 outputs (phoneme multi-hot aux head); the package ships no decoding spec.",
    "gate2v91_v77binary": "Single binary output derived from V77; no command labels to score.",
    "gate2v92a_graded": "167 outputs (graded/phoneme targets); no decoding spec shipped.",
    "gate2v92b_graded": "167 outputs (graded/phoneme targets); no decoding spec shipped.",
    "gate2v93a_depthonly": "No TFLite exported (keras/report only).",
    "gate2v93b_depthdetail": "No TFLite exported (keras/report only).",
    "gate2v94_sarimax_v93b": "No TFLite exported (keras/report only).",
    "gate2v95_cascadev93b": "No TFLite exported (keras/report only).",
    "gate2v98_fineoffset41": "No TFLite exported (keras/report only).",
    "gate2v100_attngap": "No TFLite: export blocked by Lambda layer serialization.",
    "gate2v101_crnn_v93b": "No TFLite exported; its own report records FAIL 87.14%.",
    "gate2v102_distancechannels": "18-channel frontend (distance-from-peak channels); the recipe is not shipped.",
    "gate2v106_pairdiscriminators": "Ships a training script and report only (per-confusion-pair discriminators), not a deployable model.",
    "gate2v107_distcompact": "148x549 compact feature layout whose recipe is not shipped; its own report records FAIL val 5.60%.",
}

GATE2_PID_CONFIGS = {
    "gate2v56_v54": {
        "tau": 0.4,
        "kp": 0.4,
        "ki": 0.05,
        "kd": 0.1,
        "kc": 0.0,
        "margin_mode": False,
    },
    "gate2v56_v54b": {
        "tau": 0.25,
        "kp": 0.6,
        "ki": 0.02,
        "kd": 0.1,
        "kc": 2.0,
        "margin_mode": True,
    },
    # V72 (ship 2026-10-22): V64d ExpandedNEG base + V54 PID evidence
    # integrator. Params from Gate2V72 reports/results.json (owner-280 PID
    # acc 88.21%); accuracy arm, streaming per-connection state.
    "gate2v72_v64d_pid": {
        "tau": 0.3,
        "kp": 0.3,
        "ki": 0.01,
        "kd": 0.05,
        "kc": 0.0,
        "margin_mode": False,
    },
}

# V76 deployable threshold-reject layer (Gate2V76 tuned_thresholds.json):
# reject a window when its score crosses tau, else keep the base probs.
# Tuned on the 202-clip class holdout; the keep>=98% arm retains 98.9% of
# command clips (96.7% acc on kept) while rejecting 56.2% of OOS traps.
GATE2_TR_CONFIGS = {
    "gate2v76_v64d_tr": {
        "score": "maxprob",
        "tau": 0.5917618364095688,
        "profile": "keep>=98%",
    },
}


def _gate2_tr_scores(model_name: str, probabilities: list[float]) -> list[float]:
    """V76 threshold-reject layer: NEGATIVE one-hot on reject, raw probs on keep."""
    cfg = GATE2_TR_CONFIGS[model_name]
    p = np.asarray(probabilities, dtype=np.float32)
    n = int(p.shape[0])
    # Only the maxprob arm is tuned for the 19-class V64d base; any other
    # configured arm falls back to it so nothing silently passes through.
    s = float(p.max()) if n else 0.0
    reject = s < float(cfg["tau"])
    scores = np.zeros(n + 1, dtype=np.float32)
    if reject:
        scores[n] = 1.0
    else:
        scores[:n] = p
    return scores.tolist()


_V56_PID_MODULE: Any = None


def _v56_pid_module():
    global _V56_PID_MODULE
    if _V56_PID_MODULE is None:
        pid_path = (
            SHIP_DIR
            / "Gate2V56_ChampionStack_V46_PID_ship_EXPERIMENTAL_20261020"
            / "deploy"
            / "pid_stream_integrator.py"
        )
        spec = importlib.util.spec_from_file_location(
            "gate2_v56_pid_integrator", pid_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load V56 PID integrator: {pid_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _V56_PID_MODULE = module
    return _V56_PID_MODULE


def _gate2_v56_pid_scores(
    model_name: str, state: dict, probabilities: list[float]
) -> list[float]:
    if model_name not in GATE2_PID_CONFIGS:
        return list(probabilities)
    pid = _v56_pid_module()
    prediction, accepted = pid.integrate_step(
        state,
        np.asarray(probabilities, dtype=np.float32),
        **GATE2_PID_CONFIGS[model_name],
    )
    scores = np.zeros(len(probabilities) + 1, dtype=np.float32)
    if accepted and 0 <= int(prediction) < len(probabilities):
        scores[int(prediction)] = 1.0
    else:
        scores[-1] = 1.0
    return scores.tolist()


def _slide_window_features(
    features: np.ndarray, offsets: tuple[int, ...], pad_value: float
) -> np.ndarray:
    """Build time-shifted feature channels using the shipped slide-window contract."""
    x = np.asarray(features, dtype=np.float32)
    if x.ndim != 2:
        raise ValueError("slide-window input must be a 2D frame-by-mel matrix")
    out = np.full(
        (x.shape[0], x.shape[1], len(offsets)), float(pad_value), dtype=np.float32
    )
    is_pad = np.max(np.abs(x - float(pad_value)), axis=1) < 0.02
    end = x.shape[0]
    while end > 0 and is_pad[end - 1]:
        end -= 1
    start = 0
    if x.shape[0] - end >= 5:
        while start < end and is_pad[start]:
            start += 1
    else:
        start, end = 0, x.shape[0]
    speech = x[start:end]
    length = end - start
    for channel, offset in enumerate(offsets):
        if offset == 0:
            out[:, :, channel] = x
            continue
        j0 = max(0, -offset)
        j1 = min(x.shape[0], length - offset)
        if j1 > j0:
            out[j0:j1, :, channel] = speech[offset + j0 : offset + j1]
    return out


def _extract_mel_features(runner, waveform: np.ndarray) -> np.ndarray:
    """Shared V19-style log-mel frontend for the single packages and the V124 ensemble.

    Everything a runner needs is taken from its attributes, so the V124 ensemble runner
    sets the same spec fields and reuses this exact path.
    """
    span = runner.source_frames * runner.hop_length + runner.n_fft
    y = np.asarray(waveform, dtype=np.float32).reshape(-1)[-span:]
    mel = librosa.feature.melspectrogram(
        y=y,
        sr=runner.sample_rate,
        n_fft=runner.n_fft,
        hop_length=runner.hop_length,
        win_length=runner.win_length,
        n_mels=runner.source_mels,
        center=runner.center,
        power=runner.power,
    )
    features = np.log1p(mel).T.astype(np.float32)
    if len(features) < runner.source_frames:
        features = np.pad(
            features,
            ((0, runner.source_frames - len(features)), (0, 0)),
            mode="constant",
        )
    elif len(features) > runner.source_frames:
        start = (len(features) - runner.source_frames) // 2
        features = features[start : start + runner.source_frames]
    features = ((features - runner.mean) / (runner.std + 1e-8)).astype(np.float32)
    if features.shape != (runner.frames, runner.n_mels):
        features = _resize_area(features, runner.frames, runner.n_mels)
    return features


class Gate2V124EnsembleRunner:
    """V124: softmax-average of V96c, V93b, V81 (nine-window) + V20-PhonemeAux (center).

    The package ships its own member weights and the V19 preprocessing spec; the
    frontend and the nine-window slide reuse the single-package machinery. Equal
    member weights (0.25 each); the V20pa head has 19 outputs and enters the average
    with a zero NEG (index 19) contribution.
    """

    NINE_OFFSETS = (-50, -38, -25, -12, 0, 12, 25, 38, 50)

    def __init__(self, name: str):
        pkg_dir = GATE2_PACKAGE_RUNNERS[name][0]
        spec_path = pkg_dir / "preprocessing_spec.json"
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot load V124 spec {spec_path}: {exc}") from exc
        self.mean = float(spec.get("stats_mean", float("nan")))
        self.std = float(spec.get("stats_std", float("nan")))
        if not np.isfinite(self.mean) or not np.isfinite(self.std) or self.std <= 0:
            raise RuntimeError(
                f"V124 package has no valid normalization stats: {spec_path}"
            )
        labels_path = pkg_dir / "labels.json"
        try:
            shipped = json.loads(labels_path.read_text(encoding="utf-8"))["labels"]
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot load V124 labels {labels_path}: {exc}") from exc
        # The package ships the 19 intents; index 19 is NEG by convention. The V20pa
        # member has no NEG output and contributes zero there.
        self.labels = [str(label) for label in shipped] + ["NEG"]
        self.frames = int(spec.get("input_frames", 148))
        self.source_frames = int(
            spec.get("source_input_frames", spec.get("input_frames", self.frames))
        )
        self.n_mels = int(spec.get("n_mels", 60))
        self.source_mels = int(
            spec.get("source_n_mels", spec.get("n_mels", self.n_mels))
        )
        self.sample_rate = int(spec.get("sample_rate", SR))
        self.n_fft = int(spec.get("n_fft", 1024))
        self.hop_length = int(spec.get("hop_length", spec.get("hop", 640)))
        self.win_length = int(spec.get("win_length", spec.get("win", self.n_fft)))
        self.center = bool(spec.get("center", True))
        self.power = float(spec.get("power", 2.0))
        self.pad_value = float(spec.get("pad_value", -self.mean / self.std))
        self.resize_method = str(spec.get("feature_resize", ""))
        member_names = (
            "gate2v96c_float16.tflite",
            "gate2v93b_depth_detail_float16.tflite",
            "gate2v81_timeshift_add_float16.tflite",
        )
        self._nine = [
            _make_interpreter(pkg_dir / "tflite" / name_) for name_ in member_names
        ]
        self._center = _make_interpreter(
            pkg_dir / "tflite" / "gate2v20_phoneme_aux_intent_float16.tflite"
        )
        for interpreter in self._nine:
            out = int(np.prod(interpreter.get_output_details()[0]["shape"]))
            if out != len(self.labels):
                raise RuntimeError(
                    f"V124 nine-window member outputs {out} scores for "
                    f"{len(self.labels)} labels"
                )
        center_out = int(np.prod(self._center.get_output_details()[0]["shape"]))
        if center_out != len(self.labels) - 1:
            raise RuntimeError(
                f"V124 center member outputs {center_out} scores for "
                f"{len(self.labels) - 1} intent labels"
            )

    def predict(self, waveform: np.ndarray) -> list[float]:
        acc: np.ndarray = np.zeros(len(self.labels), dtype=np.float32)
        features = _extract_mel_features(self, waveform)
        slide = _slide_window_features(features, self.NINE_OFFSETS, self.pad_value)
        batch = np.asarray(slide, dtype=np.float32)[None, :, :, :]
        for interpreter in self._nine:
            interpreter.set_tensor(interpreter.get_input_details()[0]["index"], batch)
            interpreter.invoke()
            acc += 0.25 * np.asarray(
                interpreter.get_tensor(interpreter.get_output_details()[0]["index"])[0],
                dtype=np.float32,
            )
        center_batch = np.asarray(features[:, :, None], dtype=np.float32)[None, :, :, :]
        self._center.set_tensor(
            self._center.get_input_details()[0]["index"], center_batch
        )
        self._center.invoke()
        center_probs = np.asarray(
            self._center.get_tensor(self._center.get_output_details()[0]["index"])[0],
            dtype=np.float32,
        )
        acc[: len(center_probs)] += 0.25 * center_probs
        return [float(value) for value in acc]


def _resize_area(
    features: np.ndarray, target_frames: int, target_mels: int
) -> np.ndarray:
    """NumPy area-resize a normalized frame/mel feature matrix."""
    out = np.asarray(features, dtype=np.float32)
    for axis, target in ((0, int(target_frames)), (1, int(target_mels))):
        source = out.shape[axis]
        if source == target:
            continue
        moved = np.moveaxis(out, axis, 0)
        resized = np.zeros((target, *moved.shape[1:]), dtype=np.float32)
        scale = source / target
        for index in range(target):
            left = index * scale
            right = (index + 1) * scale
            first = int(np.floor(left))
            last = int(np.ceil(right))
            for src_index in range(first, min(last, source)):
                weight = max(
                    0.0, min(right, src_index + 1.0) - max(left, float(src_index))
                )
                resized[index] += moved[src_index] * (weight / scale)
        out = np.moveaxis(resized, 0, axis)
    return out.astype(np.float32)


def _inference_interval_s(mode: str, data: dict[str, Any]) -> float:
    requested = data.get("interval_s")
    if (
        isinstance(requested, (int, float))
        and not isinstance(requested, bool)
        and requested in (1, 2, 3, 6, 1.0, 2.0, 3.0, 6.0)
    ):
        return float(requested)
    if mode == "both":
        return 1.0
    if (
        mode == "gate2"
        and isinstance(requested, (int, float))
        and not isinstance(requested, bool)
        and requested == 2
    ):
        return 2.0
    return 1.0


def _make_interpreter(model_path: Path):
    """Create a TFLite Interpreter from the first available backend."""
    candidates = (
        ("ai_edge_litert.interpreter", "Interpreter"),
        ("tensorflow", "lite.Interpreter"),
        ("tflite_runtime.interpreter", "Interpreter"),
    )
    last_error: Exception | None = None
    for mod_name, attr_path in candidates:
        try:
            obj: Any = importlib.import_module(mod_name)
            for part in attr_path.split("."):
                obj = getattr(obj, part)
            interp = obj(model_path=str(model_path))
            interp.allocate_tensors()
            return interp
        except (ImportError, AttributeError, OSError, ValueError) as e:
            last_error = e
    raise ImportError(
        "No TFLite interpreter available (install tflite-runtime or ai-edge-litert): "
        + str(last_error)
    )


def _asset(name: str) -> Path:
    """Resolve a runtime asset from the project root, gate1_web/, or vcm8/."""
    for base in (
        HERE,
        HERE / "gate1_web",
        HERE / "vcm8" / "training",
        HERE / "vcm8" / "training" / "tflite",
        HERE / "vcm8" / "config",
    ):
        p = base / name
        if p.is_file():
            return p
    raise FileNotFoundError(f"asset {name} not found under {HERE}")


class Gate2V2Preproc:
    """Preprocessing from the shipped Gate 2 v2 infer.py contract."""

    def __init__(self):
        config_path = _asset("gate2v2_assets/preprocessing.json")
        try:
            self.config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Failed to load Gate 2 v2 preprocessing config {config_path}: {exc}"
            ) from exc
        self.sample_rate = int(self.config["sample_rate"])
        self.n_fft = int(self.config["n_fft"])
        self.hop_length = int(self.config["hop_length"])
        self.win_length = int(self.config["win_length"])
        self.n_mels = int(self.config["n_mels"])
        self.center = bool(self.config["center"])
        self.target_frames = int(self.config["target_frames"])
        with np.load(_asset("gate2v2_assets/feature_stats.npz")) as stats:
            self.mean = float(stats["mean"])
            self.std = float(stats["std"])

    def extract(
        self, waveform: np.ndarray, sample_rate: int | None = None
    ) -> np.ndarray:
        """Return one normalized (1, frames, mels, 1) input tensor."""
        y = np.asarray(waveform, dtype=np.float32)
        if y.ndim == 2:
            y = y.mean(axis=1)
        if y.ndim != 1 or y.size == 0:
            raise ValueError(f"expected nonempty mono/stereo audio, got {y.shape}")
        source_rate = self.sample_rate if sample_rate is None else int(sample_rate)
        if source_rate != self.sample_rate:
            y = librosa.resample(y, orig_sr=source_rate, target_sr=self.sample_rate)
        mel = librosa.feature.melspectrogram(
            y=y,
            sr=self.sample_rate,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.win_length,
            n_mels=self.n_mels,
            center=self.center,
            power=2.0,
        )
        features = np.log1p(mel).T
        if len(features) < self.target_frames:
            features = np.pad(
                features,
                ((0, self.target_frames - len(features)), (0, 0)),
                mode="constant",
            )
        elif len(features) > self.target_frames:
            start = (len(features) - self.target_frames) // 2
            features = features[start : start + self.target_frames]
        return ((features - self.mean) / (self.std + 1e-8)).astype(np.float32)[
            None, :, :, None
        ]


class Gate2V6KerasRunner:
    """Packaged Gate2V6 Keras source weights via the package infer.py preprocess.

    The shipped gate2v6 TFLite needs the Flex runtime (unavailable here); the
    Keras source is the same weights and is the laptop-testing runner
    (reference implementation: DemoApp/demo_server.py Gate2V6Runner).
    """

    name = "gate2v6_keras"

    def __init__(self, expected_labels: list[str]):
        pkg = GATE2V6_PKG
        if (
            not (pkg / "infer.py").is_file()
            or not (pkg / "model_src" / "best_model.keras").is_file()
        ):
            raise RuntimeError(f"Gate2 v6 package not found: {pkg}")
        if str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        # The package's infer.py is only importable after the sys.path insert,
        # so load it dynamically (same pattern as _make_interpreter).
        gate2v6_infer = importlib.import_module("infer")
        self._infer = gate2v6_infer
        # pi-lens-ignore: Pyright:reportMissingImports
        import tensorflow as tf

        try:
            self.model = tf.keras.models.load_model(  # type: ignore[attr-defined]  # tf.keras is lazy; the linter stub omits it
                pkg / "model_src" / "best_model.keras", compile=False
            )
            raw_labels = json.loads((pkg / "labels.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(
                f"Cannot load Gate2 v6 source model or labels from {pkg}: {exc}"
            ) from exc
        self.labels = list(raw_labels["labels"])
        self.labels_path = pkg / "labels.json"
        # Hard fail at load, same contract as the gate2v2 label check.
        if self.labels != list(expected_labels):
            raise RuntimeError(
                f"Gate 2 v6 label order differs from the current registry: {self.labels_path}"
            )

    def predict(self, waveform: np.ndarray) -> list[float]:
        import soundfile as sf

        window = np.asarray(waveform, dtype=np.float32)[-WIN_SAMPLES:]
        fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=str(HERE))
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            sf.write(str(tmp), window, SR, subtype="PCM_16")
            x = self._infer.preprocess(tmp)
            scores = np.asarray(self.model(x, training=False))[0].astype(float)
        finally:
            tmp.unlink(missing_ok=True)
        return scores.tolist()

    def predict_zeros(self) -> list[float]:
        return self.predict(np.zeros(WIN_SAMPLES, dtype=np.float32))


class Preproc:
    """Log-mel features (numpy-only; verified vs trained pipeline). target=74 or 148."""

    def __init__(self, stats_name: str, target: int):
        self.fb = np.load(_asset("mel_fb.npz"))["mel_fb"]
        st = np.load(_asset(stats_name))
        self.mean = float(st["mean"])
        self.std = float(st["std"])
        self.target = int(target)
        self.win = np.array(
            [0.5 - 0.5 * np.cos(2 * np.pi * i / N_FFT) for i in range(N_FFT)],
            dtype=np.float32,
        )

    def extract(self, buf: np.ndarray) -> np.ndarray:
        pad = N_FFT // 2
        n = buf.shape[0]
        y = np.empty(n + 2 * pad, dtype=np.float64)
        y[pad : pad + n] = buf
        y[:pad] = buf[pad - 1 :: -1]
        y[pad + n :] = buf[n - 2 : n - 2 - pad : -1]
        n_frames = n // HOP + 1
        idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n_frames)[:, None]
        frames = (y[idx] * self.win).astype(np.float32)
        S = np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32) ** 2
        log_S = np.log1p((self.fb @ S.T).astype(np.float32))
        if log_S.shape[1] < self.target:
            log_S = np.pad(log_S, ((0, 0), (0, self.target - log_S.shape[1])))
        else:
            s0 = (log_S.shape[1] - self.target) // 2
            log_S = log_S[:, s0 : s0 + self.target]
        feat = log_S.T
        return ((feat - self.mean) / (self.std + 1e-8))[None, :, :, None].astype(
            np.float32
        )


LABELS_G1 = ["Nova", "Piattos", "Negative"]

# Shipped wake model. Gate1V10 is a sealed-benchmark FAILURE (owner Nova 3/10;
# its README says do NOT deploy) and stays UI-selectable only. Gate1V12 (2026-10-22)
# is the default: on the synthetic wake clips it reads Piattos correctly (V8 read
# the Piattos clip as Nova 0.915) and rejects the command words V8 false-woke on
# (V8 scored "Stop" as Nova 0.943; V12 keeps it Negative 0.815). Its sealed
# benchmark is still unrun - see Notes.md for the numbers and the open item.
DEFAULT_G1_MODEL = "gate1v12_f16"
WAKE = ["Nova", "Piattos"]

# Wake-gate candidates that shipped but have no adapter in this build. Listed so
# the dashboard can show them as unavailable instead of silently hiding them.
GATE1_DISABLED_CANDIDATES = {
    "gate1v8c_f16": "Gate1V8C input is (1,49,40,1): needs the 49x40 wake frontend adapter.",
}


def _wake_candidate(
    probs: list[float], thresholds: dict[str, float], rms: float, floor: float
) -> str | None:
    """Return a wake candidate only above the app's ambient energy floor."""
    if len(probs) < 2 or not np.isfinite(rms) or not np.isfinite(floor) or rms < floor:
        return None
    if probs[0] >= thresholds["Nova"]:
        return LABELS_G1[0]
    if probs[1] >= thresholds["Piattos"]:
        return LABELS_G1[1]
    return None


WAKE_DOMINANT_CONF = 0.7


def _gate2_suppressed(p1: list[float]) -> bool:
    """A window dominated by the wake word itself (Nova/Piattos >= 0.7) must not
    open Gate 2 command windows — the wake audio would otherwise spawn phantom
    command events that fire the wrong action."""
    return len(p1) >= 2 and (p1[0] >= WAKE_DOMINANT_CONF or p1[1] >= WAKE_DOMINANT_CONF)


def _level_rms(win: np.ndarray) -> float:
    """RMS of the most recent second: short wake words are not diluted by the
    older part of the 5.92s window (full-window RMS falsely gated them)."""
    tail = win[-SR:] if win.shape[0] >= SR else win
    return float(np.sqrt(np.mean(tail.astype(np.float64) ** 2)))


def _track_ambient(amb: deque, wrms: float) -> float:
    """Noise-floor tracking from quiet ticks only (minimum-statistics style).
    Sustained audio (speech or injected bursts) must not raise the floor, or
    every later tick — including real speech — gets energy-gated. The first
    tracked tick must not seed the floor either: a loud first tick would
    otherwise gate every later tick of the case (owner-voice run 2026-10-17)."""
    if amb:
        ambient = sorted(amb)[max(0, len(amb) // 10)]
    else:
        ambient = 0.0
    floor = max(0.005, 2.5 * ambient)
    if wrms < floor:
        amb.append(wrms)
    return floor


def _package_labels(pkg_dir: Path, spec_dir: Path | None, tflite_path: Path) -> list[str]:
    """Label list for a package, accepting the shapes the runs actually ship.

    Preference order: the package's own labels.json, then the fallback package's
    (fine-tunes inherit their base head and the output-size check further down
    fails loudly if the order does not match). Two shapes are accepted: a dict
    with a "labels" list, or a bare list. Some packages instead ship a head
    descriptor - V87's is {"num_outputs": 1, "format": "binary head ..."} - which
    is not a label list and must fall through to the fallback package.
    """
    candidates = [pkg_dir / "labels.json"]
    if spec_dir is not None:
        candidates.append(spec_dir / "labels.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        labels = raw.get("labels") if isinstance(raw, dict) else raw
        if (
            isinstance(labels, list)
            and labels
            and all(isinstance(item, str) for item in labels)
        ):
            return [str(item) for item in labels]
    raise RuntimeError(
        "Cannot load Gate2 package labels from "
        + ", ".join(str(path) for path in candidates)
        + ": no usable label list"
    )


class Gate2PackageRunner:
    """TFLite runner for shipped single-window and slide-window Gate2 packages."""

    def __init__(self, name: str):
        pkg_dir, rel_tflite, spec_dir = GATE2_PACKAGE_RUNNERS[name]
        tflite_path = pkg_dir / rel_tflite
        if not tflite_path.is_file():
            raise RuntimeError(f"Gate2 package model missing: {tflite_path}")
        spec_path = pkg_dir / "preprocessing_spec.json"
        if not spec_path.is_file() and spec_dir is not None:
            spec_path = spec_dir / "preprocessing_spec.json"
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Cannot load Gate2 package spec {spec_path}: {exc}"
            ) from exc
        self.spec_data = spec
        stats = spec.get("stats") if isinstance(spec.get("stats"), dict) else {}
        self.mean = float(spec.get("stats_mean", stats.get("mean", float("nan"))))
        self.std = float(spec.get("stats_std", stats.get("std", float("nan"))))
        if not np.isfinite(self.mean) or not np.isfinite(self.std) or self.std <= 0:
            raise RuntimeError(
                f"Gate2 package has no valid normalization stats: {spec_path}"
            )
        self.labels = _package_labels(pkg_dir, spec_dir, tflite_path)
        self.interp = _make_interpreter(tflite_path)
        input_details = self.interp.get_input_details()
        if len(input_details) != 1:
            raise RuntimeError(
                f"Gate2 package expects {len(input_details)} input tensors; adapter supports one: {tflite_path}"
            )
        ind = input_details[0]
        self.in_idx = ind["index"]
        self.in_dtype = ind["dtype"]
        shape = tuple(int(d) for d in ind["shape"])
        if len(shape) != 4:
            raise RuntimeError(
                f"Gate2 package input must be rank 4, got {shape}: {tflite_path}"
            )
        out_details = self.interp.get_output_details()
        if len(out_details) != 1:
            raise RuntimeError(
                f"Gate2 package expects {len(out_details)} output tensors; adapter supports "
                f"one: {tflite_path}"
            )
        out_scores = int(np.prod(out_details[0]["shape"]))
        if out_scores == len(self.labels) + 1:
            # Several intents-only packages ship the 19 intent labels and let the
            # twentieth output carry the reject class - the documented convention
            # ("19 intents + index 19 = NEG"), the same ordering as the V64D base.
            # Appending it keeps the intent order identical to the base package.
            self.labels = [*self.labels, "NEG"]
        if out_scores != len(self.labels):
            # Catches a package registered against the wrong base: without this the mismatched
            # head would silently score near zero instead of failing.
            raise RuntimeError(
                f"Gate2 package outputs {out_scores} scores for {len(self.labels)} labels: "
                f"{tflite_path}"
            )
        self.frames = shape[1]
        self.n_mels = shape[2]
        self.channels = shape[3]
        self.sample_rate = int(spec.get("sample_rate", SR))
        self.n_fft = int(spec.get("n_fft", 1024))
        self.hop_length = int(spec.get("hop_length", spec.get("hop", 640)))
        self.win_length = int(spec.get("win_length", spec.get("win", self.n_fft)))
        self.center = bool(spec.get("center", True))
        self.power = float(spec.get("power", 2.0))
        self.source_frames = int(
            spec.get(
                "source_input_frames",
                spec.get(
                    "input_frames",
                    spec.get("model_input_frames", spec.get("frames", self.frames)),
                ),
            )
        )
        self.source_mels = int(
            spec.get("source_n_mels", spec.get("n_mels", self.n_mels))
        )
        self.pad_value = float(spec.get("pad_value", -self.mean / self.std))
        self.resize_method = str(spec.get("feature_resize", ""))
        self.channel_offsets = {
            1: (),
            5: (-50, -25, 0, 25, 50),
            9: (-50, -38, -25, -12, 0, 12, 25, 38, 50),
            17: (
                -100,
                -88,
                -75,
                -62,
                -50,
                -38,
                -25,
                -12,
                0,
                12,
                25,
                38,
                50,
                62,
                75,
                88,
                100,
            ),
        }.get(self.channels)
        if self.channel_offsets is None:
            raise RuntimeError(
                f"No adapter for {self.channels}-channel Gate2 frontend: {tflite_path}"
            )

    def _extract_features(self, waveform: np.ndarray) -> np.ndarray:
        return _extract_mel_features(self, waveform)

    def _infer_features(self, features: np.ndarray) -> list[float]:
        x = np.asarray(features, dtype=self.in_dtype)[None, :, :, :]
        self.interp.set_tensor(self.in_idx, x)
        self.interp.invoke()
        return [
            float(v)
            for v in self.interp.get_tensor(
                self.interp.get_output_details()[0]["index"]
            )[0]
        ]

    def predict(self, waveform: np.ndarray) -> list[float]:
        features = self._extract_features(waveform)
        if self.channels == 1:
            model_features = features[:, :, None]
        else:
            offsets = self.channel_offsets
            if offsets is None:
                raise RuntimeError(
                    f"No slide offsets for {self.channels}-channel Gate2 model"
                )
            model_features = _slide_window_features(features, offsets, self.pad_value)
        return self._infer_features(model_features)

    def predict_pid_clip(self, waveform: np.ndarray, model_name: str) -> list[float]:
        """Run the V56 per-slide PID recipe for a single offline utterance."""
        if self.channels != 9:
            raise RuntimeError("V56 PID adapter requires nine sliding-window channels")
        features = self._extract_features(waveform)
        offsets = self.channel_offsets
        if offsets is None:
            raise RuntimeError("V56 PID adapter has no slide offsets")
        slide_features = _slide_window_features(features, offsets, self.pad_value)
        pid = _v56_pid_module()
        state = pid.new_state()
        config = GATE2_PID_CONFIGS[model_name]
        prediction = len(self.labels)
        accepted = False
        for channel in range(self.channels):
            one_hot = np.full(
                (self.frames, self.n_mels, self.channels),
                self.pad_value,
                dtype=np.float32,
            )
            one_hot[:, :, channel] = slide_features[:, :, channel]
            probs = self._infer_features(one_hot)
            prediction, accepted = pid.integrate_step(
                state, np.asarray(probs, dtype=np.float32), **config
            )
        scores = np.zeros(len(self.labels) + 1, dtype=np.float32)
        scores[
            int(prediction)
            if accepted and 0 <= int(prediction) < len(self.labels)
            else -1
        ] = 1.0
        return scores.tolist()


G3TO5P_DIR = SHIP_DIR / "Gate3to5P_OwnerFinetuned_ship_EXPERIMENTAL_20261017"
G3TO5P_MAP = {
    "TIMER": "gate3a_p",
    "ALARM": "gate3b_p",
    "TEMPERATURE": "gate3c_p",
    "BRIGHTNESS": "gate3d_p",
    "COLOR": "gate4_p",
    "CREATE_REMINDER": "gate5_p",
}


class Gate3to5PPack:
    """Owner-fine-tuned CRNN specialists (laptop/TensorFlow only; tflite/ ships empty).

    Predicts the routed slot value on the trailing 8-second window when the
    action fires; scores are training-fit per the package README, not accuracy.
    """

    def __init__(self):
        import tensorflow as tf  # lazy: laptop-only pack

        try:
            self.models = {
                intent: tf.keras.models.load_model(  # type: ignore[attr-defined]  # tf.keras is lazy; the linter stub omits it
                    str(G3TO5P_DIR / "models" / f"{fname}.keras"), compile=False
                )
                for intent, fname in G3TO5P_MAP.items()
            }
            self.slots = json.loads(
                (G3TO5P_DIR / "slot_values.json").read_text(encoding="utf-8")
            )
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Cannot load Gate3-5P owner-finetuned pack from {G3TO5P_DIR}: {exc}"
            ) from exc

    def predict(self, intent: str, waveform: np.ndarray) -> tuple[str, float]:
        y = np.asarray(waveform, dtype=np.float32).reshape(-1)
        mel = librosa.feature.melspectrogram(
            y=y,
            sr=SR,
            n_fft=1024,
            hop_length=640,
            win_length=1024,
            n_mels=60,
            center=True,
            power=2.0,
        )
        x = np.log1p(mel).T
        if len(x) < 148:
            x = np.pad(x, ((0, 148 - len(x)), (0, 0)), mode="constant")
        else:
            start = (len(x) - 148) // 2
            x = x[start : start + 148]
        probs = self.models[intent].predict(
            x[None, :, :, None].astype(np.float32), verbose=0
        )[0]
        return self.slots[intent][int(np.argmax(probs))], float(np.max(probs))


G3TO5P_PACK: Any = None


def _g3to5p_pack() -> Any:
    global G3TO5P_PACK
    if G3TO5P_PACK is None:
        G3TO5P_PACK = Gate3to5PPack()
    return G3TO5P_PACK


class PipelineActivationWindows:
    """Independent wake/intent latches; Action Gate fires once per G2 event."""

    G1_SECONDS = 12.0
    G2_SECONDS = 8.0
    # Owner-voice E2E (2026-10-17): the 5.92s window scores wake and command
    # in the same ticks, so the command latch can precede the 2-of-3 wake
    # activation by 1-3 evaluation ticks. The grace must cover that in-pair
    # lag while still blocking cross-pair staleness.
    G2_WAKE_GRACE = 6.0

    def __init__(self):
        self.g1_until = 0.0
        self.g1_label: str | None = None
        self.g1_conf = 0.0
        self.g2_until = 0.0
        self.g2_intent: str | None = None
        self.g2_conf = 0.0
        self.g2_event_id = 0
        self._consumed_event_id = 0
        self._last_gate2_intent: str | None = None
        self.g1_activated_at = 0.0
        self.g2_confirmed_at = 0.0

    def activate_gate1(self, now: float, label: str, confidence: float) -> None:
        self.g1_until = max(self.g1_until, now + self.G1_SECONDS)
        self.g1_label = label
        self.g1_conf = float(confidence)
        self.g1_activated_at = now
        # A fresh wake word re-arms the intent memory: the operator's next
        # command (even a repeat of the last one) fires without needing an
        # intervening NEGATIVE tick. Owner-voice E2E 2026-10-22 confirmed the
        # repeat-suppressor swallowed "stop stop" sequences with no NEGATIVE
        # tick in between when speech was continuous.
        self._last_gate2_intent = None

    def observe_gate2(
        self, intent: str | None, confidence: float, threshold: float, now: float
    ) -> bool:
        """Latch a command window on a single threshold-qualified tick.

        NEGATIVE is the idle/reject prediction: it must never arm a pending
        action, or a later wake word would fire the phantom pre-wake reject.
        A repeat of the live intent inside its open window is the same
        utterance being re-scored, not a new event. Phantom prevention for
        stale commands lives in action_ready's wake-ordering check.
        """
        if (
            intent is None
            or intent in ("NEGATIVE", "NEG")
            or not np.isfinite(confidence)
            or confidence < threshold
        ):
            self._last_gate2_intent = None
            return False
        # One command utterance fires once: a new event for the same intent
        # requires an intervening reset tick, not a mere 8s window expiry while
        # the same audio keeps scoring (owner-voice tick trace 2026-10-17
        # fired ALARM twice per command).
        if intent == self._last_gate2_intent:
            return False
        self._last_gate2_intent = intent
        self.g2_until = now + self.G2_SECONDS
        self.g2_intent = intent
        self.g2_conf = float(confidence)
        self.g2_event_id += 1
        self.g2_confirmed_at = now
        return True

    def gate1_active(self, now: float) -> bool:
        return now < self.g1_until

    def gate2_active(self, now: float) -> bool:
        return now < self.g2_until

    def action_ready(self, now: float) -> bool:
        """Fire only while the confirmed command is ordered after the wake word.

        Overlapping latches alone fired phantom actions when a command
        confirmed during one wake window survived into the next wake word
        (owner-voice run 2026-10-17): require the G2 confirmation to be at
        least as new as the current G1 activation.
        """
        return (
            self.gate1_active(now)
            and self.gate2_active(now)
            and self.g2_event_id > self._consumed_event_id
            and self.g2_confirmed_at >= self.g1_activated_at - self.G2_WAKE_GRACE
        )

    def snapshot(self, now: float) -> dict[str, dict[str, object]]:
        g1_active = self.gate1_active(now)
        g2_active = self.gate2_active(now)
        overlap = g1_active and g2_active
        return {
            "g1": {
                "active": g1_active,
                "remaining_s": round(max(0.0, self.g1_until - now), 2),
                "activation_label": self.g1_label if g1_active else None,
                "activation_conf": self.g1_conf if g1_active else 0.0,
            },
            "g2": {
                "active": g2_active,
                "remaining_s": round(max(0.0, self.g2_until - now), 2),
                "activation_intent": self.g2_intent if g2_active else None,
                "activation_conf": self.g2_conf if g2_active else 0.0,
            },
            "action_gate": {
                "active": overlap,
                "triggered": False,
                "pending": overlap and self.g2_event_id > self._consumed_event_id,
                "intent": self.g2_intent if overlap else None,
                "event_id": self.g2_event_id if overlap else 0,
            },
        }

    def consume_action(self) -> None:
        self._consumed_event_id = self.g2_event_id

    def manual_stop(self) -> None:
        """Cancel the pending event and clear active latches; audio capture keeps running."""
        self.consume_action()
        self.g1_until = 0.0
        self.g1_label = None
        self.g1_conf = 0.0
        self.g1_activated_at = 0.0
        self.g2_until = 0.0
        self.g2_intent = None
        self.g2_conf = 0.0
        self.g2_confirmed_at = 0.0
        self._last_gate2_intent = None

    def reset(self) -> None:
        self.__init__()


ROUTING = {
    "TIMER": "gateN",
    "ALARM": "gateN",
    "TEMPERATURE": "gateN",
    "BRIGHTNESS": "gateN",
    "COLOR": "gate4",
    "CREATE_REMINDER": "gate5",
}


class Gates:
    """All TFLite interpreters + preprocessing + labels."""

    def __init__(self):
        registry_path = _asset("model_registry.json")
        try:
            self.registry = json.loads(registry_path.read_text(encoding="utf-8"))[
                "models"
            ]
        except (OSError, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"Failed to load model registry {registry_path}: {e}"
            ) from e
        self.pre148 = Preproc("feature_stats_148.npz", TARGET_148)
        self.pre74 = Preproc("feature_stats.npz", TARGET_74)
        self.pre_gate2v2 = Gate2V2Preproc()
        # Selectable Gate 2 models: v56_v54 (champion accuracy winner) is the
        # default; the other shipped packages and the Gate2V6 Keras source load lazily.
        self.gate2_runner = "gate2v56_v54"
        self._gate2_extra: dict[str, Any] = {}
        try:
            self._gate2_extra["gate2v56_v54"] = Gate2PackageRunner("gate2v56_v54")
        except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
            print(
                "[gates] gate2v56_v54 default unavailable, falling back to gate2v21p: "
                + str(exc),
                flush=True,
            )
            self.gate2_runner = "gate2v21p"
            try:
                self._gate2_extra["gate2v21p"] = Gate2PackageRunner("gate2v21p")
            except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc2:
                print(
                    "[gates] gate2v21p fallback unavailable, falling back to gate2v2: "
                    + str(exc2),
                    flush=True,
                )
                self.gate2_runner = "gate2v2"
        self.gates = {}
        specs = {
            "gate1v5": "gate1v5_float32.tflite",
            "gate2": "gate2v2_float16.tflite",
            "gateN": "gateN_v1_float16.tflite",
            "gate4": "gate4_float16.tflite",
            "gate5": "gate5_float16.tflite",
        }
        self.labels = {}
        for name, fname in specs.items():
            path = _asset(fname)
            interp = _make_interpreter(path)
            ind = interp.get_input_details()[0]
            outd = interp.get_output_details()[0]
            reg_key = "gate1" if name.startswith("gate1v") else name
            if name == "gate2":
                labels_path = _asset("gate2v2_assets/labels.json")
                try:
                    gate2_labels = json.loads(labels_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"Failed to load Gate 2 v2 labels {labels_path}: {exc}"
                    ) from exc
                if gate2_labels != self.registry["gate2"]["labels"]:
                    raise RuntimeError(
                        f"Gate 2 v2 label order differs from the current registry: {labels_path}"
                    )
                self.labels[name] = list(gate2_labels)
            else:
                self.labels[name] = list(self.registry[reg_key]["labels"])
            self.gates[name] = {
                "interp": interp,
                "in_idx": ind["index"],
                "in_dtype": ind["dtype"],
                "in_shape": tuple(int(d) for d in ind["shape"]),
                "out_idx": outd["index"],
            }
        # gate1v5 (exploratory bare-only 2-class: nova/piattos, NO negative)
        # ships its own frozen normalization stats.
        self.prev5 = Preproc("feature_stats_v5_148.npz", TARGET_148)
        self.gates["gate1v5"]["pre"] = self.prev5
        # Gate1V8 ships its own train-only normalization statistics.
        self.prev8 = Preproc("feature_stats_v8_148.npz", TARGET_148)
        # Additional gate1 variants (version + precision) for the UI model chooser.
        variants = {
            "gate1v2_f32": ("gate1v2_float32.tflite", "feature_stats_148.npz"),
            "gate1v2_f16": ("gate1v2_float16.tflite", "feature_stats_148.npz"),
            "gate1v3_f32": ("gate1v3_float32.tflite", "feature_stats_v3_148.npz"),
            "gate1v3_f16": ("gate1v3_float16.tflite", "feature_stats_v3_148.npz"),
            "gate1v4_f32": ("gate1v4_float32.tflite", "feature_stats_v4_148.npz"),
            "gate1v4_f16": ("gate1v4_float16.tflite", "feature_stats_v4_148.npz"),
            "gate1v5_f32": ("gate1v5_float32.tflite", "feature_stats_v5_148.npz"),
            "gate1v5_f16": ("gate1v5_float16.tflite", "feature_stats_v5_148.npz"),
            "gate1v8_f32": ("gate1v8_float32.tflite", "feature_stats_v8_148.npz"),
            "gate1v8_f16": ("gate1v8_float16.tflite", "feature_stats_v8_148.npz"),
        }
        self.g1_variants = {}
        for key, (fname, stats_name) in variants.items():
            path = _asset(fname)
            if not path.is_file():
                continue
            interp = _make_interpreter(path)
            ind = interp.get_input_details()[0]
            outd = interp.get_output_details()[0]
            ver = key[5:7]  # "v2".."v5" or "v8"
            if ver == "v5":
                labels = ["Nova", "Piattos"]
                pre = self.prev5
            elif ver == "v8":
                labels = ["Nova", "Piattos", "Negative"]
                pre = self.prev8
            else:
                labels = ["Nova", "Piattos", "Negative"]
                pre = self.pre148 if ver == "v2" else Preproc(stats_name, TARGET_148)
            self.g1_variants[key] = {
                "interp": interp,
                "in_idx": ind["index"],
                "in_dtype": ind["dtype"],
                "in_shape": tuple(int(d) for d in ind["shape"]),
                "out_idx": outd["index"],
                "labels": labels,
                "pre": pre,
                "two_class": ver == "v5",
            }
        # Gate1V10 (2026-10-17 upload) ships its own stats; labels are lowercase
        # in the package but the output order matches the canonical Nova/Piattos/Negative.
        for key, fname in (
            ("gate1v10_f16", "gate1v10_float16.tflite"),
            ("gate1v10_dr", "gate1v10_dynamic_range.tflite"),
        ):
            v10_path = _asset(fname)
            if not v10_path.is_file():
                continue
            try:
                v10_interp = _make_interpreter(v10_path)
            except (ImportError, RuntimeError, OSError, ValueError) as v10_exc:
                # Newer-TF exports (op version > Pi tflite-runtime 2.14) must not
                # crash the dashboard; the variant is simply not offered there.
                print(
                    "[gates] " + key + " unavailable on this runtime: " + str(v10_exc),
                    flush=True,
                )
                continue
            v10_ind = v10_interp.get_input_details()[0]
            v10_outd = v10_interp.get_output_details()[0]
            v10_shape = tuple(int(d) for d in v10_ind["shape"])
            v10_frames = int(v10_shape[1]) if len(v10_shape) == 4 else TARGET_148
            self.g1_variants[key] = {
                "interp": v10_interp,
                "in_idx": v10_ind["index"],
                "in_dtype": v10_ind["dtype"],
                "in_shape": v10_shape,
                "out_idx": v10_outd["index"],
                "labels": ["Nova", "Piattos", "Negative"],
                "pre": Preproc("feature_stats_v10.npz", v10_frames),
                "two_class": False,
            }
        # Gate1V12 (2026-10-20 upload) keeps the (1,148,60,1) contract, so it rides
        # the v8 train-only stats. The package ships no feature_stats file; that
        # fallback is measured rather than assumed - under all five shipped stat
        # candidates the two synthetic wake clips score >0.99 for their persona and
        # three command clips stay Negative (see Notes.md).
        v12_path = _asset("gate1v12_float16.tflite")
        if v12_path.is_file():
            try:
                v12_interp = _make_interpreter(v12_path)
            except (ImportError, RuntimeError, OSError, ValueError) as v12_exc:
                print(
                    "[gates] gate1v12_f16 unavailable on this runtime: " + str(v12_exc),
                    flush=True,
                )
            else:
                v12_ind = v12_interp.get_input_details()[0]
                v12_outd = v12_interp.get_output_details()[0]
                v12_shape = tuple(int(d) for d in v12_ind["shape"])
                if v12_shape == (1, TARGET_148, N_MELS, 1):
                    self.g1_variants["gate1v12_f16"] = {
                        "interp": v12_interp,
                        "in_idx": v12_ind["index"],
                        "in_dtype": v12_ind["dtype"],
                        "in_shape": v12_shape,
                        "out_idx": v12_outd["index"],
                        "labels": ["Nova", "Piattos", "Negative"],
                        "pre": self.prev8,
                        "two_class": False,
                    }
                else:
                    print(
                        "[gates] gate1v12_f16 skipped: unexpected input "
                        + str(v12_shape),
                        flush=True,
                    )
        for g in self.g1_variants.values():
            dummy = np.zeros(g["in_shape"], dtype=np.float32)
            g["interp"].set_tensor(g["in_idx"], dummy)
            g["interp"].invoke()
        self.gates["gate2"]["pre"] = self.pre_gate2v2
        for n in ("gateN", "gate4", "gate5"):
            self.gates[n]["pre"] = self.pre74
        # Separate locks keep shared TFLite interpreters safe when the parallel test page
        # runs each branch on a worker thread (and when multiple browser clients connect).
        self._infer_locks = {name: threading.RLock() for name in self.gates}
        self._g1_locks = {name: threading.RLock() for name in self.g1_variants}
        self._gate2_lock = threading.RLock()
        self.warm()

    def infer_g1_variant(self, key: str, waveform: np.ndarray):
        g = self.g1_variants[key]
        with self._g1_locks[key]:
            feats = g["pre"].extract(waveform).astype(g["in_dtype"])
            g["interp"].set_tensor(g["in_idx"], feats)
            g["interp"].invoke()
            probs = [float(v) for v in g["interp"].get_tensor(g["out_idx"])[0]]
        return probs, g["labels"], g["two_class"]

    def gate2_active_model(self) -> str:
        return self.gate2_runner

    def gate2_labels(self) -> list[str]:
        extra = self._gate2_extra.get(self.gate2_runner)
        if extra is not None:
            labels = list(extra.labels)
            if (
                self.gate2_runner in GATE2_PID_CONFIGS
                or self.gate2_runner in GATE2_TR_CONFIGS
            ):
                return labels + ["NEGATIVE"]
            return labels
        return self.labels["gate2"]

    def infer_gate2(
        self, waveform: np.ndarray, pid_state: dict | None = None
    ) -> list[float]:
        with self._gate2_lock:
            extra = self._gate2_extra.get(self.gate2_runner)
            if extra is not None:
                if self.gate2_runner in GATE2_PID_CONFIGS:
                    if pid_state is None:
                        return extra.predict_pid_clip(waveform, self.gate2_runner)
                    raw = extra.predict(waveform)
                    return _gate2_v56_pid_scores(self.gate2_runner, pid_state, raw)
                if self.gate2_runner in GATE2_TR_CONFIGS:
                    return _gate2_tr_scores(self.gate2_runner, extra.predict(waveform))
                return extra.predict(waveform)
            return self.infer("gate2", waveform)

    def set_gate2_model(self, name: str) -> str:
        """Switch among the default, Keras, and compatible shipped TFLite Gate 2 models."""
        if (
            name not in ("gate2v2", "gate2v6_keras")
            and name not in GATE2_PACKAGE_RUNNERS
        ):
            raise ValueError("unknown gate2 model: " + name)
        with self._gate2_lock:
            if name == "gate2v6_keras" and "gate2v6_keras" not in self._gate2_extra:
                # Gate2V6KerasRunner hard-fails at load if the packaged label order
                # differs from the registry gate2 labels.
                self._gate2_extra["gate2v6_keras"] = Gate2V6KerasRunner(
                    self.registry["gate2"]["labels"]
                )
            if name in GATE2_PACKAGE_RUNNERS and name not in self._gate2_extra:
                if name == "gate2v124_ensemble4way":
                    self._gate2_extra[name] = Gate2V124EnsembleRunner(name)
                else:
                    self._gate2_extra[name] = Gate2PackageRunner(name)
                # Gate2V6KerasRunner hard-fails at load if the packaged label order
                # differs from the registry gate2 labels.
                self._gate2_extra["gate2v6_keras"] = Gate2V6KerasRunner(
                    self.registry["gate2"]["labels"]
                )
            self.gate2_runner = name
        return name

    def score_gate2_model(
        self, model: str, waveform: np.ndarray, pid_state: dict | None = None
    ) -> list[float]:
        """Score one EXPLICIT Gate 2 model without disturbing the live selection.

        The recording lab replays a saved take through every shipped model while
        the dashboard keeps its own runner, so this mirrors infer_gate2() but
        takes the model as an argument and loads its package on demand.
        """
        with self._gate2_lock:
            if model in GATE2_PACKAGE_RUNNERS and model not in self._gate2_extra:
                self._gate2_extra[model] = Gate2PackageRunner(model)
            extra = self._gate2_extra.get(model)
            if extra is not None:
                if model in GATE2_PID_CONFIGS:
                    if pid_state is None:
                        return extra.predict_pid_clip(waveform, model)
                    return _gate2_v56_pid_scores(
                        model, pid_state, extra.predict(waveform)
                    )
                if model in GATE2_TR_CONFIGS:
                    return _gate2_tr_scores(model, extra.predict(waveform))
                return extra.predict(waveform)
            if model != self.gate2_runner:
                raise ValueError("model is not loaded for explicit scoring: " + model)
            return self.infer("gate2", waveform)

    def gate2_labels_for(self, model: str) -> list[str]:
        """Output labels of one explicit model (PID builds append NEGATIVE)."""
        extra = self._gate2_extra.get(model)
        if extra is not None:
            labels = [str(label) for label in extra.labels]
            return (
                labels + ["NEGATIVE"]
                if model in GATE2_PID_CONFIGS or model in GATE2_TR_CONFIGS
                else labels
            )
        return [str(label) for label in self.labels["gate2"]]

    def warm(self) -> None:
        for g in self.gates.values():
            dummy = np.zeros(g["in_shape"], dtype=np.float32)
            g["interp"].set_tensor(g["in_idx"], dummy)
            g["interp"].invoke()

    def infer(self, name: str, waveform: np.ndarray) -> list[float]:
        g = self.gates[name]
        with self._infer_locks[name]:
            feats = g["pre"].extract(waveform).astype(g["in_dtype"])
            g["interp"].set_tensor(g["in_idx"], feats)
            g["interp"].invoke()
            return [float(v) for v in g["interp"].get_tensor(g["out_idx"])[0]]

    def infer_parallel(self, waveform: np.ndarray) -> dict[str, Any]:
        """Run Gate2 + numeric/color/reminder specialists concurrently on one window."""
        tasks = {
            "gate2": lambda: self.infer_gate2(waveform),
            "gateN": lambda: self.infer("gateN", waveform),
            "gate4": lambda: self.infer("gate4", waveform),
            "gate5": lambda: self.infer("gate5", waveform),
        }
        parallel = importlib.import_module("parallel_pipeline")
        raw = parallel.run_in_parallel(tasks)

        def summarize(
            name: str, scores: list[float], labels: list[str]
        ) -> dict[str, Any]:
            if len(scores) != len(labels) or not scores:
                raise RuntimeError(
                    f"{name} returned {len(scores)} scores for {len(labels)} labels"
                )
            top_index = int(np.argmax(scores))
            return {
                "labels": labels,
                "probs": scores,
                "top": labels[top_index],
                "conf": float(scores[top_index]),
            }

        gate2 = summarize("gate2", raw["gate2"], self.gate2_labels())
        specialists = {
            name: summarize(name, raw[name], self.labels[name])
            for name in ("gateN", "gate4", "gate5")
        }
        return {
            "gate2": gate2,
            "specialists": specialists,
            "model": self.gate2_active_model(),
        }


# Noise canceller DSP lives in nc_dsp.py so the live pipeline and the
# recording-lab replay run byte-identical preprocessing.
_nc_noise_update = nc_dsp._nc_noise_update
_nc_apply = nc_dsp._nc_apply


def _g2_candidate_intent(p2, labels, g2thr, default_thr):
    """Top Gate-2 intent with NEGATIVE-mask bypass.

    NEGATIVE is the reject class: it must never latch by itself, but it must
    not mask a real command either. If NEGATIVE tops the window, the best
    non-NEGATIVE intent is promoted whenever it meets its own per-class
    threshold, so one real command among negative-dominated ticks still acts.
    """
    p2 = np.asarray(p2, dtype=float)
    top_i = int(np.argmax(p2))
    if top_i >= len(labels):
        # PID / threshold-reject layers append one extra reject score; a win there
        # is a rejection, never a command index into the label list.
        return "NEGATIVE", float(p2[top_i])
    intent = labels[top_i]
    conf = float(p2[top_i])
    if intent in ("NEGATIVE", "NEG"):
        masked = p2.copy()
        masked[top_i] = -np.inf
        j = int(np.argmax(masked))
        cand = labels[j]
        if cand not in ("NEGATIVE", "NEG") and float(p2[j]) >= float(
            g2thr.get(cand, default_thr)
        ):
            return cand, float(p2[j])
    return intent, conf


_ROOM_QUEUES: set = set()


def _publish_room(payload: dict) -> None:
    """Fan the latest pipe payload out to any open room-simulation viewers."""
    if not _ROOM_QUEUES:
        return
    for q in tuple(_ROOM_QUEUES):
        try:
            q.put_nowait(payload)
        except Exception:
            _ROOM_QUEUES.discard(q)


async def ws_room_handler(request: web.Request) -> web.WebSocketResponse:
    """Read-only room feed: forwards live pipe payloads; runs no models itself."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    q: asyncio.Queue = asyncio.Queue()
    _ROOM_QUEUES.add(q)
    try:
        await ws.send_json({"type": "room", "status": "linked"})
        while not ws.closed:
            payload = await q.get()
            await ws.send_json(payload)
    finally:
        _ROOM_QUEUES.discard(q)
    return ws


async def room_sim_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(_asset("room_sim.html"))


def _append_ws_received(line: str) -> None:
    """Append one received-samples line to ws_received.log (blocking I/O; run via to_thread)."""
    with (HERE / "ws_received.log").open("a", encoding="utf-8") as lf:
        lf.write(line + "\n")


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    gates: Gates = request.app["gates"]
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    conn_id = format(id(ws) & 0xFFFFFF, "06x")
    stream_acc = np.zeros(0, dtype=np.float32)
    # Rolling capture of everything the mic streams (last CAPTURE_SECONDS), so
    # the dashboard can snapshot "the past 30 seconds" into the recording lab.
    capture_chunks: list[np.ndarray] = []
    capture_samples = 0
    mode = "gate1"
    arch = 0  # 0 = v1 all gates run, 1 = v2 Gate 1 first, 2 = v3 Gate 1 first + intent vote
    tick_interval = 1.0
    tick_interval_changed = asyncio.Event()
    g1_model = DEFAULT_G1_MODEL
    if g1_model not in gates.g1_variants:
        # Runtimes missing a variant fall back to any available shipped v8/v5 build.
        for fallback in ("gate1v8_f32", "gate1v8_f16", "gate1v5_f32"):
            if fallback in gates.g1_variants:
                g1_model = fallback
                break
    thr = {"Nova": 0.5, "Piattos": 0.5, "gate2MinConf": 0.5, "g2thr": {}}
    tick_n = 0
    skipped_ticks = 0
    skip_ticks_enabled = False
    drift_s = 0.0
    skip_log = deque(maxlen=12)  # wall-clock record of overrunning evaluations
    received = 0
    pframes = importlib.import_module("pipeline_frames")
    frame_pending: list[np.ndarray] = []
    frame_mem: deque = deque(maxlen=pframes.FRAME_MEMORY_SECONDS)
    mem_max = pframes.FRAME_MEMORY_SECONDS
    guard = {
        "amb": deque(maxlen=30),
        "recent": deque(maxlen=3),
        "cooldown_until": 0.0,
        "last_wake_event": None,
        "calib_end": 0.0,
        "calib_max": 0.0,
        "v3_intent": None,
        "v3_streak": 0,
    }
    activations = PipelineActivationWindows()
    nc = {"enabled": False, "profile": None}
    pid_runtime: dict[str, Any] = {"model": None, "state": None}

    def reset_gate2_pid() -> None:
        pid_runtime["model"] = None
        pid_runtime["state"] = None

    def infer_gate2_for_connection(waveform: np.ndarray) -> list[float]:
        model_name = gates.gate2_active_model()
        if model_name not in GATE2_PID_CONFIGS:
            reset_gate2_pid()
            return gates.infer_gate2(waveform)
        if pid_runtime["model"] != model_name or pid_runtime["state"] is None:
            pid_runtime["model"] = model_name
            pid_runtime["state"] = _v56_pid_module().new_state()
        return gates.infer_gate2(waveform, pid_state=pid_runtime["state"])

    def now() -> str:
        return datetime.now(UTC).isoformat()

    def attach_action_result(
        payload: dict, waveform: np.ndarray, monotonic_now: float
    ) -> bool:
        if not activations.action_ready(monotonic_now):
            return False
        intent = activations.g2_intent
        if intent is None:
            return False
        payload["action_gate"].update(
            {
                "active": True,
                "triggered": True,
                "pending": False,
                "intent": intent,
                "event_id": activations.g2_event_id,
            }
        )
        payload["action_gate"]["light_on"] = (
            True  # LIGHT FIRST: on before any specialist runs
        )
        payload["g2"].update(
            {
                "intent": intent,
                "conf": activations.g2_conf,
                "activation_intent": intent,
                "activation_conf": activations.g2_conf,
            }
        )
        # Pseudo-code contract: when the action fires, test Gate 3, 4 AND 5 on
        # the same trailing 8-second audio window (model preprocessing crops to
        # its trained input); the routed specialist decides the value. The light
        # is already on (LIGHT FIRST above).
        routed = ROUTING.get(intent)
        pack = None
        try:
            pack = _g3to5p_pack()
        except (ImportError, OSError, RuntimeError, ValueError):
            pack = None
        if pack is not None and routed in G3TO5P_MAP:
            # Gate3-5P default path: routed owner-fine-tuned specialist on the
            # trailing 8-second window (TensorFlow available on this host).
            try:
                pack_label, pack_conf = pack.predict(routed, waveform)
                payload["specialists"] = {
                    routed: {
                        "gate": "gate3to5p",
                        "label": pack_label,
                        "conf": pack_conf,
                    }
                }
                payload["spec"] = {
                    "gate": "gate3to5p",
                    "label": pack_label,
                    "conf": pack_conf,
                }
                payload["final"] = pack_label
                payload["g3to5p"] = True
            except (RuntimeError, ValueError, KeyError):
                payload["g3to5p"] = False
        if payload.get("g3to5p") is not True:
            # Fallback: legacy TFLite trio on the same window.
            payload["g3to5p"] = False
            parallel = importlib.import_module("parallel_pipeline")
            tasks = {
                name: (lambda n=name: gates.infer(n, waveform))
                for name in ("gateN", "gate4", "gate5")
            }
            results = parallel.run_in_parallel(tasks)
            specialists = {}
            for name, scores in results.items():
                idx = int(np.argmax(scores))
                specialists[name] = {
                    "gate": name,
                    "label": gates.labels[name][idx],
                    "conf": scores[idx],
                }
            payload["specialists"] = specialists
            if routed and routed in specialists:
                payload["spec"] = specialists[routed]
                payload["final"] = payload["spec"]["label"]
            else:
                payload["final"] = intent
        # Action voice feedback: play the shipped assistant response for the
        # triggered intent in the latched wake profile (the helper falls back to
        # the other persona, then to variation 2, e.g. volume_up ships only _2).
        clip = assistant_clip(activations.g1_label, intent)
        if clip is not None:
            payload["assistant_response"] = {
                "intent": intent,
                "room_active": bool(_ROOM_QUEUES),
                **clip,
            }
        payload["new_event"] = True
        activations.consume_action()
        reset_gate2_pid()
        return True

    async def ticker() -> None:
        nonlocal tick_n, skipped_ticks, skip_ticks_enabled, drift_s
        try:
            while not ws.closed:
                tick_interval_changed.clear()
                tick_elapsed = False
                try:
                    await asyncio.wait_for(
                        tick_interval_changed.wait(), timeout=tick_interval
                    )
                except TimeoutError:
                    tick_elapsed = True  # expected tick deadline: proceed with scoring
                if not tick_elapsed:
                    continue
                tick_start_time = time.monotonic()
                tick_n += 1
                if stream_acc.shape[0] < WIN_SAMPLES:
                    await ws.send_json(
                        {
                            "type": "status",
                            "text": "filling first window... ("
                            + str(stream_acc.shape[0])
                            + "/"
                            + str(WIN_SAMPLES)
                            + ")",
                        }
                    )
                    continue
                ts = now()
                if mode == "gate1":
                    # Keep inferring every tick for probability display; the energy floor
                    # suppresses wake events because Gate1V8 Negative is speech-only.
                    win = stream_acc[-WIN_SAMPLES:]
                    wrms = _level_rms(win)
                    floor = _track_ambient(guard["amb"], wrms)
                    probs, g1_labels, _ = gates.infer_g1_variant(g1_model, win)
                    wake = _wake_candidate(probs, thr, wrms, floor)
                    # Variants differ in class count; render from model labels.
                    payload = {
                        "type": "probs",
                        "ts": ts,
                        "model": g1_model,
                        "labels": g1_labels,
                        "probs": dict(zip(g1_labels, probs, strict=False)),
                        "nova": probs[0],
                        "piattos": probs[1],
                        "negative": (probs[2] if len(probs) > 2 else None),
                        "wake": wake,
                        "rms": round(wrms, 5),
                        "floor": round(floor, 5),
                    }
                    guard["recent"].append(wake)
                    votes = sum(
                        1 for w in guard["recent"] if w == wake and wake is not None
                    )
                    if not wake or votes < 2 or time.time() < guard["cooldown_until"]:
                        payload["wake"] = None
                    if wake and votes >= 2 and time.time() >= guard["cooldown_until"]:
                        guard["cooldown_until"] = time.time() + 5.0
                    _publish_room(payload)
                    await ws.send_json(payload)
                elif mode == "gate2":
                    probs = infer_gate2_for_connection(stream_acc[-WIN_SAMPLES:])
                    top_i = int(np.argmax(probs))
                    g2_labels = gates.gate2_labels()
                    await ws.send_json(
                        {
                            "type": "probs2",
                            "ts": ts,
                            "model": gates.gate2_active_model(),
                            "probs": dict(zip(g2_labels, probs, strict=False)),
                            "top": g2_labels[top_i],
                            "conf": probs[top_i],
                        }
                    )
                elif mode == "parallel":
                    # Parallel test page: Gate1 wake must latch first; then Gate2 + GateN/Gate4/Gate5
                    # score the SAME rolling window concurrently. Only Gate2's route selects the
                    # specialist value/action light; the other specialist outputs remain visible.
                    win = stream_acc[-WIN_SAMPLES:]
                    wrms = _level_rms(win)
                    floor = _track_ambient(guard["amb"], wrms)
                    monotonic_now = time.monotonic()
                    state = activations.snapshot(monotonic_now)
                    # If Gate1 is not latched, low-energy audio is just idle. If the wake latch is
                    # active, still run the parallel heads for inspection; the action light remains
                    # energy-gated below so silence cannot trigger a command.
                    if (
                        wrms < floor
                        and not state["g1"]["active"]
                        and not (time.time() < guard["calib_end"])
                    ):
                        guard["recent"].append(None)
                        guard["last_wake_event"] = None
                        activations.observe_gate2(
                            None, 0.0, thr["gate2MinConf"], monotonic_now
                        )
                        activations.consume_action()
                        state = activations.snapshot(monotonic_now)
                        await ws.send_json(
                            {
                                "type": "parallel",
                                "ts": ts,
                                "g1": {
                                    "active": state["g1"]["active"],
                                    "wake": state["g1"]["activation_label"],
                                    "candidate": None,
                                    "conf": state["g1"]["activation_conf"],
                                    "votes": 0,
                                    "rms": round(wrms, 5),
                                    "floor": round(floor, 5),
                                },
                                "gate2": None,
                                "specialists": {},
                                "action": None,
                                "stage": "quiet/noise gated - awaiting wake/command",
                            }
                        )
                        continue

                    p1, g1_labels, _ = gates.infer_g1_variant(g1_model, win)
                    wake = _wake_candidate(p1, thr, wrms, floor)
                    guard["recent"].append(wake)
                    votes = sum(
                        1 for w in guard["recent"] if w == wake and w is not None
                    )
                    if wake is not None and votes >= 2:
                        if (
                            wake != guard["last_wake_event"]
                            and time.time() >= guard["cooldown_until"]
                        ):
                            wake_index = 1 if wake == "Piattos" else 0
                            activations.activate_gate1(
                                monotonic_now, wake, p1[wake_index]
                            )
                            guard["last_wake_event"] = wake
                            guard["cooldown_until"] = time.time() + 5.0
                    else:
                        guard["last_wake_event"] = None
                    state = activations.snapshot(monotonic_now)
                    g1_state = {
                        "active": state["g1"]["active"],
                        "wake": state["g1"]["activation_label"],
                        "candidate": wake,
                        "conf": float(p1[int(np.argmax(p1[:2]))]),
                        "probs": dict(zip(g1_labels, p1, strict=False)),
                        "votes": votes,
                        "remaining_s": state["g1"]["remaining_s"],
                        "rms": round(wrms, 5),
                        "floor": round(floor, 5),
                    }
                    if not state["g1"]["active"]:
                        activations.observe_gate2(
                            None, 0.0, thr["gate2MinConf"], monotonic_now
                        )
                        activations.consume_action()
                        await ws.send_json(
                            {
                                "type": "parallel",
                                "ts": ts,
                                "g1": g1_state,
                                "gate2": None,
                                "specialists": {},
                                "action": None,
                                "stage": "waiting for Gate 1 wake word",
                            }
                        )
                        continue

                    # All four model branches are independent and run concurrently after wake.
                    try:
                        outputs = await asyncio.to_thread(gates.infer_parallel, win)
                    except (RuntimeError, OSError, ValueError) as exc:
                        await ws.send_json(
                            {
                                "type": "parallel",
                                "ts": ts,
                                "g1": g1_state,
                                "gate2": None,
                                "specialists": {},
                                "action": None,
                                "stage": "parallel inference error: " + str(exc),
                            }
                        )
                        continue

                    g2_result = outputs["gate2"]
                    current_intent = g2_result["top"]
                    current_conf = float(g2_result["conf"])
                    suppressed = _gate2_suppressed(p1)
                    g2_threshold = thr["g2thr"].get(current_intent, thr["gate2MinConf"])
                    if suppressed or wrms < floor:
                        # No G2 activation during wake-dominated or quiet windows.
                        activations.observe_gate2(
                            None, 0.0, thr["gate2MinConf"], monotonic_now
                        )
                    else:
                        activations.observe_gate2(
                            current_intent, current_conf, g2_threshold, monotonic_now
                        )
                    state = activations.snapshot(monotonic_now)
                    intent = (
                        state["g2"]["activation_intent"]
                        if state["g2"]["active"]
                        else current_intent
                    )
                    intent_conf = (
                        state["g2"]["activation_conf"]
                        if state["g2"]["active"]
                        else current_conf
                    )
                    branch_summary = {
                        name: {"label": result["top"], "conf": result["conf"]}
                        for name, result in outputs["specialists"].items()
                    }
                    parallel_mod = importlib.import_module("parallel_pipeline")
                    action = parallel_mod.select_parallel_action(
                        wake_active=state["g1"]["active"]
                        and not suppressed
                        and wrms >= floor,
                        intent=intent,
                        intent_confidence=intent_conf,
                        threshold=g2_threshold,
                        specialists=branch_summary,
                        routing=ROUTING,
                    )
                    triggered = (
                        (not suppressed)
                        and wrms >= floor
                        and activations.action_ready(monotonic_now)
                    )
                    action["light"] = bool(triggered)
                    action["triggered"] = bool(triggered)
                    if triggered:
                        activations.consume_action()
                    await ws.send_json(
                        {
                            "type": "parallel",
                            "ts": ts,
                            "stage": "wake active - branches scored concurrently",
                            "g1": g1_state,
                            "gate2": {
                                "model": outputs["model"],
                                "intent": current_intent,
                                "conf": current_conf,
                                "threshold": g2_threshold,
                                "active": state["g2"]["active"],
                                "probs": g2_result["probs"],
                            },
                            "specialists": outputs["specialists"],
                            "action": action,
                        }
                    )
                else:  # pipe: G1 wake on the latest 6-second frame → Gate 2 only while latched → specialists → LIGHT-first action
                    wake_ack = None
                    # Frame memory: store continuous audio; slice all accumulated audio into 1s frames
                    if frame_pending:
                        pending_audio = np.concatenate(frame_pending)
                        frame_pending.clear()
                        while pending_audio.size >= SR:
                            pframes.append_second_frame(
                                frame_mem, pending_audio[:SR], SR
                            )
                            pending_audio = pending_audio[SR:]
                        if pending_audio.size > 0:
                            frame_pending.append(pending_audio)
                    win_frame = pframes.frame_window(frame_mem, WIN_SAMPLES)
                    win = (
                        win_frame
                        if win_frame is not None
                        else stream_acc[-WIN_SAMPLES:]
                    )
                    g3_win = pframes.frame_window(frame_mem, 8 * SR)
                    specialist_win = g3_win if g3_win is not None else win
                    wrms = _level_rms(win)
                    floor = _track_ambient(guard["amb"], wrms)
                    monotonic_now = time.monotonic()
                    if nc["enabled"]:
                        # Noise canceller: learn from the raw window, then clean the
                        # inference windows only; energy gating stays on raw audio.
                        _nc_noise_update(win, nc)
                        win = _nc_apply(win, nc)
                        specialist_win = _nc_apply(specialist_win, nc)
                    elapsed_s = time.monotonic() - tick_start_time
                    if skip_ticks_enabled:
                        if elapsed_s > tick_interval:
                            skipped_ticks += int(elapsed_s // tick_interval)
                            # Which realtime seconds were skipped: every overrun
                            # means interval-length audio windows that no tick
                            # evaluated. Log the wall-clock moment + the overrun
                            # so the operator can pick a saner cadence.
                            skip_log.append(
                                {
                                    "wall": datetime.now().strftime("%H:%M:%S"),
                                    "gap": round(elapsed_s, 2),
                                }
                            )
                            drift_s += elapsed_s - tick_interval
                    else:
                        skipped_ticks = 0
                        skip_log.clear()
                        drift_s = 0.0
                    # Delay indicator: a tick whose scoring exceeds the evaluation
                    # interval reports late=true and eval_ms so the dashboard can
                    # warn the operator in real time.
                    tick_late = elapsed_s > tick_interval
                    memory_state = {
                        "seconds": len(frame_mem),
                        "max": mem_max,
                        "window_frames": min(
                            pframes.FRAME_WINDOW_FRAMES, len(frame_mem)
                        ),
                        "source": "frames" if win_frame is not None else "rolling",
                        "scheduler": {
                            "interval_s": tick_interval,
                            "skipped_ticks": skipped_ticks,
                            "skip_ticks_enabled": skip_ticks_enabled,
                            "eval_ms": round(elapsed_s * 1000.0),
                            "late": tick_late,
                            "drift_s": round(drift_s, 2),
                            "skipped_log": list(skip_log),
                        },
                        "noise_canceller": {
                            "enabled": nc["enabled"],
                            "ready": nc["profile"] is not None,
                        },
                    }
                    if wrms < floor and not (time.time() < guard["calib_end"]):
                        reset_gate2_pid()
                        # Silence cannot create new activations, but existing
                        # 8s/4s windows keep running and may still overlap.
                        guard["recent"].append(None)
                        guard["last_wake_event"] = None
                        activations.observe_gate2(
                            None, 0.0, thr["gate2MinConf"], monotonic_now
                        )
                        state = activations.snapshot(monotonic_now)
                        g1_state = dict(state["g1"])
                        g1_state.update(
                            {
                                "probs": [],
                                "wake": g1_state["activation_label"],
                                "label": "gated (room "
                                + str(round(wrms, 5))
                                + " < floor "
                                + str(round(floor, 5))
                                + ")",
                                "votes": 0,
                                "rms": round(wrms, 5),
                                "floor": round(floor, 5),
                            }
                        )
                        g2_state = dict(state["g2"])
                        g2_state.update(
                            {
                                "intent": g2_state["activation_intent"],
                                "conf": g2_state["activation_conf"],
                                "current_intent": None,
                                "current_conf": 0.0,
                                "probs": [],
                                "model": gates.gate2_active_model(),
                                "labels": [],
                                "waiting": True,
                            }
                        )
                        payload = {
                            "type": "pipe",
                            "ts": ts,
                            "memory": memory_state,
                            "g1": g1_state,
                            "g2": g2_state,
                            "action_gate": state["action_gate"],
                        }
                        attach_action_result(payload, specialist_win, monotonic_now)
                        payload["path"] = pframes.pipe_path_steps(
                            g1=g1_state,
                            g2=g2_state,
                            spec=payload.get("spec"),
                            action_gate=payload.get("action_gate"),
                            g2_ran=False,
                        )
                        payload["path_text"] = pframes.pipe_path_text(payload["path"])
                        diag_write(
                            conn_id,
                            "tick_gated",
                            {
                                "tick": tick_n,
                                "rms": round(wrms, 5),
                                "floor": round(floor, 5),
                                "drift_s": round(drift_s, 2),
                            },
                        )
                        _publish_room(payload)
                        await ws.send_json(payload)
                        continue

                    # Gate 1 and Gate 2 are independent heads: score both on this
                    # window concurrently; firing still needs both latches to overlap.
                    # Architecture v2/v3: Gate 2 sleeps until the wake latch opens —
                    # no Gate 2 inference runs before the wake word has been heard.
                    parallel = importlib.import_module("parallel_pipeline")
                    tasks: dict[str, Any] = {
                        "gate1": lambda w=win: gates.infer_g1_variant(g1_model, w),
                    }
                    if arch == 0 or activations.gate1_active(monotonic_now):
                        tasks["gate2"] = lambda w=win: infer_gate2_for_connection(w)
                    branch_results = parallel.run_in_parallel(tasks)
                    p1, _, _ = branch_results["gate1"]
                    p2 = branch_results.get("gate2")
                    wake = _wake_candidate(p1, thr, wrms, floor)
                    # Calibration records only ambient Gate1 scores; it cannot
                    # create or consume Action Gate activations.
                    if time.time() < guard["calib_end"]:
                        activations.observe_gate2(
                            None, 0.0, thr["gate2MinConf"], monotonic_now
                        )
                        guard["calib_max"] = max(guard["calib_max"], p1[0], p1[1])
                        if time.time() + 1.0 >= guard["calib_end"]:
                            new_thr = min(0.95, max(0.5, guard["calib_max"] + 0.05))
                            thr["Nova"] = new_thr
                            thr["Piattos"] = new_thr
                            guard["calib_end"] = 0.0
                            await ws.send_json(
                                {
                                    "type": "calibrated",
                                    "thr": {"Nova": new_thr, "Piattos": new_thr},
                                }
                            )
                        state = activations.snapshot(monotonic_now)
                        g1_calib = {
                            **state["g1"],
                            "probs": p1,
                            "wake": None,
                            "label": "calibrating…",
                        }
                        g2_calib = {
                            **state["g2"],
                            "intent": None,
                            "conf": 0.0,
                            "current_intent": None,
                            "current_conf": 0.0,
                            "probs": [],
                            "model": gates.gate2_active_model(),
                            "labels": [],
                            "waiting": True,
                        }
                        payload = {
                            "type": "pipe",
                            "ts": ts,
                            "memory": memory_state,
                            "g1": g1_calib,
                            "g2": g2_calib,
                            "action_gate": state["action_gate"],
                        }
                        payload["path"] = pframes.pipe_path_steps(
                            g1=g1_calib,
                            g2=g2_calib,
                            spec=None,
                            action_gate=payload.get("action_gate"),
                            g2_ran=False,
                        )
                        payload["path_text"] = pframes.pipe_path_text(payload["path"])
                        diag_write(
                            conn_id,
                            "tick_calib",
                            {
                                "tick": tick_n,
                                "calib_max": round(guard.get("calib_max", 0), 4),
                            },
                        )
                        _publish_room(payload)
                        await ws.send_json(payload)
                        continue

                    # Gate1 requires 2-of-3 agreement, then latches for 8s.
                    guard["recent"].append(wake)
                    votes = sum(
                        1 for w in guard["recent"] if w == wake and wake is not None
                    )
                    if wake is not None and votes >= 2:
                        if (
                            wake != guard["last_wake_event"]
                            and time.time() >= guard["cooldown_until"]
                        ):
                            wake_index = 1 if wake == "Piattos" else 0
                            activations.activate_gate1(
                                monotonic_now, wake, p1[wake_index]
                            )
                            guard["last_wake_event"] = wake
                            guard["cooldown_until"] = time.time() + 5.0
                            diag_write(
                                conn_id,
                                "wake",
                                {
                                    "tick": tick_n,
                                    "wake": wake,
                                    "conf": round(float(p1[wake_index]), 4),
                                    "votes": votes,
                                },
                            )
                            # One wake-ack clip per latch: the dashboard plays it
                            # instead of the full-bank reply's placeholder beeps.
                            ack = assistant_clip(wake, "wake")
                            if ack is not None:
                                guard["wake_ack_seq"] = (
                                    int(guard.get("wake_ack_seq", 0)) + 1
                                )
                                wake_ack = {
                                    "intent": "wake",
                                    "event_id": guard["wake_ack_seq"],
                                    "room_active": bool(_ROOM_QUEUES),
                                    **ack,
                                }
                    else:
                        guard["last_wake_event"] = None

                    state = activations.snapshot(monotonic_now)
                    # Gate 2 runs every active tick in v1; in v2/v3 it sleeps until
                    # the Gate 1 wake latch opens (p2 stays None while asleep).
                    # Firing always requires the Gate 1 + Gate 2 latches to overlap
                    # via activations.action_ready, not this inference.
                    if p2 is None:
                        # Architecture v2/v3: Gate 2 slept this tick — the wake latch
                        # was not open when the window was scored. Report it as asleep
                        # (meter shows WAIT) and leave the latch state untouched.
                        g2_ran = False
                        reset_gate2_pid()
                        current_intent, current_conf = None, 0.0
                        g2_threshold = thr["gate2MinConf"]
                    else:
                        g2_ran = True
                        current_intent, current_conf = _g2_candidate_intent(
                            p2, gates.gate2_labels(), thr["g2thr"], thr["gate2MinConf"]
                        )
                        g2_threshold = thr["g2thr"].get(
                            current_intent, thr["gate2MinConf"]
                        )
                        if arch == 2:
                            # Architecture v3: intent vote — arm the command latch only
                            # after the SAME qualifying intent repeats on two consecutive
                            # ticks (single-tick blips die here, like the recording lab).
                            v3_qualified = (
                                bool(current_intent)
                                and current_intent != "NEGATIVE"
                                and np.isfinite(current_conf)
                                and current_conf >= g2_threshold
                            )
                            if v3_qualified:
                                if guard["v3_intent"] == current_intent:
                                    guard["v3_streak"] = int(guard["v3_streak"]) + 1
                                else:
                                    guard["v3_intent"] = current_intent
                                    guard["v3_streak"] = 1
                                if int(guard["v3_streak"]) >= 2:
                                    activations.observe_gate2(
                                        current_intent,
                                        current_conf,
                                        g2_threshold,
                                        monotonic_now,
                                    )
                            else:
                                guard["v3_intent"] = None
                                guard["v3_streak"] = 0
                                activations.observe_gate2(
                                    None, 0.0, g2_threshold, monotonic_now
                                )
                        else:
                            # Gate 1 is latched here, so the speaker addressed the assistant
                            # and the trailing window is a real wake+command pair. Score Gate 2
                            # live: the wake word's audio tail shares the 5.92s window with the
                            # command after a natural pause, and resetting on wake dominance
                            # (owner-voice E2E 2026-10-17) made every real command unlatchable.
                            # Idle safety is already layered: NEGATIVE never latches, the
                            # per-class threshold rejects weak audio, the quiet gate resets on
                            # silence, and the wake-grace ordering blocks cross-pair staleness.
                            activations.observe_gate2(
                                current_intent,
                                current_conf,
                                g2_threshold,
                                monotonic_now,
                            )
                    state = activations.snapshot(monotonic_now)
                    g1_state = dict(state["g1"])
                    g1_state.update(
                        {
                            "probs": p1,
                            "wake": g1_state["activation_label"]
                            if g1_state["active"]
                            else None,
                            "label": g1_state["activation_label"]
                            if g1_state["active"]
                            else (wake or "scanning…"),
                            "votes": votes,
                            "rms": round(wrms, 5),
                            "floor": round(floor, 5),
                        }
                    )
                    g2_state = dict(state["g2"])
                    g2_state.update(
                        {
                            "intent": g2_state["activation_intent"]
                            if g2_state["active"]
                            else current_intent,
                            "conf": g2_state["activation_conf"]
                            if g2_state["active"]
                            else current_conf,
                            "current_intent": current_intent,
                            "current_conf": current_conf,
                            "probs": [] if p2 is None else p2,
                            "model": gates.gate2_active_model(),
                            "labels": gates.gate2_labels(),
                            "threshold": g2_threshold,
                            "waiting": p2 is None,
                        }
                    )
                    payload = {
                        "type": "pipe",
                        "ts": ts,
                        "memory": memory_state,
                        "g1": g1_state,
                        "g2": g2_state,
                        "action_gate": state["action_gate"],
                    }
                    if wake_ack is not None:
                        payload["wake_response"] = wake_ack
                    attach_action_result(payload, specialist_win, monotonic_now)
                    payload["path"] = pframes.pipe_path_steps(
                        g1=g1_state,
                        g2=g2_state,
                        spec=payload.get("spec"),
                        action_gate=payload.get("action_gate"),
                        g2_ran=g2_ran,
                    )
                    payload["path_text"] = pframes.pipe_path_text(payload["path"])
                    g1d = payload.get("g1") or {}
                    g2d = payload.get("g2") or {}
                    agd = payload.get("action_gate") or {}
                    diag_write(
                        conn_id,
                        "tick",
                        {
                            "tick": tick_n,
                            "eval_ms": round(elapsed_s * 1000.0),
                            "late": tick_late,
                            "drift_s": round(drift_s, 2),
                            "g1_active": bool(g1d.get("active")),
                            "g1_label": g1d.get("activation_label") or g1d.get("wake"),
                            "g2_active": bool(g2d.get("active")),
                            "g2_intent": g2d.get("activation_intent")
                            or g2d.get("current_intent"),
                            "g2_conf": g2d.get("current_conf"),
                            "triggered": bool(agd.get("triggered")),
                        },
                    )
                    if agd.get("triggered") and agd.get("intent"):
                        # Action gate fired: log the full outcome for troubleshooting.
                        diag_write(
                            conn_id,
                            "action",
                            {
                                "tick": tick_n,
                                "intent": agd["intent"],
                                "conf": g2d.get("conf"),
                                "final": payload.get("final"),
                                "g1_label": activations.g1_label,
                                "event_id": agd.get("event_id"),
                                "specialists": payload.get("specialists", {}),
                                "g3to5p": payload.get("g3to5p", False),
                            },
                        )
                    _publish_room(payload)
                    await ws.send_json(payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print("[ticker] " + type(e).__name__ + ": " + str(e))

    async def ticker_safe() -> None:
        # A fatal error in one tick must never permanently stop the trigger
        # gantt: log it, tell the dashboard, and restart the evaluation loop.
        while not ws.closed:
            try:
                await ticker()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                detail = type(e).__name__ + ": " + str(e)
                print("[ticker-fatal] " + detail, flush=True)
                diag_write(conn_id, "ticker_error", {"error": detail})
                with contextlib.suppress(Exception):
                    await ws.send_json({"type": "ticker_error", "error": detail})
                await asyncio.sleep(0.5)

    tick = asyncio.create_task(ticker_safe())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                arr = np.frombuffer(msg.data, dtype="<f4")
                capture_chunks.append(arr)
                capture_samples += arr.shape[0]
                while (
                    capture_chunks
                    and capture_samples - capture_chunks[0].shape[0] >= CAPTURE_SAMPLES
                ):
                    capture_samples -= capture_chunks[0].shape[0]
                    capture_chunks.pop(0)

                received += arr.shape[0]
                if received // 16000 != (received - arr.shape[0]) // 16000:
                    line = (
                        "[ws] received samples: "
                        + str(received)
                        + " at "
                        + datetime.now().strftime("%H:%M:%S")
                    )
                    print(line, flush=True)
                    await asyncio.to_thread(_append_ws_received, line)
                stream_acc = np.concatenate([stream_acc, arr])[-WIN_SAMPLES:]
                if mode == "both":
                    frame_pending.append(arr)
            elif msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    if data.get("type") == "mode" and data.get("mode") in (
                        "gate1",
                        "gate2",
                        "both",
                        "parallel",
                    ):
                        next_mode = data["mode"]
                        if next_mode != mode:
                            mode = next_mode
                            activations.reset()
                            guard["recent"].clear()
                            guard["last_wake_event"] = None
                            guard["cooldown_until"] = 0.0
                            frame_pending.clear()
                            reset_gate2_pid()
                        next_tick_interval = _inference_interval_s(next_mode, data)
                        if next_tick_interval != tick_interval:
                            tick_interval = next_tick_interval
                            tick_interval_changed.set()
                    elif data.get("type") == "noise_canceller":
                        nc["enabled"] = bool(data.get("enabled"))
                        await ws.send_json(
                            {
                                "type": "noise_canceller",
                                "enabled": nc["enabled"],
                                "ready": nc["profile"] is not None,
                            }
                        )
                    elif data.get("type") == "thr":
                        t = data.get("thr", {})
                        for k in ("Nova", "Piattos", "gate2MinConf"):
                            if k in t:
                                thr[k] = float(t[k])
                        g2thr_in = t.get("g2thr")
                        if isinstance(g2thr_in, dict):
                            for intent_key, value in g2thr_in.items():
                                with contextlib.suppress(TypeError, ValueError):
                                    thr["g2thr"][str(intent_key)] = min(
                                        0.95, max(0.05, float(value))
                                    )
                    elif data.get("type") == "save_capture":
                        label = str(data.get("label") or "live-30s")
                        audio = (
                            np.concatenate(capture_chunks)
                            if capture_chunks
                            else np.zeros(0, dtype=np.float32)
                        )
                        if audio.size < SR:
                            await ws.send_json(
                                {
                                    "type": "capture_saved",
                                    "error": "less than 1 s captured - is the mic streaming?",
                                }
                            )
                        else:
                            entry = request.app["lab"].store.save(audio, label)
                            await ws.send_json(
                                {"type": "capture_saved", "recording": entry}
                            )
                    elif data.get("type") == "calibrate":
                        guard["calib_end"] = time.time() + float(
                            data.get("seconds", 10)
                        )
                        guard["calib_max"] = 0.0
                        guard["recent"].clear()
                        guard["last_wake_event"] = None
                        activations.reset()
                        reset_gate2_pid()
                    elif data.get("type") == "memory":
                        # Rolling-buffer size option: 6 s minimum (G1/G2 window),
                        # 20 s default. Specialists fall back to 5.92 s below 8 s.
                        try:
                            mem_max = min(20, max(6, int(data.get("seconds", 20))))
                        except (TypeError, ValueError):
                            mem_max = 20
                        frame_mem = deque(list(frame_mem)[-mem_max:], maxlen=mem_max)
                        frame_pending.clear()
                        await ws.send_json({"type": "memory", "seconds": mem_max})
                    elif data.get("type") == "interval":
                        req_int = data.get("interval_s")
                        if (
                            isinstance(req_int, (int, float))
                            and not isinstance(req_int, bool)
                            and req_int in (1, 2, 3, 6, 1.0, 2.0, 3.0, 6.0)
                        ):
                            next_tick_interval = float(req_int)
                            if next_tick_interval != tick_interval:
                                tick_interval = next_tick_interval
                                tick_interval_changed.set()
                            await ws.send_json(
                                {"type": "interval", "interval_s": tick_interval}
                            )
                    elif data.get("type") == "skip_ticks":
                        skip_ticks_enabled = bool(data.get("enabled", False))
                        if not skip_ticks_enabled:
                            skipped_ticks = 0
                        await ws.send_json(
                            {
                                "type": "skip_ticks",
                                "enabled": skip_ticks_enabled,
                                "skipped_ticks": skipped_ticks,
                            }
                        )
                    elif data.get("type") == "reset":
                        stream_acc = np.zeros(0, dtype=np.float32)
                        frame_pending.clear()
                        frame_mem.clear()
                        guard["recent"].clear()
                        guard["last_wake_event"] = None
                        guard["cooldown_until"] = 0.0
                        activations.reset()
                        reset_gate2_pid()
                        tick_n = 0
                        skipped_ticks = 0
                        drift_s = 0.0
                        skip_log.clear()
                        tick_interval_changed.set()
                        await ws.send_json(
                            {
                                "type": "reset",
                                "status": "ok",
                                "text": "pipeline reset complete",
                            }
                        )
                    elif data.get("type") == "manual_stop":
                        # Manual Stop: cancel the pending action and clear active
                        # latches; microphone capture and the dashboard keep running.
                        activations.manual_stop()
                        reset_gate2_pid()
                        guard["recent"].clear()
                        guard["last_wake_event"] = None
                        await ws.send_json(
                            {"type": "manual_stop", "ok": True, "ts": now()}
                        )
                    elif data.get("type") == "model":
                        model_name = str(data.get("model", ""))
                        if model_name in gates.g1_variants and model_name != g1_model:
                            g1_model = model_name
                            guard["recent"].clear()
                            guard["last_wake_event"] = None
                            guard["cooldown_until"] = 0.0
                            activations.reset()
                    elif data.get("type") == "g2model":
                        g2_model_name = str(data.get("model", ""))
                        if not g2_model_name:
                            # Query: report the active gate2 model without switching.
                            await ws.send_json(
                                {"type": "g2model", "model": gates.gate2_active_model()}
                            )
                        else:
                            await ws.send_json(
                                {
                                    "type": "status",
                                    "text": "loading gate2 model "
                                    + g2_model_name
                                    + "...",
                                }
                            )
                            try:
                                active_g2 = gates.set_gate2_model(g2_model_name)
                            except (ValueError, RuntimeError) as exc:
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "text": "gate2 model error: " + str(exc),
                                    }
                                )
                            else:
                                activations.reset()
                                guard["recent"].clear()
                                guard["last_wake_event"] = None
                                guard["cooldown_until"] = 0.0
                                await ws.send_json(
                                    {"type": "g2model", "model": active_g2}
                                )
                                await ws.send_json(
                                    {
                                        "type": "status",
                                        "text": "gate2 model set to " + active_g2,
                                    }
                                )
                    elif data.get("type") == "arch":
                        try:
                            next_arch = int(data.get("arch", 0))
                        except (TypeError, ValueError):
                            next_arch = 0
                        arch = max(0, min(2, next_arch))
                        activations.reset()
                        guard["recent"].clear()
                        guard["last_wake_event"] = None
                        guard["cooldown_until"] = 0.0
                        guard["v3_intent"] = None
                        guard["v3_streak"] = 0
                        reset_gate2_pid()
                        await ws.send_json({"type": "arch", "arch": arch})
                        await ws.send_json(
                            {
                                "type": "status",
                                "text": "architecture set to v" + str(arch + 1),
                            }
                        )
                except json.JSONDecodeError as exc:
                    print(
                        "[ws] ignored malformed JSON control frame: " + str(exc),
                        flush=True,
                    )
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        tick.cancel()
    return ws


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(_asset("vcm_monitor.html"))


async def gate2_rnnoise_test_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(_asset("gate2_rnnoise_test.html"))


async def gate2_phrase_recorder_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(_asset("gate2_phrase_recorder.html"))


async def dataset_recorder_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(_asset("dataset_recorder.html"))


VERSION_PAGES = {
    "gate1_monitor.html",
    "gate1_monitor_v2.html",
    "gate1_monitor_v3.html",
    "gate1_monitor_v4.html",
    "gate1_monitor_v5.html",
}


async def gate1_page(request: web.Request) -> web.FileResponse:
    """Serve the requested per-version monitor page by URL path."""
    path = request.path.lstrip("/")
    if path not in VERSION_PAGES:
        path = "gate1_monitor.html"
    return web.FileResponse(_asset(path))


async def pipeline_all_in_one_page(request: web.Request) -> web.FileResponse:
    """Serve the standalone all-pipelines page (no monitor tabs)."""
    target = (
        "pipeline_all_in_one.thml"
        if request.path.endswith(".thml")
        else "pipeline_all_in_one.html"
    )
    if not _asset(target).is_file():
        target = "pipeline_all_in_one.html"
    return web.FileResponse(
        _asset(target), headers={"Content-Type": "text/html; charset=utf-8"}
    )


OWNER_VOICE_DIR = GATE2V6_PKG / "owner_voice_test"


async def owner_voice_evaluate(request: web.Request) -> web.Response:
    """Batch-score Leandro's 280 recorded voice WAVs through the live Gate 2 path."""
    ove = importlib.import_module("owner_voice_eval")
    gates = request.app["gates"]
    if not (OWNER_VOICE_DIR / "manifest.csv").is_file():
        return web.json_response(
            {"error": "manifest.csv not found under " + str(OWNER_VOICE_DIR)},
            status=404,
        )
    entries = ove.load_manifest(OWNER_VOICE_DIR / "manifest.csv")

    def run_batch() -> dict[str, Any]:
        def loader(path: str, entry: dict[str, str]) -> np.ndarray:
            audio, _ = librosa.load(str(OWNER_VOICE_DIR / path), sr=SR, mono=True)
            return np.asarray(audio, dtype=np.float32)

        def predict_fn(
            waveform: np.ndarray, entry: dict[str, str]
        ) -> tuple[str, float]:
            probs = gates.infer_gate2(waveform)
            labels = gates.gate2_labels()
            top = int(np.argmax(probs))
            return labels[top], float(probs[top])

        summary = ove.evaluate_recordings(entries, predict_fn, loader=loader)
        summary["model"] = gates.gate2_active_model()
        summary["manifest_entries"] = len(entries)
        return summary

    try:
        summary = await asyncio.to_thread(run_batch)
    except (OSError, RuntimeError, ValueError) as exc:
        return web.json_response({"error": str(exc)}, status=500)
    return web.json_response(summary)


RECORDINGS_DIR = HERE / "recordings"
CAPTURE_SAMPLES = 30 * SR  # "save the past 30 seconds" capture ring
LOGS_DIR = HERE / "logs"
_DIAG_LOCK = threading.Lock()
_DIAG_RING: deque = deque(maxlen=300)


def diag_write(conn_id: str, kind: str, data: dict) -> None:
    """Append one JSON line to the live pipeline log + in-memory ring.

    Every tick, trigger, capture, and failure lands here so any run can be
    replayed or troubleshooted after the fact without SSH or console access.
    """
    entry = {"ts": datetime.now(UTC).isoformat(), "conn": conn_id, "kind": kind, **data}
    try:
        with _DIAG_LOCK:
            _DIAG_RING.append(entry)
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            path = LOGS_DIR / (
                "live_" + datetime.now(UTC).strftime("%Y%m%d") + ".jsonl"
            )
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def diag_ring(last: int = 120) -> list[dict]:
    with _DIAG_LOCK:
        items = list(_DIAG_RING)
    return items[-max(1, min(last, len(items))) :]


class RecordingLabRunner:
    """Replay a recording through explicit Gate 2 models, off the live selection.

    V56 PID builds keep per-job streaming state, mirroring the live path; a new
    runner is created for every test job, so no state leaks between runs.
    """

    def __init__(
        self,
        gates: Any,
        g1_model: str,
        thresholds: dict[str, float] | None = None,
        gate2_thresholds: dict[str, float] | None = None,
    ) -> None:
        self.gates = gates
        self.g1_model = g1_model
        self.thresholds = dict(thresholds or {})
        self.gate2_thresholds = dict(gate2_thresholds or {})
        self._pid: dict[str, Any] = {}

    def models(self) -> list[str]:
        """Every shipped Gate 2 package the lab can load (Keras build excluded: it needs TF)."""
        return [name for name in GATE2_PACKAGE_RUNNERS if name != "gate2v6_keras"]

    def wake_probs(self, window: np.ndarray) -> tuple[np.ndarray, list[str]]:
        probs, labels, _ = self.gates.infer_g1_variant(self.g1_model, window)
        return np.asarray(probs, dtype=np.float32)[:2], [
            str(label) for label in labels[:2]
        ]

    def wake_thresholds(self) -> dict[str, float]:
        return {
            "Nova": float(self.thresholds.get("Nova", 0.5)),
            "Piattos": float(self.thresholds.get("Piattos", 0.5)),
        }

    def score_gate2(
        self, model: str, window: np.ndarray
    ) -> tuple[np.ndarray, list[str], float]:
        pid_state = None
        if model in GATE2_PID_CONFIGS:
            state = self._pid.get(model)
            if state is None:
                state = _v56_pid_module().new_state()
                self._pid[model] = state
            pid_state = state
        started = time.perf_counter()
        probs = self.gates.score_gate2_model(model, window, pid_state=pid_state)
        ms = (time.perf_counter() - started) * 1000.0
        return (
            np.asarray(probs, dtype=np.float32),
            self.gates.gate2_labels_for(model),
            ms,
        )

    def reset_pid(self, model: str) -> None:
        """Drop the PID controller state so the next lane starts fresh."""
        self._pid.pop(model, None)

    def gate2_threshold(self, intent: str) -> float:
        default = float(self.thresholds.get("gate2MinConf", 0.5))
        return float(self.gate2_thresholds.get(intent, default))

    def specialists(self, window: np.ndarray, routed: str) -> dict[str, Any] | None:
        """Routed specialist (gateN/gate4/gate5) on the trailing window — Gate 3 replay.

        Uses the legacy TFLite trio (always available, deterministic across
        replays); the live path prefers the Gate3-5P TensorFlow pack when the
        routed intent has one, but replay charts only need the routed outcome.
        """
        if routed not in ("gateN", "gate4", "gate5"):
            return None
        scores = self.gates.infer(routed, window)
        best = int(np.argmax(scores))
        return {
            "gate": routed,
            "label": str(self.gates.labels[routed][best]),
            "conf": scores[best],
        }


async def recording_lab_page(request: web.Request) -> web.FileResponse:
    """Serve the recording lab page (record minutes, replay through every Gate 2 model)."""
    return web.FileResponse(
        _asset("recording_lab.html"),
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


async def api_recordings(request: web.Request) -> web.Response:
    return web.json_response({"recordings": request.app["lab"].store.list()})


async def api_recording_save(request: web.Request) -> web.Response:
    """Persist a browser-recorded take (base64 WAV) as a lab recording."""
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        return web.json_response({"error": "expected a JSON body"}, status=400)
    raw_b64 = str(body.get("wav_base64", "")).split(",")[-1].strip()
    if not raw_b64:
        return web.json_response({"error": "wav_base64 required"}, status=400)
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except (ValueError, TypeError) as exc:
        return web.json_response(
            {"error": "bad base64 payload: " + str(exc)}, status=400
        )
    try:
        audio = recording_lab.decode_wav_bytes(raw)
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    if audio.size < recording_lab.SR // 4:
        return web.json_response(
            {"error": "recording is shorter than 0.25 s"}, status=400
        )
    entry = request.app["lab"].store.save(
        audio,
        str(body.get("label", "recording")),
        meta={"wake_word": body.get("wake_word", ""), "action": body.get("action", "")},
    )
    return web.json_response({"recording": entry})


async def api_recording_item(request: web.Request) -> web.Response:
    """PATCH (rename / trim) or DELETE one recording."""
    lab = request.app["lab"]
    rec_id = request.match_info["rec_id"]
    if lab.store.get(rec_id) is None:
        return web.json_response({"error": "unknown recording"}, status=404)
    if request.method == "DELETE":
        return web.json_response({"deleted": lab.store.delete(rec_id), "id": rec_id})
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}
    audio = None
    start_s, end_s = body.get("trim_start_s"), body.get("trim_end_s")
    if start_s is not None or end_s is not None:
        buffer = lab.store.load(rec_id)
        if buffer is None:
            return web.json_response({"error": "recording audio missing"}, status=404)
        first = max(0, int(float(start_s or 0.0) * recording_lab.SR))
        last = (
            min(buffer.size, int(float(end_s) * recording_lab.SR))
            if end_s is not None
            else buffer.size
        )
        if last - first < recording_lab.SR // 4:
            return web.json_response(
                {"error": "trim would leave less than 0.25 s"}, status=400
            )
        audio = buffer[first:last]
    meta = (
        {k: body[k] for k in ("wake_word", "action") if k in body}
        if any(k in body for k in ("wake_word", "action"))
        else None
    )
    updated = lab.store.update(rec_id, label=body.get("label"), audio=audio, meta=meta)
    if updated is None:
        return web.json_response({"error": "update failed"}, status=400)
    return web.json_response({"recording": updated})


async def api_recording_audio(request: web.Request) -> web.FileResponse:
    """Play or download one recording's WAV (?download=1 forces a save dialog)."""
    lab = request.app["lab"]
    entry = lab.store.get(request.match_info["rec_id"])
    if entry is None:
        raise web.HTTPNotFound()
    path = lab.store.path_of(entry)
    if not path.is_file():
        raise web.HTTPNotFound()
    headers = {"Content-Type": "audio/wav"}
    if request.query.get("download"):
        headers["Content-Disposition"] = 'attachment; filename="' + path.name + '"'
    return web.FileResponse(path, headers=headers)


async def api_recording_test(request: web.Request) -> web.Response:
    """Queue a whole-Gate-2 replay of one recording (runs off the live ticker)."""
    lab = request.app["lab"]
    rec_id = request.match_info["rec_id"]
    if lab.store.get(rec_id) is None:
        return web.json_response({"error": "unknown recording"}, status=404)
    try:
        body = await request.json()
    except (ValueError, json.JSONDecodeError):
        body = {}
    gates = request.app["gates"]
    # Gate 1 variants: explicit list, or the dashboard's default wake model.
    g1_requested = body.get("g1_models")
    if not g1_requested:
        g1_requested = [str(body.get("g1_model") or DEFAULT_G1_MODEL)]
    g1_models = [g for g in (str(x) for x in g1_requested) if g in gates.g1_variants]
    if not g1_models:
        g1_models = [DEFAULT_G1_MODEL]
    runner_probe = RecordingLabRunner(gates, g1_models[0])
    testable = runner_probe.models()
    requested = body.get("models")
    if not requested or requested == "all":
        models = testable
    else:
        models = [str(name) for name in requested if str(name) in testable]
    if not models:
        return web.json_response(
            {"error": "no testable Gate 2 models requested"}, status=400
        )
    combos = [(g1, g2) for g1 in g1_models for g2 in models]

    def runner_factory(g1_model: str) -> RecordingLabRunner:
        # One runner per Gate 1 variant: fresh PID state per combination, and
        # the live dashboard's own runner selection is never touched.
        return RecordingLabRunner(
            gates,
            g1_model,
            thresholds=body.get("thresholds") or {},
            gate2_thresholds=body.get("gate2_thresholds") or {},
        )

    # NC axis: nc_modes [False]/[True]/[False, True] (both = A/B every pair),
    # falling back to the single "nc" flag for older callers.
    raw_modes = body.get("nc_modes")
    nc_modes = (
        [bool(m) for m in raw_modes]
        if isinstance(raw_modes, list) and raw_modes
        else [bool(body.get("nc", False))]
    )
    raw_gated = body.get("gated_modes")
    gated_modes = (
        [bool(m) for m in raw_gated]
        if isinstance(raw_gated, list) and raw_gated
        else [bool(body.get("gated", False))]
    )
    raw_arch = body.get("architectures")
    architectures = (
        sorted({int(a) for a in raw_arch})
        if isinstance(raw_arch, list) and raw_arch
        else None
    )
    try:
        workers = max(0, int(body.get("workers", 0) or 0))
    except (TypeError, ValueError):
        workers = 0
    try:
        job = lab.start_test(
            rec_id,
            combos,
            runner_factory,
            hop_s=float(body.get("hop_s", 1.0) or 1.0),
            nc_modes=nc_modes,
            gated_modes=gated_modes,
            architectures=architectures,
            workers=workers,
        )
    except (KeyError, ValueError) as exc:
        diag_write("lab", "test-job-error", {"rec_id": rec_id, "error": str(exc)[:300]})
        return web.json_response({"error": str(exc)}, status=400)
    diag_write(
        "lab",
        "test-job-start",
        {
            "job_id": job.get("id"),
            "recording": rec_id,
            "combos": len(combos),
            "g1": g1_models,
            "models": models,
            "hop_s": float(body.get("hop_s", 1.0) or 1.0),
            "nc_modes": nc_modes,
        },
    )
    return web.json_response({"job": job})


async def api_job(request: web.Request) -> web.Response:
    job = request.app["lab"].job(request.match_info["job_id"])
    if job is None:
        return web.json_response({"error": "unknown job"}, status=404)
    return web.json_response({"job": job})


def _g3_pack_available() -> bool:
    """Gate3-5P pack loads when TensorFlow is installed and every model file exists."""
    import importlib.util

    if importlib.util.find_spec("tensorflow") is None:
        return False
    return all(
        (G3TO5P_DIR / "models" / f"{fname}.keras").is_file()
        for fname in G3TO5P_MAP.values()
    )


async def api_lab_models(request: web.Request) -> web.Response:
    """Gate 1 variants, Gate 2 models and Gate 3 specialists the lab can replay."""
    return web.json_response(
        {
            "g1_models": sorted(request.app["gates"].g1_variants),
            "models": sorted(GATE2_PACKAGE_RUNNERS),
            "g3": {
                "dir": str(G3TO5P_DIR),
                "routes": dict(G3TO5P_MAP),
                "available": _g3_pack_available(),
            },
        }
    )


async def api_results(request: web.Request) -> web.Response:
    return web.json_response({"results": request.app["lab"].results()})


async def api_diag(request: web.Request) -> web.Response:
    try:
        last = int(request.query.get("last", "150"))
    except ValueError:
        last = 150
    return web.json_response({"lines": diag_ring(last)})


async def api_client_log(request: web.Request) -> web.Response:
    """Receive UI-side errors (window.onerror / unhandledrejection) from the page.

    Every dashboard crash lands in the same live jsonl as the pipeline ticks, so
    a dead button or stalled gantt can be troubleshooted after the fact.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    diag_write(
        "ui",
        str(body.get("kind") or "client-error"),
        {
            "message": str(body.get("message") or "")[:500],
            "source": str(body.get("source") or "")[:200],
            "line": body.get("line"),
            "col": body.get("col"),
            "url": str(body.get("url") or "")[:200],
        },
    )
    return web.json_response({"ok": True})


async def api_job_log(request: web.Request) -> web.StreamResponse:
    path = request.app["lab"].job_log_path(request.match_info["job_id"])
    if not path.is_file():
        return web.json_response({"error": "no log for this job"}, status=404)
    return web.FileResponse(path, headers={"Content-Type": "text/plain; charset=utf-8"})


async def api_job_cancel(request: web.Request) -> web.Response:
    job_id = request.match_info["job_id"]
    cancelled = request.app["lab"].cancel(job_id)
    diag_write(
        "lab", "test-job-cancel", {"job_id": job_id, "cancelled": bool(cancelled)}
    )
    return web.json_response({"cancelled": cancelled, "id": job_id})


async def api_result_item(request: web.Request) -> web.Response:
    lab = request.app["lab"]
    job_id = request.match_info["job_id"]
    if request.method == "DELETE":
        return web.json_response({"deleted": lab.delete_result(job_id), "id": job_id})
    job = lab.result(job_id)
    if job is None:
        return web.json_response({"error": "unknown result"}, status=404)
    return web.json_response({"job": job})


@web.middleware
async def _fresh_html(request: web.Request, handler: Any) -> web.StreamResponse:
    """Serve HTML uncached so a plain browser refresh shows the latest build."""
    resp = await handler(request)
    # Everything except streaming media is served uncached: the dashboard is
    # iterated on constantly and stale browser caches hid updates before.
    if not request.path.startswith(("/media/", "/assistant-responses/")):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp


def build_app() -> web.Application:
    exercise_root = HERE.parents[1]
    if str(exercise_root) not in sys.path:
        sys.path.insert(0, str(exercise_root))
    slot_app = importlib.import_module("Gate3to5SlotSpecialistApp.app")
    # The recording lab uploads multi-minute WAV takes (base64), so the limit
    # must clear the slot app's default as well.
    app = web.Application(
        middlewares=[_fresh_html],
        client_max_size=max(int(slot_app.REQUEST_LIMIT), 96 * 1024 * 1024),
    )
    app["gates"] = Gates()
    app["lab"] = recording_lab.RecordingLab(HERE / "recordings")
    analysis_added = app["lab"].backfill_analysis()
    print(f"[recording-lab] analysis log: {analysis_added} lanes backfilled")
    # "/" opens the edited all-in-one pipeline test (the desktop icon lands
    # here); the legacy tabbed monitor stays reachable at /vcm_monitor.html.
    app.router.add_get("/", pipeline_all_in_one_page)
    app.router.add_get("/vcm_monitor.html", index)
    app.router.add_get("/gate2_rnnoise_test.html", gate2_rnnoise_test_page)
    app.router.add_get("/gate2_rnnoise_test_2s.html", gate2_rnnoise_test_page)
    app.router.add_get("/gate2_phrase_recorder.html", gate2_phrase_recorder_page)
    app.router.add_get("/dataset_recorder.html", dataset_recorder_page)
    app.router.add_get("/gate1_monitor.html", gate1_page)
    for v in ("v2", "v3", "v4", "v5"):
        app.router.add_get(f"/gate1_monitor_{v}.html", gate1_page)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/pipeline_all_in_one.html", pipeline_all_in_one_page)
    app.router.add_get("/pipeline_all_in_one.thml", pipeline_all_in_one_page)
    app.router.add_static("/assistant-responses/", path=str(ASSISTANT_AUDIO))
    lofi_path = exercise_root / "LoFiRadio"
    if not lofi_path.is_dir():
        lofi_path = Path("/home/lcsoneja/Desktop/LoFiRadio")
    if lofi_path.is_dir():
        app.router.add_static("/media/lofiradio/", path=str(lofi_path))
    calls_path = exercise_root / "Call_Sounds"
    if not calls_path.is_dir():
        calls_path = Path("/home/lcsoneja/Desktop/Call_Sounds")
    if calls_path.is_dir():
        app.router.add_static("/media/call-sounds/", path=str(calls_path))
    app.router.add_get("/ws/room", ws_room_handler)
    app.router.add_get("/room_sim.html", room_sim_page)
    app.router.add_post("/api/owner-voice/evaluate", owner_voice_evaluate)
    # --- recording lab: saved takes + whole-Gate-2 replays ---------------------
    app.router.add_get("/recording_lab.html", recording_lab_page)
    app.router.add_get("/api/recordings", api_recordings)
    app.router.add_post("/api/recordings", api_recording_save)
    app.router.add_patch("/api/recordings/{rec_id}", api_recording_item)
    app.router.add_delete("/api/recordings/{rec_id}", api_recording_item)
    app.router.add_get("/api/recordings/{rec_id}/audio", api_recording_audio)
    app.router.add_post("/api/recordings/{rec_id}/test", api_recording_test)
    app.router.add_get("/api/jobs/{job_id}", api_job)
    app.router.add_post("/api/jobs/{job_id}/cancel", api_job_cancel)
    app.router.add_get("/api/lab/models", api_lab_models)
    app.router.add_get("/api/results", api_results)
    app.router.add_get("/api/results/{job_id}", api_result_item)
    app.router.add_get("/api/analysis", api_analysis)
    app.router.add_delete("/api/results/{job_id}", api_result_item)
    app.router.add_get("/api/diag", api_diag)
    app.router.add_get("/api/jobs/{job_id}/log", api_job_log)
    app.router.add_post("/api/client-log", api_client_log)
    app.router.add_static("/js/", path=str(HERE / "gate1_web" / "js"))
    app.router.add_static("/vendor/", path=str(HERE / "gate1_web" / "vendor"))
    app.router.add_static("/data/", path=str(HERE / "gate1_web" / "data"))
    slot_app.register_routes(app, prefix="/gate3to5")
    # One-shot architecture (separate page): the wake word gates a single 5 s Gate 2 capture.
    # Additive only - it registers /oneshot.html and /ws/oneshot and touches no existing route.
    oneshot = importlib.import_module("oneshot_pipeline")
    oneshot.register_routes(app)
    return app


async def api_analysis(request: web.Request) -> web.Response:
    """The consolidated per-lane analysis log (ground truth + verdict per lane)."""
    lab = request.app["lab"]
    path = lab.job_log_path("analysis")
    rows = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
    return web.json_response({"rows": rows})


def main() -> None:
    app = build_app()
    print(
        "VCM unified monitor on http://127.0.0.1:8765/ (Gate1/Gate2 + Gate3-Gate5 candidates) - Ctrl+C to stop"
    )
    web.run_app(app, host="127.0.0.1", port=PORT, print=None)


if __name__ == "__main__":
    main()
