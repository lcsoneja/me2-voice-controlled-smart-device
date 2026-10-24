"""Read parameter totals from the packaged Gate2 Keras source checkpoints."""
import gc
from pathlib import Path

import tensorflow as tf

SHIPPING = Path(__file__).resolve().parents[3] / "Shipping"
PACKAGES = (
    "Gate2V6_ship_20261013",
    "Gate2V16_ship_20261017",
    "Gate2V18_ship_20261017",
    "Gate2V19_ship_20261017",
    "Gate2V19P_ship_EXPERIMENTAL_20261017",
    "Gate2V21_ship_20261017",
    "Gate2V21P_ship_EXPERIMENTAL_20261017",
    "Gate2V22_ship_20261017",
    "Gate2V22_SilenceNeg_ship_EXPERIMENTAL_20261017",
)

for package in PACKAGES:
    checkpoint = SHIPPING / package / "model_src" / "best_model.keras"
    try:
        model = tf.keras.models.load_model(checkpoint, compile=False)
        print(f"{package}: {model.count_params():,}")
        del model
        tf.keras.backend.clear_session()
        gc.collect()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"{package}: ERROR {type(exc).__name__}: {exc}")

for variant in ("clean", "augmented"):
    checkpoint = SHIPPING / "Gate2WorkingModels_ship" / "models" / variant / "best_model.keras"
    model = tf.keras.models.load_model(checkpoint, compile=False)
    print(f"Gate2WorkingModels {variant}: {model.count_params():,}")
    del model
    tf.keras.backend.clear_session()
    gc.collect()
