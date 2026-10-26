"""Fill me2-deck.pdf placeholders with measured values + append the best-combination table.

v3: spans cluster into visual lines; substitutions are CONTEXT-AWARE (each
table row keyed by its own label), so a missed line can never shift the
placeholder values. Unfilled lines are reported.
"""
import io
import json
import pathlib
import re

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

ROOT = pathlib.Path(__file__).resolve().parent
PROJ = ROOT / "vcm_live_test_local" / "vcm_live_test_local"
SRC = ROOT / "me2-deck.pdf"
DST = ROOT / "me2-deck-filled.pdf"
BEST = PROJ / "_best_combo.json"
IDX = PROJ / "recordings" / "index.json"

data = json.loads(BEST.read_text(encoding="utf-8")) if BEST.exists() else {}
best = data.get("best") or {}
rows = data.get("top") or []

n_takes, dur = 0, 0.0
if IDX.exists():
    idx = json.loads(IDX.read_text(encoding="utf-8"))
    recs = idx["recordings"] if isinstance(idx, dict) else idx
    n_takes = len(recs)
    dur = sum(float(r.get("duration_s") or 0) for r in recs)


def num(x, fmt="{:.1f}"):
    return fmt.format(x) if isinstance(x, (int, float)) and x >= 0 else "n/a"


full_rate = best.get("rate", -1)
act_rate = best.get("act", -1)
oos_rej = best.get("oos_rej", -1)
p95 = best.get("p95", -1)

RULES_P1 = [
    ("Parameters / weights", ["0.34", "0.70"]),
    ("Keyword / intent acc", [num(100 * full_rate), num(100 * act_rate)]),
    ("False-accept", [num(100 * (1 - oos_rej))]),
    ("Latency p95", [num(p95), num(p95 / 1000.0, "{:.3f}")]),
    ("Runtime", ["1"]),
    ("Hours / utts", [f"{dur / 3600:.2f}", str(n_takes)]),
    ("Speakers", ["6 real + synth + 1 owner"]),
    ("Labels", ["19", "3 (G3-5)"]),
    ("Steps / loss", ["n/a", "n/a"]),
    ("log-mel", ["148", "60"]),
    ("Causal encoder", ["n/a", "n/a"]),
]
RULES_P2 = [
    ("Repo public", ["done: repo public + benchmark.py"]),
    ("Dataset licensed", ["done: LICENSE.md (research-only)"]),
    ("Training logs", ["done: ships + SHA256 + model_src"]),
    ("Pi 4 latency", ["pending: Pi offline 2026-10-22"]),
    ("Held-out test set", ["done: holdout unseen speakers"]),
    ("Baseline of comparable", ["done: 55-model baseline sweep"]),
]
FILLS = [
    ("onnxruntime", "tflite (XNNPack)"),
    ("\u27e8fill: author / team\u27e9", "Leandro Soneja - AI 231 ME2"),
    ("\u27e8fill: CTC / attn\u27e9", "CNN (DS-CNN) classifier"),
    ("\u27e8fill: # A100\u27e9", "DGX Station - 1 GPU (local)"),
    ("Source \u27e8fill\u27e9", "Source ME2 holdout (HF: airimonda/ai231-me2) + owner-280 + SAPI wake"),
    ("Optimiser \u27e8fill\u27e9", "Optimiser n/a (ship model_src)"),
    ("\u27e8fill: org/repo \u2014 public, MIT\u27e9", "github.com/airimonda/vcm-benchmark"),
    ("\u27e8fill: Zenodo / HF DOI + access terms\u27e9", "huggingface.co/datasets/airimonda/ai231-me2-voice-commands"),
    ("\u27e8fill: node ID, # GPUs, wall-clock, seeds\u27e9", "DGX Station - local (see ships)"),
    ("\u27e8fill: release URL + licence\u27e9", "Shipping/ - TFLite f16 + SHA256SUMS"),
]
PLACEHOLDER = re.compile("\u27e8[^\u27e9]*\u27e9")

reader = PdfReader(str(SRC))
writer = PdfWriter()
stats = {"placeholder_lines": 0, "redrawn": 0, "unfilled": []}

for pno, page in enumerate(reader.pages):
    rules = RULES_P1 if pno == 0 else RULES_P2
    spans = []

    def collect(text, cm, tm, font_dict, font_size, _spans=spans):
        if text and text.strip():
            ax = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            ay = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            _spans.append((text, ax, ay, float(font_size or 9.0)))

    page.extract_text(visitor_text=collect)

    ordered = sorted(spans, key=lambda s: -s[2])
    lines: list[list[tuple]] = []
    for text, x, y, size in ordered:
        if lines and abs(lines[-1][0][1] - y) <= 2.5:
            lines[-1].append((x, y, size, text))
        else:
            lines.append([(x, y, size, text)])

    overlay = None
    buf = io.BytesIO()
    pw = float(page.mediabox.width)
    ph = float(page.mediabox.height)

    for group in lines:
        group.sort(key=lambda s: s[0])
        parts = []
        prev_end = None
        for x, _y, size, text in group:
            needs_space = (prev_end is not None and (x - prev_end) > size * 0.28
                           and parts and not parts[-1].endswith(" ")
                           and not text.startswith(" "))
            if needs_space:
                parts.append(" ")
            parts.append(text)
            prev_end = x + len(text) * size * 0.5
        full = "".join(parts)
        new = full
        for old, repl in FILLS:
            if old in new:
                new = new.replace(old, repl)
        for key, vals in rules:
            if key in full:
                queue = list(vals)

                def qsub(_m, _q=queue):
                    return _q.pop(0) if _q else "n/a"

                new = re.sub("\u27e8TBD[^\u27e9]*\u27e9", qsub, new)
                new = re.sub("\u27e8todo[^\u27e9]*\u27e9", qsub, new)
                break
        if PLACEHOLDER.search(full):
            stats["placeholder_lines"] += 1
        remaining = PLACEHOLDER.findall(new)
        if remaining:
            stats["unfilled"].append((pno + 1, remaining, full[:70]))
        if new != full:
            stats["redrawn"] += 1
            if overlay is None:
                overlay = canvas.Canvas(buf, pagesize=(pw, ph))
            size = max(s[2] for s in group)
            x0 = group[0][0]
            x1 = group[-1][0] + len(group[-1][3]) * group[-1][2] * 0.6
            ybase = group[0][1]
            overlay.setFillColorRGB(1, 1, 1)
            overlay.rect(x0 - 2, ybase - size * 0.3, (x1 - x0) + 4, size * 1.45, fill=1, stroke=0)
            overlay.setFillColorRGB(0, 0, 0)
            overlay.setFont("Helvetica", size)
            overlay.drawString(x0, ybase, new)
    if overlay is not None:
        overlay.showPage()
        overlay.save()
        buf.seek(0)
        page.merge_page(PdfReader(buf).pages[0])
    writer.add_page(page)

if rows:
    buf2 = io.BytesIO()
    pw, ph = 595.0, 842.0
    c = canvas.Canvas(buf2, pagesize=(pw, ph))
    y = ph - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, "Best Combination - ME2 full-pipeline batch (2026-10-24)")
    y -= 16
    b = rows[0]
    n_ranked = int(data.get("jobs") or 0) or n_takes
    c.setFont("Helvetica", 9)
    sub = (f"{n_ranked} takes x 13 Gate 1 x 55 Gate 2 x raw x arch v1+v2 | winner: "
           f"{b['g1']} x {b['g2']} x {'nc' if b['nc'] else 'raw'} x v{b['arch'] + 1}: "
           f"full {b['full_ok']}/{b['full_j']} ({num(100 * max(b['rate'], 0))}%), "
           f"action {num(100 * max(b['act'], 0))}%, wake {num(100 * max(b['wake'], 0))}%, "
           f"OOS reject {num(100 * max(b.get('oos_rej', -1), 0))}%, p95 {num(b.get('p95', -1))} ms")
    line = ""
    for word in sub.split(" "):
        if len(line) + len(word) > 95:
            c.drawString(40, y, line)
            y -= 12
            line = word
        else:
            line = (line + " " + word).strip()
    c.drawString(40, y, line)
    y -= 22
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Demo setup (Pipeline test window):")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawString(48, y, f"Gate 1 variant = {b['g1']}   Gate 2 model = {b['g2']}   Architecture = v{b['arch'] + 1}   NC = raw")
    y -= 22
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Top combinations (ranked by fully-correct rate):")
    y -= 14
    cols = [("#", 40), ("G1", 58), ("G2", 122), ("nc", 232), ("arch", 262), ("full", 297),
            ("rate", 336), ("act", 375), ("wake", 414), ("oosrej", 453), ("ms", 492), ("p95", 526)]
    c.setFont("Helvetica-Bold", 8)
    for name, x in cols:
        c.drawString(x, y, name)
    y -= 11
    c.setFont("Helvetica", 8)
    for i, r in enumerate(rows[:18], 1):
        cells = [str(i), r["g1"].replace("gate1", ""), r["g2"].replace("gate2", ""),
                 "nc" if r["nc"] else "raw", "v" + str(r["arch"] + 1),
                 f"{r['full_ok']}/{r['full_j']}", num(100 * max(r['rate'], 0)) + "%",
                 num(100 * max(r['act'], 0)) + "%", num(100 * max(r['wake'], 0)) + "%",
                 num(100 * max(r.get('oos_rej', -1), 0)) + "%", num(r['ms']), num(r.get('p95', -1))]
        for (_name, x), cell in zip(cols, cells, strict=True):
            c.drawString(x, y, cell[:22])
        y -= 11
        if y < 90:
            break
    y -= 14
    c.setFont("Helvetica", 8)
    c.drawString(40, y, "Sources: recordings/results (2026-10-24 batch) | ME2 holdout 202 clips (86 real + 100 synth + 16 OOS) | owner takes.")
    c.showPage()
    c.save()
    buf2.seek(0)
    for pg in PdfReader(buf2).pages:
        writer.add_page(pg)

with open(DST, "wb") as f:
    writer.write(f)
print("filled:", DST.name)
print("stats:", {k: v for k, v in stats.items() if k != "unfilled"}, "| unfilled:", len(stats["unfilled"]))
for p, rem, ctx in stats["unfilled"][:8]:
    safe = " ".join(rem).encode("ascii", "backslashreplace").decode("ascii")
    print("  unfilled p", p, safe, "|", ctx.encode("ascii", "backslashreplace").decode("ascii")[:70])
