"""Generate the VCM Pipeline Dashboard desktop icon (.ico) - dark tile, blue waveform, live dot."""
from PIL import Image, ImageDraw

OUT = r"C:\Users\Leandro\Desktop\Leandro\AI 222 and AI 231\Exercise 2\Exercise 2b\vcm_live_test_local\vcm_live_test_local\vcm_pipeline.ico"

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=52, fill=(13, 17, 23, 255))
d.rounded_rectangle([4, 4, S - 5, S - 5], radius=48, outline=(31, 111, 235, 255), width=7)
heights = [0.28, 0.5, 0.78, 1.0, 0.78, 0.5, 0.28]
bw, gap = 17, 11
total = len(heights) * bw + (len(heights) - 1) * gap
x0 = (S - total) // 2
cy = S // 2 + 6
for i, h in enumerate(heights):
    bh = max(14, int(h * 150))
    x = x0 + i * (bw + gap)
    y = cy - bh // 2
    shade = (88, 166, 255, 255) if i % 2 == 0 else (56, 139, 253, 255)
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=bw // 2, fill=shade)
d.ellipse([S - 66, 26, S - 26, 66], fill=(63, 185, 80, 255))
img.save(OUT, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)])
# pi-lens-ignore: Pyright:reportAttributeAccessIssue
print("saved:", OUT)
