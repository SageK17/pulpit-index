#!/usr/bin/env python3
"""App icons for the installable web app: a serif P on ink, with a rose-red rule (the site's liturgical red)."""
from PIL import Image, ImageDraw, ImageFont
import os
HERE = os.path.dirname(os.path.abspath(__file__))
INK, PAPER, RED = (20, 20, 23), (245, 245, 242), (179, 34, 61)
FONT = "/System/Library/Fonts/Supplemental/Georgia.ttf"

def icon(size, pad_ratio=0.0):
    im = Image.new("RGB", (size, size), INK)
    d = ImageDraw.Draw(im)
    inner = size * (1 - 2 * pad_ratio)
    f = ImageFont.truetype(FONT, int(inner * 0.62))
    box = d.textbbox((0, 0), "P", font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    x = (size - w) / 2 - box[0]
    y = (size - h) / 2 - box[1] - inner * 0.04
    d.text((x, y), "P", font=f, fill=PAPER)
    rw, rh = inner * 0.30, max(2, inner * 0.035)
    ry = y + box[1] + h + inner * 0.07
    d.rounded_rectangle([(size - rw) / 2, ry, (size + rw) / 2, ry + rh], radius=rh / 2, fill=RED)
    return im

out = os.path.join(HERE, "icons")
icon(512).save(os.path.join(out, "icon-512.png"))
icon(192).save(os.path.join(out, "icon-192.png"))
icon(180).save(os.path.join(out, "apple-touch-icon.png"))
icon(512, pad_ratio=0.12).save(os.path.join(out, "icon-maskable-512.png"))
print("icons written")
