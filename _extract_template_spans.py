"""Dump every text span (text, x, y, font size, font name) of the required ME2 deck template.

Read-only: the template is the required submission format, so nothing is written to it.
"""

import json
import pathlib

from pypdf import PdfReader

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "me2-deck.pdf"
OUT = HERE / "_template_spans.json"


def main():
    reader = PdfReader(str(SRC))
    pages = []
    for index, page in enumerate(reader.pages):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        spans = []

        def collect(text, cm, tm, font_dict, font_size, _spans=spans):
            if not (text and text.strip()):
                return
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            fname = ""
            try:
                fname = str((font_dict or {}).get("/BaseFont", ""))
            except Exception:
                pass
            _spans.append({"y": round(y, 1), "x": round(x, 1),
                           "fs": round(float(font_size or 0.0), 1),
                           "font": fname, "t": text})

        page.extract_text(visitor_text=collect)
        ordered = sorted(spans, key=lambda s: (-s["y"], s["x"]))
        pages.append({"page": index + 1, "w": width, "h": height, "spans": ordered})

    OUT.write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding="utf-8")

    for pg in pages:
        print("== PAGE " + str(pg["page"]) + " " + str(int(pg["w"])) + "x" + str(int(pg["h"]))
              + " spans=" + str(len(pg["spans"])))
        for s in pg["spans"]:
            label = ascii(s["t"].strip())[:74]
            print("  y=" + str(s["y"]).ljust(6) + " x=" + str(s["x"]).ljust(7)
                  + " fs=" + str(s["fs"]).ljust(5) + (s["font"] or "-").ljust(20) + label)


if __name__ == "__main__":
    main()
