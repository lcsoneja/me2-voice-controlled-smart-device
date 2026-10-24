"""Fill the required ME2 deck template for both models, preserving its exact format.

The template (me2-deck.pdf) is the required submission format: embedded subset fonts,
tinted diagram boxes, a two-page layout. Rebuilding it would change the format, and the
first overlay attempt garbled it because pypdf reports the same x for every span in a
placeholder run. So this edits the template in place: each value cell is redacted
(transparently - a filled redaction paints over the box tints) and the value drawn at the
original baseline in the original size where it fits.

One subtlety, learned the hard way: pymupdf pads line bounding boxes enough that the
neighbouring diagram line falls inside them, so a rect built from the line bbox clips the
row above. Redaction bands are therefore derived from the baseline and font size.

Values come from the corrected source of truth
(Shipping/ME2_Deck_Corrected_ship_20261024) and each model's own package reports.
Nothing is invented: unmeasured fields read "pending" or "n/a".
"""

import pathlib
from typing import Any, cast

import pymupdf  # resolved by the repo-local pymupdf.pyi stub; the real package is installed

HERE = pathlib.Path(__file__).resolve().parent
TEMPLATE = HERE / "me2-deck.pdf"

LEFT_RIGHT = 424.0   # left column must not cross into the right column at x = 428
COL_RIGHT = 815.0    # page right safe edge (page width 841.9)
STATUS_X = 703.0     # status column left edge in the template
MIN_SIZE = 9.5

# Verified against the installed PyMuPDF (reports version 2.0): both constants are 0,
# i.e. "do not remove images" / "do not remove line art" while redacting text.
KEEP_IMAGES = 0
KEEP_LINE_ART = 0

# The template's diagram says "KV-cache . streaming", but the corrected source records this
# model as stateless (20 s ring buffer, 6-frame scoring window, no KV-cache).
KV_TEXT = "ring buffer \u00b7 stateless"


# (label key, value-cell x or None for "replace the whole line", right limit, text)
def diagram_rows() -> list[tuple[str, float | None, float, str]]:
    # The Causal encoder row is replaced whole: its label (x0 48.7) shares space with the
    # row below, so a value-cell-only redaction would clip the label to "Causal e".
    return [("Mic", 262.1, LEFT_RIGHT, "148 \u00d7 60"),
            ("Causal encoder", None, LEFT_RIGHT, "Causal encoder \u00d7 3 \u00b7 64/128/256-dim"),
            ("KV-cache", None, LEFT_RIGHT, KV_TEXT)]


V64P = {
    "out": "me2-deck-v64p.pdf",
    "tag": "gate2v64p_paired_owner x gate1v3_f32",
    "page1": [("1 October 2026", 171.9, COL_RIGHT, "Leandro Soneja \u00b7 AI 231 ME2")]
             + diagram_rows()
             + [("Parameters / weights", 231.1, LEFT_RIGHT, "0.34 M \u00b7 0.70 MB"),
                ("Keyword / intent acc", 216.1, LEFT_RIGHT, "91.2% / 91.7%"),
                ("False-accept rate", 216.1, LEFT_RIGHT, "pending live test"),
                ("Latency p95 / RTF", 216.1, LEFT_RIGHT, "47.9 ms / 0.005"),
                ("Runtime", 216.1, LEFT_RIGHT, "TFLite f16 \u00b7 1 thread"),
                ("Source", 556.6, COL_RIGHT, "own TTS+owner corpus"),
                ("Hours / utts", 556.6, COL_RIGHT, "5.8 h / 8,730"),
                ("Speakers", 556.6, COL_RIGHT, "21 TTS + 1 owner"),
                ("Labels", 556.6, COL_RIGHT, "19 intents \u00b7 3 slots"),
                ("Cluster", 602.6, COL_RIGHT, "A100 \u00d78 shared, 1/run"),
                ("Objective", 602.6, COL_RIGHT, "CE, TC-ResNet 20-way"),
                ("Optimiser", 602.6, COL_RIGHT, "Adam + cosine"),
                ("Steps / loss", 602.6, COL_RIGHT, "3,687 \u00d7 15 / 0.02")],
    "links": [
        ("GitHub repository", "github.com/lcsoneja/me2-voice-controlled-smart-device"),
        ("Dataset location", "HF Drewboy/ai231-vcm-v64p-training-store (private, CC-BY-NC-4.0)"),
        ("A100 cluster", "8\u00d7 A100-SXM4-40GB shared; seed 42"),
        ("Model weights", "GitHub Release v1.0-me2 + TFLite f16 + SHA256SUMS"),
    ],
}

V20AUX = {
    "out": "me2-deck-v20aux.pdf",
    "tag": "gate2v20_aux x gate1v3_f32",
    "page1": [("1 October 2026", 171.9, COL_RIGHT, "Leandro Soneja \u00b7 AI 231 ME2")]
             + diagram_rows()
             + [("Parameters / weights", 231.1, LEFT_RIGHT, "0.25 M \u00b7 0.52 MB"),
                ("Keyword / intent acc", 216.1, LEFT_RIGHT, "90.7% / 93.7%"),
                ("False-accept rate", 216.1, LEFT_RIGHT, "pending live test"),
                ("Latency p95 / RTF", 216.1, LEFT_RIGHT, "30.7 ms / 0.003"),
                ("Runtime", 216.1, LEFT_RIGHT, "TFLite f16 \u00b7 1 thread"),
                ("Source", 556.6, COL_RIGHT, "own TTS corpus (V19)"),
                ("Hours / utts", 556.6, COL_RIGHT, "n/a h / 29,496"),
                ("Speakers", 556.6, COL_RIGHT, "21 TTS voices"),
                ("Labels", 556.6, COL_RIGHT, "19 intents \u00b7 3 slots"),
                ("Cluster", 602.6, COL_RIGHT, "A100 \u00d78 shared, 1/run"),
                ("Objective", 602.6, COL_RIGHT, "CE + 0.1\u00d7CTC aux"),
                ("Optimiser", 602.6, COL_RIGHT, "Adam + cosine"),
                ("Steps / loss", 602.6, COL_RIGHT, "n/a / val 98.84%")],
    "links": [
        ("GitHub repository", "github.com/lcsoneja/me2-voice-controlled-smart-device"),
        ("Dataset location", "HF Drewboy/ai231-vcm-v20aux-phoneme-store (private, CC-BY-NC-4.0)"),
        ("A100 cluster", "8\u00d7 A100-SXM4-40GB shared; seed 42"),
        ("Model weights", "GitHub Release v1.0-me2 + TFLite f16 + SHA256SUMS"),
    ],
}

# Checklist rows in visual order. The template's own status cells sit one row high, so they
# are cleared and re-placed on the rows they actually belong to.
CHECKLIST = [("Repo public", "done"),
             ("Dataset licensed", "done"),
             ("Training logs", "done"),
             ("Pi 4 latency", "pending"),
             ("Held-out test", "done"),
             ("Baseline of comparable", "done")]


def rows_of(page) -> list[dict[str, Any]]:
    data = cast("dict[str, Any]", page.get_text("dict"))
    out: list[dict[str, Any]] = []
    for block in data["blocks"]:
        for line in block.get("lines", []):
            out.append({"text": "".join(s["text"] for s in line["spans"]), "spans": line["spans"]})
    return out


def find_row(rows, key, used):
    for index, row in enumerate(rows):
        if index not in used and key in row["text"]:
            used.add(index)
            return row
    return None


def line_bounds(row):
    return (min(s["bbox"][0] for s in row["spans"]), min(s["bbox"][1] for s in row["spans"]),
            max(s["bbox"][3] for s in row["spans"]))


def anchor_span(row, value_x: float | None):
    ordered = sorted(row["spans"], key=lambda s: s["bbox"][0])
    if value_x is None:
        return ordered[0]
    for span in ordered:
        if span["bbox"][0] >= value_x - 2.0:
            return span
    return ordered[-1]


def queue(page, row, value_x, right, text, pending):
    """Redact this row's own text, then queue the value for its original baseline.

    The vertical band comes from the baseline and font size, not the line bbox: pymupdf
    pads line boxes so generously that a bbox-derived rect reaches into the line above and
    clips it (the template's diagram lines interpenetrate). `width` still uses the whole
    column so a long value is shrunk to fit instead of crossing into the next column.
    """
    xs0, _y0, _y1 = line_bounds(row)
    xmax = max(s["bbox"][2] for s in row["spans"])
    if value_x is None:
        x_start, x_end = xs0 - 0.5, xmax + 0.5
    else:
        x_start, x_end = value_x - 1.0, right
    anchor = anchor_span(row, value_x)
    size = float(anchor["size"])
    baseline = anchor["origin"][1]
    y_top = baseline - size * 0.75
    y_bot = baseline + size * 0.28
    page.add_redact_annot(pymupdf.Rect(x_start, y_top, x_end, y_bot), fill=None)
    pending.append({"x": x_start + 0.5, "baseline": baseline, "size": size,
                    "text": text, "width": right - x_start - 2.0})


def draw(page, pending):
    for item in pending:
        size = item["size"]
        while size > MIN_SIZE and pymupdf.get_text_length(
                item["text"], fontname="helv", fontsize=size) > item["width"]:
            size -= 0.5
        page.insert_text((item["x"], item["baseline"]), item["text"],
                         fontname="helv", fontsize=size, color=(0, 0, 0))


def build(spec):
    doc = pymupdf.open(str(TEMPLATE))
    for pno in (0, 1):
        page = doc[pno]
        rows = rows_of(page)
        used = set()
        pending = []
        if pno == 0:
            for key, value_x, right, text in spec["page1"]:
                row = find_row(rows, key, used)
                if row is None:
                    print("  MISS " + key)
                    continue
                queue(page, row, value_x, right, text, pending)
        else:
            for key, text in spec["links"]:
                row = find_row(rows, key, used)
                if row is None:
                    print("  MISS " + key)
                    continue
                queue(page, row, 234.7, COL_RIGHT, text, pending)
            todo = [r for r in rows if "todo" in r["text"]]
            if todo:
                band_x = min(line_bounds(r)[0] for r in todo) - 4.0
                band_y0 = min(line_bounds(r)[1] for r in todo) - 3.0
                band_y1 = max(line_bounds(r)[2] for r in todo) + 3.0
                page.add_redact_annot(pymupdf.Rect(band_x, band_y0, COL_RIGHT, band_y1), fill=None)
            for key, status in CHECKLIST:
                row = find_row(rows, key, set())
                if row is None:
                    print("  MISS checklist " + key)
                    continue
                anchor = anchor_span(row, None)
                size = float(anchor["size"])
                baseline = anchor["origin"][1]
                page.add_redact_annot(pymupdf.Rect(STATUS_X - 2.0, baseline - size * 0.75,
                                                  COL_RIGHT, baseline + size * 0.28), fill=None)
                pending.append({"x": STATUS_X, "baseline": baseline, "size": size,
                                "text": status, "width": COL_RIGHT - STATUS_X - 2.0})
        page.apply_redactions(images=KEEP_IMAGES, graphics=KEEP_LINE_ART)
        draw(page, pending)
    out = HERE / spec["out"]
    doc.set_metadata({"title": "ME2 \u2014 Voice Controlled Smart Device (" + spec["tag"] + ")",
                      "author": "Leandro Soneja \u2014 AI 231 ME2"})
    doc.save(str(out), garbage=3, deflate=True)
    doc.close()
    return out


def verify(path):
    doc = pymupdf.open(str(path))
    print("VERIFY " + path.name + " pages=" + str(doc.page_count))
    for pno in range(doc.page_count):
        page = doc[pno]
        text = page.get_text()
        leftover = [m for m in ("TBD", "fill:", "todo", "onnxruntime", "KV-cache", "DGX", "\u27e8")
                    if m in text]
        spans = [s for b in cast("dict[str, Any]", page.get_text("dict"))["blocks"]
                 for ln in b.get("lines", []) for s in ln["spans"]]
        overflow = [s["text"] for s in spans if s["bbox"][2] > 818]
        print("  p" + str(pno + 1) + " leftover=" + str(leftover)
              + " max_x=" + str(round(max((s["bbox"][2] for s in spans), default=0), 1))
              + " overflow=" + str(overflow[:3]))
    doc.close()


def main():
    for spec in (V64P, V20AUX):
        out = build(spec)
        print("WROTE " + out.name + " " + str(out.stat().st_size) + " bytes")
        verify(out)


if __name__ == "__main__":
    main()
