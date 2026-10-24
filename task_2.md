# task_2.md - DGX agent: publish the models and the dataset

**Owner:** Leandro Soneja - AI 231 ME2
**Repo (application, already published):** https://github.com/lcsoneja/me2-voice-controlled-smart-device
**DGX host:** ai-n003

---

## 0. Scope - read this first

The **application is already on GitHub**. Do not re-upload it, do not fork it, do not
replace its commits. The repository already contains the dashboard server, the web UI, the
Gate 1 wake assets, the two headline Gate 2 packages, the decks and the evaluation scripts.

**Your job is only two things:**

1. **Models** -> publish the *complete, active* Gate 2 model set to **GitHub** (as a Release, not
   as loose commits - see section 2).
2. **Dataset** -> publish the *project's own* training/eval dataset artifacts to **HuggingFace**
   (section 3). GitHub cannot hold them.

If a step would modify the application repo's existing files or history: **stop and report.**

---

## 1. What "only what is needed" means, exactly

The application loads Gate 2 models through a registry. The registry is the single source of
truth for the active set, so do **not** hand-pick packages and do **not** copy the whole
`Shipping/` tree. That tree contains caches, reports, diagnostic and superseded packages and is
far larger than what runs.

**Resolution procedure (authoritative):**

```bash
git clone https://github.com/lcsoneja/me2-voice-controlled-smart-device.git
cd me2-voice-controlled-smart-device/vcm_live_test_local/vcm_live_test_local
python3 build_pi_release.py        # resolves GATE2_PACKAGE_RUNNERS and preflights every path
```

`build_pi_release.py` reads `GATE2_PACKAGE_RUNNERS` from `gate1_server.py` and fails loudly if
any model file, `labels.json`, or `preprocessing_spec.json` is missing. Reuse it; do not rewrite it.

**Expected counts (sanity check - report if yours differ):**

| Quantity | Expected |
| --- | --- |
| Active Gate 2 model IDs | **56** |
| Unique package directories | **53** |
| Minimal payload (TFLite + labels + spec, no reports/checkpoints) | **~39.6 MB** |

If your counts differ, the registry and your `Shipping/` copy disagree. **Stop and report the
difference**; do not "fix" it by copying extra packages.

**Per package, ship only:**

- `labels.json`
- `preprocessing_spec.json` (or the documented fallback package's spec)
- the referenced `tflite/*.tflite` (exactly the file the registry names)

**Do not ship:** `reports/`, `model_src/*.keras` training checkpoints, `__pycache__`,
`.build_*` staging, `*.tar.gz` intermediates, or any package not referenced by the registry.

---

## 2. Publish the models to GitHub

GitHub rejects or punishes large binaries in normal commits (hard 100 MB per file, ~1 GB repo
soft limit). Use a **Release**, which is the sanctioned path:

1. Build the payload with the script above (it writes `_pi_deploy/vcm_pi_latest_*.tar.gz` and a
   `RELEASE_MANIFEST.json` whose `gate2_active_model_ids` list must show the 56 IDs).
2. Also emit `SHA256SUMS.txt` for every file you publish (`sha256sum` output, sorted).
3. Create the release:

    ```bash
    gh release create models-v1.0-me2 \
      --repo lcsoneja/me2-voice-controlled-smart-device \
      --title "ME2 Gate 2 complete model set (56 active IDs / 53 packages)" \
      --notes "Registry-resolved active Gate 2 set. TFLite float16 + labels + preprocessing specs. See RELEASE_MANIFEST.json." \
      me2_models_20261024.tar.gz SHA256SUMS.txt RELEASE_MANIFEST.json
    ```

4. Attach only files that are referenced by the registry or describe it. Do not attach the
   training corpus.

**Auth:**

```bash
export GH_TOKEN=<fine-grained PAT, Contents: read/write on lcsoneja/me2-voice-controlled-smart-device>
gh auth status          # verify BEFORE doing anything
```

Never hardcode the token, never commit it, never echo it.

---

## 3. Publish the dataset to HuggingFace

GitHub is the wrong host for audio and for multi-GB corpora. The dataset goes to a
**HuggingFace dataset repo** owned by Leandro.

Already-published stores (verify and top up; do **not** recreate or re-upload from scratch):

| Store | Contents | Licence |
|---|---|---|
| `huggingface.co/datasets/Drewboy/ai231-vcm-v64p-training-store` | V64P training store (~300 files) | CC-BY-NC-4.0, research-only |
| `huggingface.co/datasets/Drewboy/ai231-vcm-v20aux-phoneme-store` | V20 phoneme-aux store (~15 files) | CC-BY-NC-4.0, research-only |

The HF account is **`Drewboy`**. Do not create a dataset repo under any other account.

```bash
huggingface-cli login          # token stays on this host; never commit it
huggingface-cli upload Drewboy/ai231-vcm-v64p-training-store <local_dir> --repo-type dataset
```

### 3a. HARD RULE - what may and may not be published

| Data | Publish? | Why |
| --- | --- | --- |
| The project's own manifests, split definitions, label maps, training/eval logs, per-source row counts | **Yes** | Owned by the project; needed to reproduce the reported numbers |
| Leandro's own collected owner-voice training data | **Only with explicit written authorization** | Personal voice data |
| Class gold dataset at `/data/ai231` | **Check permission first** | Owned by the class/Sir Mark; it is write-restricted and may not be redistributable by you |
| `martinnavs/ai231-fil-supplemental-data` | **No - link only** | A classmate's dataset, already public on HF |
| `airimonda/ai231-me2-voice-commands` | **No - link only** | A classmate's dataset, already public on HF |
| The frozen test split and any private recordings/sessions | **No, never** | Contaminates the benchmark and exposes personal audio |

Re-uploading a peer's dataset under Leandro's account is a licensing and attribution violation.
If the task seems to require it, **stop and report** - the correct action is to cite the upstream
repo in the dataset card.

### 3b. Dataset card must state

- provenance: dataset name, revision/hash, and per-source row counts;
- schema: the 9 fields (`audio_path, transcript, intent, slot, speaker_id, recording_env,
  is_synthetic, duration_ms, sample_rate`) and audio format (16 kHz mono WAV, 1 s);
- the 20 frozen labels and the fact that wake words (`Nova`, `Piattos`) are project-owned and
  appear in no public set;
- split policy: **the frozen test split (`SPLIT_LOCK.json`, seed 42) is never added to or
  re-derived**; all new data goes to train only;
- licence and citation, and explicit links to the two upstream dataset repos above;
- honesty note: reported accuracies describe these recordings and microphones.

---

## 4. Guardrails

- No cloud upload of private audio, transcripts or weights, except the deliberate publishing
  steps in sections 2 and 3.
- Never modify the frozen split, the label registry, or inference thresholds.
- Never rename model run directories (it breaks `CHECKPOINT_PATHS` in `live_session.py`).
- Do not retrain as part of this task. Publishing only.
- Do not commit `*.keras`, `*.tflite`, or any tarball into the repository's normal git history;
  Releases and HF only.
- If a path, token, permission or account is missing: **stop and report exactly what is missing.**
  Do not substitute another host, account, or dataset.

---

## 5. Verification (required before you report success)

1. Registry preflight passes with **56** IDs.
2. `sha256sum -c SHA256SUMS.txt` passes for every published file.
3. Confirm on the remote, not from your local state:

    ```bash
    gh release view models-v1.0-me2 --repo lcsoneja/me2-voice-controlled-smart-device
    gh release view models-v1.0-me2 --repo lcsoneja/me2-voice-controlled-smart-device --json assets --jq '.assets[] | "\(.size)\t\(.name)"'
    ```

4. Confirm no file you uploaded exceeds 100 MB and that no `*.keras` entered git history.
5. Re-download one published model package and confirm its TFLite loads:

    ```python
    from tflite_runtime.interpreter import Interpreter   # or ai_edge_litert on the laptop
    interp = Interpreter(model_path="gate2v64p_paired_owner_float16.tflite")
    interp.allocate_tensors()
    ```

Report the observed output shape and label count.

---

## 6. Report format

1. **Load/registry status** - counts vs expected (56 / 53 / ~39.6 MB), and any mismatch.
2. **Models** - release URL, asset names + sizes, SHA256 of the bundle, commit/release created.
3. **Dataset** - HF repo URL, file list, revision hash, and which data was cleared for release
   (with the authorization basis), plus what was deliberately excluded and why.
4. **Verification** - the exact commands run and their observed results.
5. **Blockers** - precisely what is missing or refused, if anything.

State clearly what you measured, what you only inspected, and what you did not do.
