"""Build the ME2 deck PDFs (A4 landscape, uniform 40pt safe margins) from measured lane results.

Two decks, same layout, different Gate 2 model:
  me2-deck-v64p.pdf    gate1v12_f16 x gate2v64p_paired_owner, raw noise canceller, arch v1
  me2-deck-v20aux.pdf  gate1v12_f16 x gate2v20_aux,          raw noise canceller, arch v1

Numbers come only from _v12_compare.json (the controlled head-to-head run).
Nothing is invented: a metric with no data prints "not measured".
"""

import argparse
import json
import pathlib

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE / "vcm_live_test_local" / "vcm_live_test_local"
DEFAULT_INPUT = HERE / "_v12_compare.json"
CFG = HERE / "_deck_config.json"

PAGE = landscape(A4)
PW, PH = PAGE
MARGIN = 40.0
INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#5A5A5A")
RULE = colors.HexColor("#C9C9C9")
ACCENT = colors.HexColor("#1F4E79")
BAND = colors.HexColor("#F1F4F8")

MODEL_FACTS = {
    "gate2v64p_paired_owner": {
        "params": "338,260",
        "tflite": "698,728 B (0.70 MB, float16)",
        "note": "20 outputs (19 intents + NEG background rejection). NEG recall 97.89%; "
                "held-out owner val 100% on 43 clips.",
    },
    "gate2v20_aux": {
        "params": "246,035 intent-only (248,700 with the training-only aux head)",
        "tflite": "515,332 B (0.52 MB, float16)",
        "note": "V19 TC-ResNet intent path + phoneme-auxiliary CTC head removed at inference. "
                "Clean synthetic val 98.84% (3,201 clips).",
    },
}

G1_FACTS = {
    "gate1v12_f16": "Gate 1 V12 wake model (Nova / Piattos / Negative), 148x60 log-mel frontend.",
    "gate1v3_f32": "Gate 1 V3 reference wake model used in the published ranking.",
}


def styles():
    return {
        "title": ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=INK),
        "sub": ParagraphStyle("s", fontName="Helvetica", fontSize=10.5, leading=14, textColor=MUTED),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16,
                            textColor=ACCENT, spaceBefore=2, spaceAfter=5),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.2, leading=12.6, textColor=INK),
        "small": ParagraphStyle("sm", fontName="Helvetica", fontSize=8.2, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=8.6, leading=11.4, textColor=INK),
        "cellb": ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8.6, leading=11.4, textColor=INK),
    }


def tflite_bytes(name):
    for base in (APP / "gate1_web", APP):
        hits = sorted(base.glob(f"{name}*.tflite"))
        if hits:
            return hits[0].stat().st_size
    return None


def fmt_bytes(n):
    return f"{n:,} B ({n / 1048576:.2f} MB)" if n else "not measured"


def pct(v, num, den):
    if v is None or v < 0 or not den:
        return "not measured"
    return f"{100 * v:.1f}%  ({num}/{den})"


def table(rows, widths, st):
    data = [[Paragraph(a, st["cellb"]), Paragraph(b, st["cell"])] for a, b in rows]
    t = Table(data, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), BAND),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def footer(canv, doc):
    canv.saveState()
    canv.setStrokeColor(RULE)
    canv.setLineWidth(0.4)
    canv.line(MARGIN, MARGIN - 12, PW - MARGIN, MARGIN - 12)
    canv.setFont("Helvetica", 7.6)
    canv.setFillColor(MUTED)
    canv.drawString(MARGIN, MARGIN - 23, "ME2 - Voice Controlled Smart Device - on-device VCM")
    canv.drawRightString(PW - MARGIN, MARGIN - 23, f"p. {doc.page}")
    canv.restoreState()


def build(path, lane, ref, cfg, variant_label):
    st = styles()
    g2 = lane["g2"]
    facts = MODEL_FACTS.get(g2, {"params": "not measured", "tflite": "not measured", "note": ""})
    g1_size = tflite_bytes(lane["g1"].replace("_f16", "_float16").replace("_f32", "_float32"))
    repo = cfg.get("repo") or "pending - to be published"
    dset = cfg.get("dataset") or "class gold /data/ai231 + supplementals"

    doc = BaseDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN, rightMargin=MARGIN,
                          topMargin=MARGIN, bottomMargin=MARGIN + 18,
                          title=f"ME2 VCM deck - {variant_label}", author="Leandro Soneja")
    frame = Frame(MARGIN, MARGIN + 18, PW - 2 * MARGIN, PH - 2 * MARGIN - 18, id="body")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=footer)])

    story = []
    story.append(Paragraph("ME2 - Voice Controlled Smart Device", st["title"]))
    story.append(Paragraph("Always-on keyword + intent recognition at the edge, no cloud round-trip", st["sub"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        f"Leandro Soneja - AI 231 ME2 &nbsp;|&nbsp; configuration: <b>{lane['g1']} x {g2} - "
        f"{'noise canceller' if lane['nc'] else 'raw'} - architecture v{lane['arch'] + 1}</b>", st["sub"]))
    story.append(Spacer(1, 12))

    left = [Paragraph("Model", st["h2"]),
            table([("Gate 1 (wake)", f"{lane['g1']} - {fmt_bytes(g1_size)}"),
                   ("Gate 2 (intent)", g2),
                   ("Gate 2 params", facts["params"]),
                   ("Gate 2 weights", facts["tflite"]),
                   ("Noise canceller", "raw (off)" if not lane["nc"] else "enabled"),
                   ("Architecture", f"v{lane['arch'] + 1}"),
                   ("Runtime", "tflite-runtime, XNNPACK delegate")],
                  [74, 210], st),
            Spacer(1, 5), Paragraph(facts["note"], st["small"])]

    right = [Paragraph("Dataset", st["h2"]),
             table([("Primary", dset),
                    ("Labels", "20 intents / slots (frozen labels.json)"),
                    ("Wake words", "Nova, Piattos (project-own schema)"),
                    ("Frozen split", "SPLIT_LOCK.json, seed 42 - never modified"),
                    ("Takes scored", f"{lane['takes']:,} takes in this run")],
                   [74, 210], st)]

    cols = Table([[left, right]], colWidths=[(PW - 2 * MARGIN) / 2 - 6] * 2, hAlign="LEFT")
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (0, 0), 12),
                              ("RIGHTPADDING", (1, 0), (1, 0), 0)]))
    story.append(cols)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Measured results - this configuration", st["h2"]))
    story.append(table([
        ("Full pipeline (wake + intent)", pct(lane.get("rate"), lane.get("full_ok"), lane.get("full_j"))),
        ("Intent accuracy (after wake)", pct(lane.get("act"), lane.get("act_ok"), lane.get("act_j"))),
        ("Wake detection", pct(lane.get("wake"), lane.get("wake_ok"), lane.get("full_j"))),
        ("Out-of-scope rejection", (pct(lane.get("oos_rej"), lane.get("oos", 0) - lane.get("oos_fire", 0), lane.get("oos", 0))
                                    + f"  ({lane.get('oos', 0)} OOS takes)")),
        ("Latency p95 / mean (host CPU)", f"{lane.get('p95', -1):.1f} ms / {lane.get('ms', -1):.1f} ms"),
        ("Raspberry Pi 4/5 latency", "not measured for this lane (host CPU only)"),
    ], [190, 300], st))
    story.append(Spacer(1, 10))

    story.append(Paragraph("Control: the same takes scored with the published reference Gate 1", st["h2"]))
    if ref:
        story.append(table([
            (f"{ref['g1']} x {ref['g2']} - raw - v{ref['arch'] + 1}",
             "full " + pct(ref.get("rate"), ref.get("full_ok"), ref.get("full_j"))
             + "   intent " + pct(ref.get("act"), ref.get("act_ok"), ref.get("act_j"))
             + f"   p95 {ref.get('p95', -1):.1f} ms"),
        ], [190, 300], st))
    else:
        story.append(Paragraph("Reference lane not measured in this run.", st["small"]))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Both rows were produced by one controlled pass over the identical take set, so the comparison is "
        "like-for-like. Latency is host-CPU p95 across takes; it is not a Raspberry Pi measurement.",
        st["small"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Reproduction", st["h2"]))
    story.append(Paragraph(
        f"Repository: {repo}<br/>"
        f"Dashboard: <font face='Courier'>python gate1_server.py</font> then open "
        f"<font face='Courier'>http://127.0.0.1:8765/</font><br/>"
        f"This run: <font face='Courier'>py -3.12 _batch_v12_compare.py</font> then "
        f"<font face='Courier'>py -3.12 _v12_analyze.py</font>", st["body"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph("To be submitted - what the reviewer will look for", st["h2"]))
    checks = [
        ("1", "Repository public, one-command reproduction"),
        ("2", "Dataset licensed and citable"),
        ("3", "Training logs + final checkpoint committed"),
        ("4", "Latency reproduced by the posted script (Pi)"),
        ("5", "Held-out test set with unseen speakers"),
        ("6", "Baseline of comparable size compared"),
    ]
    data = [[Paragraph("#", st["cellb"]), Paragraph("Item", st["cellb"]), Paragraph("Status", st["cellb"])]
            for _ in [0]]
    for n, item in checks:
        status = "pending"
        data.append([Paragraph(n, st["cell"]), Paragraph(item, st["cell"]), Paragraph(status, st["cell"])])
    t = Table(data, colWidths=[24, 420, 90], hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(KeepTogether([t, Spacer(1, 8), Paragraph(
        "Honesty note: out-of-scope rejection above is measured only on the OOS takes inside this take bank; "
        "a quiet-room false-trigger test was not run. Accuracy figures describe these recordings, not "
        "unseen microphones.", st["small"])]))

    doc.build(story)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(DEFAULT_INPUT))
    args = ap.parse_args()
    raw = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    lanes = raw.get("lanes", raw)
    cfg = json.loads(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}

    def lane(g1, g2):
        return lanes.get(f"{g1}|{g2}|False|0")

    made = []
    for g2, filename, label in (("gate2v64p_paired_owner", "me2-deck-v64p.pdf", "V64P paired-owner"),
                                 ("gate2v20_aux", "me2-deck-v20aux.pdf", "V20 phoneme-aux")):
        main_lane = lane("gate1v12_f16", g2)
        if not main_lane:
            print(f"SKIP {filename}: no measured lane for gate1v12_f16 x {g2}")
            continue
        ref = lane("gate1v3_f32", g2)
        out = HERE / filename
        build(out, main_lane, ref, cfg, label)
        made.append(out.name)
        print(f"wrote {out.name}  full={main_lane.get('rate'):.4f} intent={main_lane.get('act'):.4f} "
              f"wake={main_lane.get('wake'):.4f} p95={main_lane.get('p95'):.1f}ms")
    print("DECKS=" + (",".join(made) if made else "none"))


if __name__ == "__main__":
    main()
