# Gate2V20 — phoneme-auxiliary CNN (EXPERIMENTAL)

V20 keeps the **audio-to-intent** path and V19's 148x60 frontend. During training only, an auxiliary CTC head predicts an eSpeak en-US IPA-symbol sequence derived from each V19 transcript. At inference the phone head is removed: the model takes audio features and outputs one of the 19 intents. This is not a separate ASR stage.

## Data and phone targets
- Exact V19 eight-view feature store and split: 235,968 train rows, 3,201 clean validation rows; no owner command audio used.
- eSpeak en-US G2P generated targets for 93 unique transcript phrases; 40 symbol tokens including word boundary plus CTC blank. CTC head has 74 steps; longest target 42 symbols / 42 minimum CTC steps.
- Phone labels are **pseudo-phonetic G2P targets**, not forced-aligned or human-verified acoustic phoneme annotations. Digraph phones may be split into IPA symbols.

## Architecture / loss
- V19 TC-ResNet intent path: 246,035 parameters; a 74-frame auxiliary phone-logit head adds 2,665 training-only parameters.
- Multitask training model: 248,700 parameters. Intent-only deployed model: 246,035 parameters.
- Loss: sparse intent cross-entropy + 0.1 x length-normalized CTC phone-symbol loss; V19 sample/class weighting retained.

## Results
- V20 clean synthetic validation: **98.84%** / 3,201; V19 CNN reference **98.53%**.
- Intent-only TFLite: 515,332 bytes; 64-row Keras/TFLite argmax parity 64/64; pure TFLite BUILTINS/no Flex.
- Host CPU TFLite p50: 0.255 ms vs V19 CNN 0.253 ms (1 thread, batch1; not Pi timing).

## Caveats
This is an auxiliary-label experiment, not a phoneme recognizer benchmark. The eSpeak phone strings are canonical en-US G2P derived from text, so accent/pronunciation mismatch and target noise are possible. No owner-voice evaluation was run. The owner-280 diagnostic is reused and p-models were trained on it; use a fresh session for an independent owner result. No Raspberry Pi latency/power test or full-integer INT8 export is included.
