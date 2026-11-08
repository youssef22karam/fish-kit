"""新しい魚の頭（えらぶた・下あご・上あご）を作るための道具。README.md の「新しい魚の頭」の順に使う。

python scripts/fishgen/head_rig.py grid <名前>          頭に cm の目盛りを描いた画像（logs/<名前>_headgrid.png）と、Codex への質問（logs/<名前>_ask.txt）
python scripts/fishgen/head_rig.py answer <名前>        Codex の答えのログ（logs/<名前>_codex_head.log）から JSON を logs/<名前>_head.json に
python scripts/fishgen/head_rig.py apply <名前>         Codex の答え（logs/<名前>_head.json）から、えらぶたの範囲の画像（refs/fish/<名前>_gill_range.png）、
                                                        切り取ったえらぶた（refs/fish/<名前>_cover.png）、確かめる画像（logs/<名前>_headcheck.png）、
                                                        photo-fish.ts に書く形（logs/<名前>_head.ts）を作る
python scripts/fishgen/head_rig.py gills <名前>         Codex が描いたえらの見える写真（refs/fish/<名前>_gills_raw.png）を元の写真に合わせて、
                                                        えらぶたの範囲だけ元の写真に貼った refs/fish/<名前>_gills.webp を作る
python scripts/fishgen/head_rig.py pectgrid <名前>      胸びれのまわりの目盛りの画像と質問（ask_pects.sh が Codex に聞く）
python scripts/fishgen/head_rig.py pectapply <名前>     Codex の答えから胸びれの輪郭 refs/fish/<名前>_pect.json（fishgen.py が胸びれを切り抜く形）
python scripts/fishgen/head_rig.py eyeask / eyeapply <名前>  目の円を Codex に聞く質問と、答えから refs/fish/<名前>_eye.json（ask_eyes.sh）
python scripts/fishgen/head_rig.py ts <名前>            logs/<名前>_head.ts の形を photo-fish.ts に入れる

写真の画素と模型の対応は glb の extras.swim.photo = (x0, z0, k)：模型 x = (x0 − 画素 x) / k、模型 y = (z0 − 画素 y) / k。
"""
import json
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..")
REF = os.path.join(ROOT, "refs/fish")
LOG = os.path.join(HERE, "logs")
os.makedirs(LOG, exist_ok=True)

# 頭の範囲（口先から体長の何割まで）。細長い魚は頭が小さい
HEAD_FRAC = {"tachiuo": 0.14, "sawara": 0.26, "kamasu": 0.3, "hiramasa": 0.28, "buri": 0.28, "kihada": 0.28}
# 魚の名前（Codex に見せる）
NAMES = {
    "aji": "Japanese jack mackerel (maaji, Trachurus japonicus)",
    "saba": "chub mackerel (masaba, Scomber japonicus)",
    "tachiuo": "largehead hairtail (tachiuo, Trichiurus japonicus)",
    "sawara": "Japanese Spanish mackerel (sawara, Scomberomorus niphonius)",
    "kamasu": "Japanese barracuda (honkamasu, Sphyraena pinguis)",
    "buri": "Japanese amberjack (buri, Seriola quinqueradiata)",
    "hiramasa": "yellowtail amberjack (hiramasa, Seriola lalandi)",
    "kihada": "yellowfin tuna (kihada, Thunnus albacares)",
    "magochi": "bartail flathead (magochi, Platycephalus sp.)",
    "kurodai": "blackhead seabream (kurodai, Acanthopagrus schlegelii)",
    "madai": "red seabream (madai, Pagrus major)",
    "mebaru": "Japanese black rockfish (kuromebaru, Sebastes ventricosus)",
    "kasago": "marbled rockfish (kasago, Sebastiscus marmoratus)",
    "isaki": "chicken grunt (isaki, Parapristipoma trilineatum)",
    "isaki_young": "young chicken grunt with juvenile stripes (isaki, Parapristipoma trilineatum)",
    "onagagure": "largescale blackfish (onagagure / kuromejina, Girella leonina)",
    "kuchibuto": "opaleye (kuchibuto-gure / mejina, Girella punctata)",
    "shibudai": "star snapper (shibudai / fuedai, Lutjanus stellatus)",
}


def photo_map(name):
    """glb の extras.swim（写真の画素と模型の対応と、体長）"""
    b = open(os.path.join(ROOT, "public/fish", name + ".glb"), "rb").read()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    for node in j["nodes"]:
        sw = node.get("extras", {}).get("swim")
        if sw:
            return sw
    raise SystemExit("no swim extras in glb")


def fish_mask(img):
    a = np.asarray(img.convert("RGB")).astype(float)
    border = np.concatenate([a[:12].reshape(-1, 3), a[-12:].reshape(-1, 3), a[:, :12].reshape(-1, 3), a[:, -12:].reshape(-1, 3)])
    bg = np.median(border, 0)
    return np.linalg.norm(a - bg, axis=-1) > 22


def head_range(name):
    """頭の範囲（cm）：x0, x1, y0, y1"""
    sw = photo_map(name)
    x0, z0, k = sw["photo"]
    img = Image.open(os.path.join(REF, name + ".png"))
    m = fish_mask(img)
    cols = np.flatnonzero(m.sum(0) > 3)
    snout, tail = cols.min(), cols.max()
    head1 = snout + HEAD_FRAC.get(name, 0.33) * (tail - snout)
    # 上下はひれを消した写真で（ひれまで入れない）
    nof = os.path.join(REF, name + "_nofins.png")
    mb = fish_mask(Image.open(nof)) if os.path.exists(nof) else m
    rows = np.flatnonzero(mb[:, snout:int(head1)].sum(1) > 2)
    pad = 0.02 * (tail - snout)
    to_cm = lambda px, py: ((x0 - px) / k * 100, (z0 - py) / k * 100)
    cx1, cy1 = to_cm(snout - pad, rows.min() - pad)
    cx0, cy0 = to_cm(head1, rows.max() + pad)
    # 目盛りの線が 0.5cm の倍数に来るように
    return sw, (np.floor(cx0 * 2) / 2, np.ceil(cx1 * 2) / 2, np.floor(cy0 * 2) / 2, np.ceil(cy1 * 2) / 2)


def cmd_grid(name):
    sw, (cx0, cx1, cy0, cy1) = head_range(name)
    x0, z0, k = sw["photo"]
    wpx = (cx1 - cx0) / 100 * k
    sc = float(np.clip(1500 / wpx, 2, 8))
    out = os.path.join(LOG, f"{name}_headgrid.png")
    cmd = f'python "{os.path.join(HERE, "grid.py")}" "{os.path.join(REF, name + ".png")}" "{out}" {x0} {z0} {k} {cx0:.1f} {cx1:.1f} {cy0:.1f} {cy1:.1f} {sc:.2f}'
    os.system(cmd)
    L = sw["length"] * 100
    ask = open(os.path.join(HERE, "ask_head.txt"), encoding="utf-8").read()
    ask = ask.replace("{FISH}", NAMES[name]).replace("{LEN}", f"{L:.0f}").replace("{X0}", f"{cx0:.1f}").replace("{X1}", f"{cx1:.1f}")
    ask = ask.replace("{Y0}", f"{cy0:.1f}").replace("{Y1}", f"{cy1:.1f}")
    open(os.path.join(LOG, f"{name}_ask.txt"), "w", encoding="utf-8").write(ask)
    print(out, "range", round(cx0, 1), round(cx1, 1), round(cy0, 1), round(cy1, 1), "scale", round(sc, 2))


def load_answer(name):
    t = open(os.path.join(LOG, f"{name}_head.json"), encoding="utf-8").read()
    t = t[t.index("{"):t.rindex("}") + 1]
    return json.loads(t)


def resample(line, n):
    """折れ線を、長さに沿って n 点に"""
    p = np.asarray(line, float)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    s = np.linspace(0, d[-1], n)
    return np.stack([np.interp(s, d, p[:, 0]), np.interp(s, d, p[:, 1])], -1)


def resample_poly(poly, n):
    p = np.asarray(poly, float)
    return resample(np.vstack([p, p[:1]]), n + 1)[:-1]


def gill_lines(poly, n=39):
    """えらぶたの輪郭（閉じた多角形、cm）→ 下から上へ同じ高さで並べた、後ろの縁（いちばん小さい x）と前の縁（いちばん大きい x）"""
    p = np.asarray(poly, float)
    y0, y1 = p[:, 1].min(), p[:, 1].max()
    ys = np.linspace(y0 + 0.02, y1 - 0.02, n)
    edge, hinge = [], []
    for y in ys:
        xs = []
        for i in range(len(p)):
            a, b = p[i], p[(i + 1) % len(p)]
            if (a[1] - y) * (b[1] - y) <= 0 and a[1] != b[1]:
                xs.append(a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]))
        edge.append(min(xs))
        hinge.append(max(xs))
    return ys, np.array(edge), np.array(hinge), y0, y1


def cm_to_px(sw, pts):
    x0, z0, k = sw["photo"]
    p = np.asarray(pts, float)
    return np.stack([x0 - p[:, 0] / 100 * k, z0 - p[:, 1] / 100 * k], -1)


def fmt(pts):
    return "[" + ", ".join(f"[{x:.2f}, {y:.2f}]" for x, y in pts) + "]"


def cmd_apply(name):
    sw = photo_map(name)
    A = load_answer(name)
    L = sw["length"]
    src = Image.open(os.path.join(REF, name + ".png")).convert("RGB")
    W, H = src.size
    gpoly = cm_to_px(sw, A["gill_cover"])
    # えらぶたの範囲の画像（元の写真に、赤い線と薄い赤）
    rng = src.copy()
    ov = Image.new("RGBA", src.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.polygon([tuple(p) for p in gpoly], fill=(255, 0, 0, 80))
    d.line([tuple(p) for p in np.vstack([gpoly, gpoly[:1]])], fill=(255, 0, 0, 255), width=4, joint="curve")
    rng = Image.alpha_composite(rng.convert("RGBA"), ov).convert("RGB")
    rng.save(os.path.join(REF, f"{name}_gill_range.png"))
    # 切り取ったえらぶた（範囲の中は元の写真、外は透明）
    mask = Image.new("L", src.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in gpoly], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.8))
    cov = src.convert("RGBA")
    cov.putalpha(mask)
    cov.save(os.path.join(REF, f"{name}_cover.png"))
    # 確かめる画像（頭のまわり、3 倍）
    chk = src.copy()
    d = ImageDraw.Draw(chk)
    d.line([tuple(p) for p in np.vstack([gpoly, gpoly[:1]])], fill=(255, 0, 0), width=2)
    for key, col in (("lower_lip", (0, 255, 255)), ("under", (0, 255, 0))):
        d.line([tuple(p) for p in cm_to_px(sw, A[key])], fill=col, width=2)
    up = cm_to_px(sw, A["upper_jaw"])
    d.line([tuple(p) for p in np.vstack([up, up[:1]])], fill=(255, 255, 0), width=2)
    for key, col in (("jaw_joint", (255, 0, 255)), ("upper_pivot", (255, 128, 0))):
        x, y = cm_to_px(sw, [A[key]])[0]
        d.ellipse((x - 5, y - 5, x + 5, y + 5), outline=col, width=2)
    allp = np.vstack([gpoly, up, cm_to_px(sw, A["under"])])
    bx0, by0 = np.maximum(allp.min(0) - 40, 0)
    bx1, by1 = np.minimum(allp.max(0) + 40, [W, H])
    crop = chk.crop((int(bx0), int(by0), int(bx1), int(by1)))
    s = 1400 / crop.size[0]
    crop.resize((int(crop.size[0] * s), int(crop.size[1] * s)), Image.LANCZOS).save(os.path.join(LOG, f"{name}_headcheck.png"))

    # photo-fish.ts に書く形
    ys, edge, hinge, y0, y1 = gill_lines(A["gill_cover"])
    med = float(np.median(hinge))
    hinge = np.minimum(hinge, med + 3.3 * L)        # 下で前へ細くのびた所は止める（シーバスは中ほど + 体長の 3.3%）
    lip = resample(sorted(A["lower_lip"], key=lambda p: p[0]), 6)
    under = resample(sorted(A["under"], key=lambda p: p[0]), 7)
    upper = resample_poly(A["upper_jaw"], 20)
    # 上あごを出す角度は Codex の答えの半分（そのままだと、細い帯が口の中へ棒のように垂れて見える）
    # 口を閉じた写真なので、上あごの骨の縁は唇の線のすぐ上（体長の 0.25%）
    edge_line = lip + np.array([0, 0.25 * L])
    ts = f"""  {name}: {{
    edge: cmY({fmt(np.stack([edge, ys], -1))}),
    hinge: cmY({fmt(np.stack([hinge, ys], -1))}),
    top: {y1 / 100:.4f},
    bottom: {y0 / 100:.4f},
    pivotMax: {(med + 0.8 * L) / 100:.4f},
  }},
"""
    ts += f"""  {name}: {{
    joint: [{A['jaw_joint'][0] / 100:.4f}, {A['jaw_joint'][1] / 100:.4f}],
    close: 0,
    lowerLip: cm({fmt(lip)}),
    under: cm({fmt(under)}),
    jawEdge: cm({fmt(edge_line)}),
    upper: cm({fmt(upper)}),
    upperPivot: [{A['upper_pivot'][0] / 100:.4f}, {A['upper_pivot'][1] / 100:.4f}],
    upperClose: 0,
    upperOpen: {0.5 * float(A.get('upper_protrusion_deg') or 15) * np.pi / 180:.3f},
    photoClose: 0,
  }},
"""
    # 頭の写真を切り出す範囲（えらぶたと口のまわり）
    box = [int(max(bx0 - 20, 0)), int(max(by0 - 20, 0)), int(min(bx1 + 20, W)), int(min(by1 + 20, H))]
    ts += f"  {name}: {{ file: '{name}', box: [{box[0]}, {box[1]}, {box[2] - box[0]}, {box[3] - box[1]}] }},\n"
    json.dump(box, open(os.path.join(LOG, f"{name}_headbox.json"), "w"))
    open(os.path.join(LOG, f"{name}_head.ts"), "w", encoding="utf-8").write(ts)
    print(ts)


def align_shift(ref, img):
    la = np.asarray(ref.convert("L"), float)
    lb = np.asarray(img.convert("L"), float)
    la -= la.mean()
    lb -= lb.mean()
    F = np.fft.fft2(la) * np.conj(np.fft.fft2(lb))
    r = np.fft.ifft2(F / (np.abs(F) + 1e-9)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    H, W = la.shape
    dy = dy - H if dy > H // 2 else dy
    dx = dx - W if dx > W // 2 else dx
    return int(dx), int(dy)


def cmd_gills(name):
    sw = photo_map(name)
    A = load_answer(name)
    src = Image.open(os.path.join(REF, name + ".png")).convert("RGB")
    raw = Image.open(os.path.join(REF, f"{name}_gills_raw.png")).convert("RGB")
    if raw.size != src.size:
        raw = raw.resize(src.size, Image.LANCZOS)
    dx, dy = align_shift(src, raw)
    print("shift", dx, dy)
    if abs(dx) > 40 or abs(dy) > 40:
        raise SystemExit("too far off: regenerate")
    raw = Image.fromarray(np.roll(np.roll(np.asarray(raw), dy, 0), dx, 1))
    gpoly = cm_to_px(sw, A["gill_cover"])
    mask = Image.new("L", src.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in gpoly], fill=255)
    # 範囲の縁から 2 画素内側まで元の写真（縁の線を見せない）、少しぼかしてなじませる
    mask = mask.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.GaussianBlur(1.5))
    out = Image.composite(raw, src, mask)
    out.save(os.path.join(REF, f"{name}_gills.webp"), lossless=True)
    print("saved", name)


def cmd_answer(name):
    """Codex の答え（logs/<名前>_codex_head.log の最後の JSON）を logs/<名前>_head.json に"""
    t = open(os.path.join(LOG, f"{name}_codex_head.log"), encoding="utf-8", errors="replace").read()
    i = t.rindex('"gill_cover"')
    s = t.rindex("{", 0, i)
    e = t.index("}", t.index('"mouth_closed"', i)) + 1
    json.loads(t[s:e])
    open(os.path.join(LOG, f"{name}_head.json"), "w", encoding="utf-8").write(t[s:e])
    print("answer", name)


# 胸びれを探す範囲（口先から体長の何割〜何割）
PECT_FRAC = {"tachiuo": (0.07, 0.3), "kurodai": (0.14, 0.66), "madai": (0.14, 0.66), "mebaru": (0.14, 0.6), "kasago": (0.12, 0.6), "kihada": (0.14, 0.68)}


def cmd_pectgrid(name):
    """胸びれのまわりに目盛りを描いた画像（logs/<名前>_pectgrid.png）と質問（logs/<名前>_pectask.txt）"""
    sw = photo_map(name)
    x0, z0, k = sw["photo"]
    img = Image.open(os.path.join(REF, name + ".png"))
    m = fish_mask(img)
    cols = np.flatnonzero(m.sum(0) > 3)
    snout, tail = cols.min(), cols.max()
    f0, f1 = PECT_FRAC.get(name, (0.14, 0.46))
    a, b = int(snout + f0 * (tail - snout)), int(snout + f1 * (tail - snout))
    nof = os.path.join(REF, name + "_nofins.png")
    mb = fish_mask(Image.open(nof)) if os.path.exists(nof) else m
    rb = np.flatnonzero(mb[:, a:b].sum(1) > 2)
    rf = np.flatnonzero(m[:, a:b].sum(1) > 2)
    pad = 0.02 * (tail - snout)
    to_cm = lambda px, py: ((x0 - px) / k * 100, (z0 - py) / k * 100)
    cx1, cy1 = to_cm(a, rb.min() - pad)
    cx0, cy0 = to_cm(b, rf.max() + pad)
    cx0, cx1, cy0, cy1 = np.floor(cx0 * 2) / 2, np.ceil(cx1 * 2) / 2, np.floor(cy0 * 2) / 2, np.ceil(cy1 * 2) / 2
    sc = float(np.clip(1500 / ((cx1 - cx0) / 100 * k), 1.5, 8))
    out = os.path.join(LOG, f"{name}_pectgrid.png")
    os.system(f'python "{os.path.join(HERE, "grid.py")}" "{os.path.join(REF, name + ".png")}" "{out}" {x0} {z0} {k} {cx0:.1f} {cx1:.1f} {cy0:.1f} {cy1:.1f} {sc:.2f}')
    ask = open(os.path.join(HERE, "ask_pect.txt"), encoding="utf-8").read()
    ask = ask.replace("{FISH}", NAMES[name]).replace("{X0}", f"{cx0:.1f}").replace("{X1}", f"{cx1:.1f}").replace("{Y0}", f"{cy0:.1f}").replace("{Y1}", f"{cy1:.1f}")
    open(os.path.join(LOG, f"{name}_pectask.txt"), "w", encoding="utf-8").write(ask)


def cmd_pectapply(name):
    """Codex の答え（logs/<名前>_codex_pect.log）から、胸びれの輪郭（写真の画素）を refs/fish/<名前>_pect.json に。fishgen.py が使う。
    確かめる画像は logs/<名前>_pectcheck.png"""
    t = open(os.path.join(LOG, f"{name}_codex_pect.log"), encoding="utf-8", errors="replace").read()
    i = t.rindex('"pectoral"')
    s = t.rindex("{", 0, i)
    e = t.index("}", t.index('"found"', i)) + 1
    A = json.loads(t[s:e])
    if not A.get("found", True) or len(A["pectoral"]) < 6:
        print(name, "no pectoral")
        return
    sw = photo_map(name)
    poly = cm_to_px(sw, A["pectoral"])
    base = cm_to_px(sw, A["base"])
    json.dump({"poly": poly.round(1).tolist(), "base": base.round(1).tolist()}, open(os.path.join(REF, f"{name}_pect.json"), "w"))
    src = Image.open(os.path.join(REF, name + ".png")).convert("RGB")
    d = ImageDraw.Draw(src)
    d.line([tuple(p) for p in np.vstack([poly, poly[:1]])], fill=(255, 0, 0), width=2)
    d.line([tuple(p) for p in base], fill=(0, 255, 0), width=3)
    x0, y0 = np.maximum(poly.min(0) - 60, 0)
    x1, y1 = poly.max(0) + 60
    c = src.crop((int(x0), int(y0), int(x1), int(y1)))
    s = 900 / c.size[0]
    c.resize((int(c.size[0] * s), int(c.size[1] * s))).save(os.path.join(LOG, f"{name}_pectcheck.png"))
    print("pect", name, len(poly))


def cmd_eyeask(name):
    """目の質問（logs/<名前>_eyeask.txt）。目盛りの画像は頭の形と同じ logs/<名前>_headgrid.png"""
    _, (cx0, cx1, cy0, cy1) = head_range(name)
    ask = open(os.path.join(HERE, "ask_eye.txt"), encoding="utf-8").read()
    ask = ask.replace("{FISH}", NAMES[name]).replace("{X0}", f"{cx0:.1f}").replace("{X1}", f"{cx1:.1f}").replace("{Y0}", f"{cy0:.1f}").replace("{Y1}", f"{cy1:.1f}")
    open(os.path.join(LOG, f"{name}_eyeask.txt"), "w", encoding="utf-8").write(ask)


def cmd_eyeapply(name):
    """Codex の答え（logs/<名前>_codex_eye.log）から目の円（写真の画素）を refs/fish/<名前>_eye.json に。確かめる画像は logs/<名前>_eyecheck.png"""
    t = open(os.path.join(LOG, f"{name}_codex_eye.log"), encoding="utf-8", errors="replace").read()
    i = t.rindex('"center"')
    s = t.rindex("{", 0, i)
    e = t.index("}", t.index('"pupil_radius"', i)) + 1
    A = json.loads(t[s:e])
    sw = photo_map(name)
    (x, y), = cm_to_px(sw, [A["center"]])
    r = A["radius"] / 100 * sw["photo"][2]
    json.dump({"x": round(float(x), 1), "y": round(float(y), 1), "r": round(float(r), 1)}, open(os.path.join(REF, f"{name}_eye.json"), "w"))
    src = Image.open(os.path.join(REF, name + ".png")).convert("RGB")
    d = ImageDraw.Draw(src)
    d.ellipse((x - r, y - r, x + r, y + r), outline=(0, 255, 0), width=2)
    src.crop((int(x - 3 * r), int(y - 2.2 * r), int(x + 3 * r), int(y + 2.2 * r))).resize((300, 220)).save(os.path.join(LOG, f"{name}_eyecheck.png"))
    print("eye", name, round(float(x)), round(float(y)), round(float(r), 1))


def cmd_ts(name):
    """logs/<名前>_head.ts の 3 つの形を photo-fish.ts の GILLS・MOUTHS・HEAD_FILES に入れる（同じ名前があれば置きかえる）"""
    p = os.path.join(ROOT, "src/game/fish/photo-fish.ts")
    t = open(p, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in t else "\n"
    src = open(os.path.join(LOG, f"{name}_head.ts"), encoding="utf-8").read()
    blocks = [b for b in src.split(f"  {name}: {{")[1:]]
    tables = ["const GILLS: Record<string, GillShape> = {", "const MOUTHS: Record<string, MouthShape> = {", "const HEAD_FILES: Record<string, { file: string; box: [number, number, number, number] }> = {"]
    for head, body in zip(tables, blocks):
        entry = (f"  {name}: {{" + body.rstrip()).replace("\n", nl) + nl
        s = t.index(head) + len(head) + len(nl)
        e = t.index(nl + "};", s) + len(nl)
        table = t[s:e]
        key = f"  {name}: {{"
        if key in table:
            i = table.index(key)
            # その名前の項目の終わり（次の 2 字下げの項目か、表の終わり）
            j = i + len(key)
            depth = 1
            while depth:
                depth += {"{": 1, "}": -1}.get(table[j], 0)
                j += 1
            j = table.index(nl, j) + len(nl)
            table = table[:i] + entry + table[j:]
        else:
            table = table + entry
        t = t[:s] + table + t[e:]
    open(p, "w", encoding="utf-8", newline="").write(t)
    print("ts", name)


if __name__ == "__main__":
    {"grid": cmd_grid, "eyeask": cmd_eyeask, "eyeapply": cmd_eyeapply, "pectgrid": cmd_pectgrid, "pectapply": cmd_pectapply, "answer": cmd_answer, "apply": cmd_apply, "gills": cmd_gills, "ts": cmd_ts}[sys.argv[1]](sys.argv[2])
