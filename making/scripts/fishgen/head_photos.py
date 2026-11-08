"""頭の写真（public/fish/<名前>_head.webp と <名前>_cover.webp）を、refs/fish/ の写真から作る。
<名前>_gills.webp：えらぶたを切り取って中のえらが見える写真（口は閉じている）。背景（#2d2d2e 前後）を透明にして頭のまわりを切り出す。
<名前>_cover.png：切り取ったえらぶただけの写真（ほかは透明）。
どちらも元の写真（<名前>.png、1672 × 941）とぴったり同じ位置・大きさで描いてあること。
box は写真の (x0, y0, x1, y1)。photo-fish.ts の HEAD_FILES の box（x, y, 幅, 高さ）と合わせる（新しい魚は head_rig.py apply が両方書く）。
python scripts/fishgen/head_photos.py suzuki
"""
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
BOXES = {"suzuki": (0, 296, 512, 616)}


def build(name):
    # 新しい魚は head_rig.py apply が書いた範囲（えらぶたと口のまわり）
    jb = os.path.join(ROOT, f"scripts/fishgen/logs/{name}_headbox.json")
    box = BOXES.get(name) or tuple(json.load(open(jb)))
    g = Image.open(os.path.join(ROOT, f"refs/fish/{name}_gills.webp")).convert("RGB")
    a = np.array(g).astype(float)
    bg = np.array([45, 45, 46.0])
    m = np.linalg.norm(a - bg, axis=-1) > 22
    lab, n = ndi.label(m)
    sizes = ndi.sum(m, lab, range(1, n + 1))
    m = lab == (1 + np.argmax(sizes))
    # 中の穴（瞳など、背景の色に近い暗い所）は埋める。シーバスの写真は前のまま
    if name != "suzuki":
        m = ndi.binary_fill_holes(m)
    m = ndi.binary_erosion(m, iterations=2)
    alpha = (ndi.gaussian_filter(m.astype(float), 1.0) * 255).astype(np.uint8)
    head = np.dstack([np.array(g), alpha])[box[1]:box[3], box[0]:box[2]]
    Image.fromarray(head, "RGBA").save(os.path.join(ROOT, f"public/fish/{name}_head.webp"), lossless=False, quality=90)
    cov = Image.open(os.path.join(ROOT, f"refs/fish/{name}_cover.png")).convert("RGBA").crop(box)
    cov.save(os.path.join(ROOT, f"public/fish/{name}_cover.webp"), lossless=False, quality=90)
    print(name, "ok")


for k in sys.argv[1:] or ["suzuki"]:
    build(k)
