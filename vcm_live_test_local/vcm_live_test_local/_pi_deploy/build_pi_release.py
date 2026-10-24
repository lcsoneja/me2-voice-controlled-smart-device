from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
from pathlib import Path

SCRIPT = Path(__file__).resolve()
APP = SCRIPT.parents[1]
PROJECT = APP.parents[1]
SHIPPING = PROJECT / "Shipping"
BUILD = SCRIPT.parent / ".build_pi_latest"
ARCHIVE = SCRIPT.parent / "vcm_pi_latest_20261024.tar.gz"

sys.path.insert(0, str(APP))
import gate1_server as server


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Required release directory missing: {source}")
    shutil.copytree(
        source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )


def main() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)
    if ARCHIVE.exists():
        ARCHIVE.unlink()

    dashboard = BUILD / "Exercise2" / "vcm_live_test_local" / "vcm_live_test_local"
    pi_shipping = BUILD / "Exercise2" / "Shipping"
    desktop = BUILD / "Desktop"
    dashboard.mkdir(parents=True)
    pi_shipping.mkdir(parents=True)
    desktop.mkdir(parents=True)

    runtime_files = (
        "gate1_server.py",
        "recording_lab.py",
        "nc_dsp.py",
        "pipeline_frames.py",
        "parallel_pipeline.py",
        "owner_voice_eval.py",
        "gate1_forward_reference.py",
        "mel_fb.npz",
        "vcm_pipeline.png",
    )
    for name in runtime_files:
        source = APP / name
        if not source.is_file():
            raise FileNotFoundError(f"Required dashboard file missing: {source}")
        shutil.copy2(source, dashboard / name)

    copy_tree(APP / "gate1_web", dashboard / "gate1_web")
    model_root = dashboard / "vcm8"
    (model_root / "config").mkdir(parents=True)
    (model_root / "training").mkdir(parents=True)
    shutil.copy2(
        APP / "vcm8" / "config" / "model_registry.json",
        model_root / "config" / "model_registry.json",
    )
    for source in (APP / "vcm8" / "training").glob("feature_stats*.npz"):
        shutil.copy2(source, model_root / "training" / source.name)
    copy_tree(APP / "vcm8" / "training" / "tflite", model_root / "training" / "tflite")
    copy_tree(
        PROJECT / "Gate3to5SlotSpecialistApp",
        BUILD / "Exercise2" / "Gate3to5SlotSpecialistApp",
    )

    # Keep the entire candidate/owner-specialist packages and response banks; do not copy training corpora.
    for name in (
        "Gate3to5_SlotSpecialists_Candidates_20261009",
        "Gate3to5P_OwnerFinetuned_ship_EXPERIMENTAL_20261017",
        "Gate2_AssistantResponses_ONEWORD_20261022",
        "Gate2_AssistantResponses_20261017",
    ):
        copy_tree(SHIPPING / name, pi_shipping / name)

    source_dirs = {
        entry.name.casefold(): entry for entry in SHIPPING.iterdir() if entry.is_dir()
    }

    def source_dir(expected: Path) -> Path:
        actual = source_dirs.get(expected.name.casefold())
        if actual is None:
            raise FileNotFoundError(
                f"Package directory missing (case-insensitive lookup): {expected}"
            )
        return actual

    active_models: list[str] = []
    copied_packages: set[str] = set()
    for model_name, (
        expected_dir,
        relative_model,
        fallback_dir,
    ) in server.GATE2_PACKAGE_RUNNERS.items():
        active_models.append(model_name)
        actual_dir = source_dir(expected_dir)
        model_source = actual_dir / relative_model
        labels_source = actual_dir / "labels.json"
        if not model_source.is_file() or not labels_source.is_file():
            raise FileNotFoundError(
                f"Incomplete Gate2 package for {model_name}: model={model_source}; labels={labels_source}"
            )
        target_dir = pi_shipping / expected_dir.name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_model = target_dir / relative_model
        target_model.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(model_source, target_model)
        shutil.copy2(labels_source, target_dir / "labels.json")
        copied_packages.add(expected_dir.name)

        spec_source = actual_dir / "preprocessing_spec.json"
        if spec_source.is_file():
            shutil.copy2(spec_source, target_dir / "preprocessing_spec.json")
        elif fallback_dir is not None:
            actual_fallback = source_dir(fallback_dir)
            fallback_spec = actual_fallback / "preprocessing_spec.json"
            if not fallback_spec.is_file():
                raise FileNotFoundError(
                    f"Fallback preprocessing spec missing for {model_name}: {fallback_spec}"
                )
            fallback_target = pi_shipping / fallback_dir.name
            fallback_target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fallback_spec, fallback_target / "preprocessing_spec.json")
            copied_packages.add(fallback_dir.name)
        else:
            raise FileNotFoundError(
                f"Preprocessing spec missing for {model_name}: {spec_source}"
            )

    for name in ("restart_vcm.sh", "vcm-dashboard.desktop", "handoff.md"):
        shutil.copy2(SCRIPT.parent / name, desktop / name)

    manifest = {
        "release": "2026-10-24 latest laptop dashboard build",
        "server_source_bytes": (APP / "gate1_server.py").stat().st_size,
        "dashboard_web_files": sum(
            1 for p in (dashboard / "gate1_web").rglob("*") if p.is_file()
        ),
        "gate2_active_model_ids": sorted(set(active_models)),
        "gate2_active_model_count": len(server.GATE2_PACKAGE_RUNNERS),
        "gate2_package_directories": sorted(copied_packages),
        "notes": [
            "Runtime TFLite artifacts only; no training checkpoints or dataset recordings.",
            "Pi app data/logs/recordings are preserved during installation.",
        ],
    }
    (BUILD / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    with tarfile.open(ARCHIVE, "w:gz") as bundle:
        for name in ("Exercise2", "Desktop", "RELEASE_MANIFEST.json"):
            bundle.add(BUILD / name, arcname=name)

    with tarfile.open(ARCHIVE, "r:gz") as bundle:
        members = {member.name for member in bundle.getmembers()}
        missing: list[str] = []
        for model_name, (
            package,
            relative_model,
            fallback_dir,
        ) in server.GATE2_PACKAGE_RUNNERS.items():
            prefix = f"Exercise2/Shipping/{package.name}/"
            if prefix + str(relative_model).replace("\\", "/") not in members:
                missing.append(f"{model_name}: model file")
            if prefix + "labels.json" not in members:
                missing.append(f"{model_name}: labels")
            spec_prefix = prefix + "preprocessing_spec.json"
            fallback_prefix = (
                f"Exercise2/Shipping/{fallback_dir.name}/preprocessing_spec.json"
                if fallback_dir
                else ""
            )
            if spec_prefix not in members and fallback_prefix not in members:
                missing.append(f"{model_name}: preprocessing spec")
        if missing:
            raise RuntimeError("Archive preflight failed: " + ", ".join(missing))

    archive_hash = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    print(f"ARCHIVE={ARCHIVE}")
    print(f"SIZE_BYTES={ARCHIVE.stat().st_size}")
    print(f"SHA256={archive_hash}")
    print(f"GATE2_MODELS={len(server.GATE2_PACKAGE_RUNNERS)}")
    print(f"GATE2_PACKAGES={len(copied_packages)}")
    print(f"WEB_RUNTIME_FILES={manifest['dashboard_web_files']}")
    print("PREFLIGHT=PASS")


if __name__ == "__main__":
    main()
