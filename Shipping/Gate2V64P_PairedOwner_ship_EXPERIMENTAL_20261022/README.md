# Gate2 V64P - Paired Negatives + Owner Fine-tune (PRODUCTION CANDIDATE)

V64d model fine-tuned with owner-280 recordings (8-view augmented, w=2.0).
20 outputs: 19 intents + NEG (background-only rejection).

## Key numbers
- Held-out owner val (43 clips): 100.00%
- Owner-280 (⚠️ FIT — training data): 280/280 = 100.00%
- NEG recall: 97.89%
- Params: 338,260; TFLite 698,728 B, p50 0.552 ms

## ⚠️ Owner-280 diagnostic is NOT independent for this model.
Use the AI231 holdout (holdout_check.py --filter v64p) for the independent verdict.
