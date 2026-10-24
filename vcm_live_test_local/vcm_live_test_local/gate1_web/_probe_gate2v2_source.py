"""Compare the legacy Gate2 v2 TFLite output to the two packaged legacy Keras sources."""
import importlib
from pathlib import Path

import numpy as np
import tensorflow as tf

APP = Path(__file__).resolve().parents[1]
SHIPPING = APP.parents[1] / "Shipping"
server = importlib.import_module("gate1_server")
rng = np.random.default_rng(20261017)
audio = rng.normal(0.0, 0.02, 96000).astype(np.float32)
features = server.Gate2V2Preproc().extract(audio)

interpreter = server._make_interpreter(APP / "gate1_web" / "gate2v2_float16.tflite")
input_info = interpreter.get_input_details()[0]
interpreter.set_tensor(input_info["index"], features.astype(input_info["dtype"]))
interpreter.invoke()
tflite_output = interpreter.get_tensor(interpreter.get_output_details()[0]["index"])[0]
print("tflite outputs", len(tflite_output))

for variant in ("clean", "augmented"):
    model = tf.keras.models.load_model(
        SHIPPING / "Gate2WorkingModels_ship" / "models" / variant / "best_model.keras",
        compile=False,
    )
    keras_output = model.predict(features, verbose=0)[0]
    print(variant, "params", model.count_params(), "max_abs_diff", float(np.max(np.abs(keras_output - tflite_output))))
    del model
    tf.keras.backend.clear_session()
