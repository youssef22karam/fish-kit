"""Light real-time fish from two side photos.
(Species are listed in SPECIES.
 Run it through build.py, which stands in for a missing <id>_nofins.png.)
blender -b --factory-startup -P fishgen.py -- <species id> [<species id> ...]

Inputs per species (refs/fish/):  <id>.png         side view, fins spread, flat dark backdrop, head LEFT
                                  <id>_nofins.png  the same photo with every fin removed (Codex edit)
- body outline   = mask of the fins-removed photo; loft of 56 stations x 40 ring vertices, no subdivision
- median fins    = (fish mask - body mask) components -> flat sheets in the mid plane, empty cells culled;
                   their shape comes from the photo's alpha
- pectoral fin   = where the two photos differ inside the body -> a sheet on each flank, hinged at its base
- eyes           = darkest blob in the head -> low-poly sphere textured with the photographed eye
- one 1024x640 WebP atlas (body skin 400 rows on top, fins packed in the 240 rows below)
- per-vertex _FIN (part, weight, 0) / _PIV (hinge) + node extras 'swim' for the viewer's vertex shader
Writes public/fish/<id>.glb and prints stats as JSON."""
import bpy
import bmesh
import json
import math
import os
import sys
from collections import deque
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")).replace("\\", "/") + "/"
REF = ROOT + "refs/fish/"
OUT = ROOT + "public/fish/"
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"), exist_ok=True)
AW, AH, FIN_ROWS = 1024, 640, 240
# far LOD: coarse body loft, coarse fin sheets, tiny eyes. FISH_LOD=1 -> _lo, 2 -> _lo2 (lighter), 3 -> _lo3 (lightest; trial)
LOD_LEVEL = int(os.environ.get("FISH_LOD") or 0)
LOD = LOD_LEVEL >= 1
# level: (body stations, body rings, fin cells along the body, eye u, eye v)
LOD_PARAMS = {0: (56, 40, 22, 12, 8), 1: (20, 14, 9, 6, 4), 2: (13, 10, 6, 5, 3), 3: (9, 8, 4, 4, 3)}[LOD_LEVEL]
LOD_SUFFIX = {0: "", 1: "_lo", 2: "_lo2", 3: "_lo3"}[LOD_LEVEL]
BODY_V0 = FIN_ROWS / AH
# ひれの四角どうし・アトラスの縁・体の所との間。狭いと、遠くで使う小さな mipmap で隣のひれの縁がにじみ、板の端に縦の線が出る
PAD = 16

# length (m), half-thickness / half-depth ratio, swim: wavelength (body lengths), tail-beat Hz,
# amplitude scale, envelope A(s) = c0 + c1 s + c2 s^2 (s = 0 snout .. 1 tail)
SPECIES = {
    "isaki":   dict(name="イサキ", length=0.35, width=0.48, swim=dict(lam=0.95, freq=1.8, amp=0.75, env=[0.02, -0.08, 0.16])),
    # 小さいイサキ（28cm まで）：縞のある幼魚の写真から
    "isaki_young": dict(name="イサキ（幼魚）", length=0.25, width=0.48, swim=dict(lam=0.95, freq=1.8, amp=0.75, env=[0.02, -0.08, 0.16])),
    "tachiuo": dict(name="タチウオ", length=1.00, width=0.22, fin_rows=6, swim=dict(lam=0.55, freq=1.1, amp=0.5, env=[0.04, 0.0, 0.04])),
    "suzuki":  dict(name="シーバス", length=0.60, width=0.52, swim=dict(lam=0.95, freq=1.4, amp=0.75, env=[0.02, -0.08, 0.16])),
    "hirame":  dict(name="ヒラメ", length=0.60, width=0.16, flat=True, swim=dict(lam=0.75, freq=1.0, amp=0.55, env=[0.03, -0.04, 0.11])),
    "kamasu":  dict(name="カマス", length=0.35, width=0.85, swim=dict(lam=1.0, freq=2.0, amp=0.7, env=[0.015, -0.07, 0.16])),
    "buri":    dict(name="ブリ", length=0.80, width=0.62, swim=dict(lam=1.1, freq=1.4, amp=0.7, env=[0.01, -0.06, 0.15])),
    "aji":     dict(name="アジ", length=0.25, width=0.50, swim=dict(lam=1.0, freq=2.4, amp=0.75, env=[0.015, -0.07, 0.16])),
    "saba":    dict(name="サバ", length=0.35, width=0.72, swim=dict(lam=1.0, freq=2.2, amp=0.72, env=[0.01, -0.06, 0.15])),
    "mebaru":  dict(name="メバル", length=0.22, width=0.5, swim=dict(lam=0.95, freq=1.8, amp=0.7, env=[0.02, -0.08, 0.16])),
    "kasago":  dict(name="カサゴ", length=0.22, width=0.62, swim=dict(lam=0.9, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "sawara":  dict(name="サワラ", length=0.80, width=0.62, swim=dict(lam=1.05, freq=1.5, amp=0.7, env=[0.01, -0.06, 0.15])),
    "hiramasa": dict(name="ヒラマサ", length=0.90, width=0.58, pect_up=0.019, swim=dict(lam=1.1, freq=1.4, amp=0.7, env=[0.01, -0.06, 0.15])),
    "magochi": dict(name="マゴチ", length=0.45, width=1.25, solid_fins=True, swim=dict(lam=0.85, freq=1.3, amp=0.65, env=[0.03, -0.06, 0.14])),
    "kurodai": dict(name="クロダイ", length=0.40, width=0.42, swim=dict(lam=0.95, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "madai":   dict(name="マダイ", length=0.45, width=0.40, swim=dict(lam=0.95, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "kihada":  dict(name="キハダ", length=1.00, width=0.70, solid_fins=True, loose_mask=True, finlets=True, swim=dict(lam=1.2, freq=1.6, amp=0.6, env=[0.005, -0.04, 0.14])),
    "onagagure": dict(name="尾長グレ", length=0.45, width=0.42, tail_thin=0.85, tail_overlap=8, swim=dict(lam=0.95, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "kuchibuto": dict(tight_body=True, name="口太グレ", length=0.40, width=0.42, tail_thin=0.85, tail_overlap=8, solid_fins=True, loose_mask=True, swim=dict(lam=0.95, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "shibudai": dict(name="シブダイ", length=0.40, width=0.45, tail_overlap=8, swim=dict(lam=0.95, freq=1.6, amp=0.7, env=[0.02, -0.08, 0.16])),
    "katakuchi": dict(name="カタクチイワシ", length=0.13, width=0.75, swim=dict(lam=1.0, freq=3.0, amp=0.72, env=[0.015, -0.07, 0.16])),
}


# ---------------- image helpers ----------------

def load_rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1, :, :3].copy()   # top row first
    bpy.data.images.remove(img)
    return a


def box_blur(a, r):
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r + 1, r)
        c = np.cumsum(np.pad(out, pad, mode="edge"), axis=axis, dtype=np.float64)
        n = out.shape[axis]
        out = ((np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis) - np.take(c, np.arange(n), axis=axis))
               / (2 * r + 1)).astype(np.float32)
    return out


def dilate(m, r):
    return box_blur(m.astype(np.float32), r) > 1e-3


def erode(m, r):
    return box_blur(m.astype(np.float32), r) > 0.999


def ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def to_lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def bilinear(a, x, y):
    h, w = a.shape[:2]
    x = np.clip(x, 0, w - 1.001); y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
    fx = x - x0; fy = y - y0
    if a.ndim == 3:
        fx = fx[..., None]; fy = fy[..., None]
    return ((a[y0, x0] * (1 - fx) + a[y0, x0 + 1] * fx) * (1 - fy)
            + (a[y0 + 1, x0] * (1 - fx) + a[y0 + 1, x0 + 1] * fx) * fy)


def components(mask, step=2):
    """Connected components (4-neighbour) on a downsampled mask. Returns list of full-res boolean masks,
    largest first."""
    m = mask[::step, ::step]
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    flat = m.ravel()
    labf = lab.ravel()
    n = 0
    sizes = []
    for start in np.flatnonzero(flat):
        if labf[start]:
            continue
        n += 1
        q = deque([start]); labf[start] = n; cnt = 0
        while q:
            p = q.popleft(); cnt += 1
            y, x = divmod(p, w)
            for nb in ((p - w) if y > 0 else -1, (p + w) if y < h - 1 else -1, (p - 1) if x > 0 else -1,
                       (p + 1) if x < w - 1 else -1):
                if nb >= 0 and flat[nb] and not labf[nb]:
                    labf[nb] = n; q.append(nb)
        sizes.append(cnt)
    order = np.argsort(sizes)[::-1]
    out = []
    for k in order:
        small = lab == (k + 1)
        full = np.repeat(np.repeat(small, step, 0), step, 1)[:mask.shape[0], :mask.shape[1]] & mask
        out.append(full)
    return out


def align(ref, img):
    """Match size and integer translation of the edited photo to the original (phase correlation)."""
    H, W = ref.shape[:2]
    out = np.zeros_like(ref)
    h, w = min(H, img.shape[0]), min(W, img.shape[1])
    out[:h, :w] = img[:h, :w]
    if h < H:
        out[h:] = out[h - 1:h]
    if w < W:
        out[:, w:] = out[:, w - 1:w]
    la = ref @ np.array([0.3, 0.59, 0.11], np.float32); lb = out @ np.array([0.3, 0.59, 0.11], np.float32)
    la = la - la.mean(); lb = lb - lb.mean()
    Fc = np.fft.fft2(la) * np.conj(np.fft.fft2(lb))
    r = np.fft.ifft2(Fc / (np.abs(Fc) + 1e-9)).real
    dy, dx = np.unravel_index(np.argmax(r), r.shape)
    dy = dy - H if dy > H // 2 else dy
    dx = dx - W if dx > W // 2 else dx
    if abs(dy) <= 12 and abs(dx) <= 12 and (dy or dx):
        out = np.roll(np.roll(out, dy, 0), dx, 1)
    print("align shift", dy, dx)
    return out


def enclosed(m):
    """m に囲まれた穴（m の外で、m の入る箱の縁から m を通らずに行けない所）"""
    ys, xs = np.nonzero(m)
    if not len(ys):
        return np.zeros_like(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = m[y0:y1, x0:x1]
    out = np.zeros_like(sub)
    out[0, :] = ~sub[0, :]
    out[-1, :] = ~sub[-1, :]
    out[:, 0] |= ~sub[:, 0]
    out[:, -1] |= ~sub[:, -1]
    while True:
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        grown &= ~sub
        if (grown == out).all():
            break
        out = grown
    h = np.zeros_like(m)
    h[y0:y1, x0:x1] = ~sub & ~out
    return h


def poly_mask(poly, shape):
    """多角形（画素の (x, y)）の中の画素"""
    H, W = shape
    p = np.asarray(poly, float)
    m = np.zeros(shape, bool)
    q = np.roll(p, -1, 0)
    for y in range(max(0, int(p[:, 1].min())), min(H, int(p[:, 1].max()) + 1)):
        yc = y + 0.5
        cross = (p[:, 1] <= yc) != (q[:, 1] <= yc)
        if not cross.any():
            continue
        a, b = p[cross], q[cross]
        xs = np.sort(a[:, 0] + (yc - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1]))
        for x0, x1 in zip(xs[0::2], xs[1::2]):
            m[y, max(0, int(np.ceil(x0 - 0.5))):min(W, int(np.floor(x1 - 0.5)) + 1)] = True
    return m


# ---------------- analysis ----------------

class Fish:
    def __init__(self, sid):
        self.sid = sid
        self.cfg = SPECIES[sid]
        self.src = load_rgb(REF + sid + ".png")
        self.nof = load_rgb(REF + sid + "_nofins.png")
        self.nof = align(self.src, self.nof)
        H, W = self.src.shape[:2]
        self.H, self.W = H, W
        border = np.concatenate([self.src[:12].reshape(-1, 3), self.src[-12:].reshape(-1, 3),
                                 self.src[:, :12].reshape(-1, 3), self.src[:, -12:].reshape(-1, 3)])
        self.bg = np.median(border, 0)
        self.fish = self._mask(self.src)
        # tight_body（体の黒いグレ）：ゆるい切り抜きは魚の形だけ。体の形（ひれを消した写真）に使うと、消し残りのうっすらした
        # ひれまで体になり、体とひれの境目がぎざぎざになる。体は普通に切り抜いて、中の穴（背景の色に近い黒いうろこ）を埋める
        self.body = self._mask(self.nof, loose=not self.cfg.get("tight_body"))
        # body must lie inside the fish silhouette
        self.body &= dilate(self.fish, 3)
        comps = components(self.body)
        # 体の中の小さな穴（背景の色に近いつやなど）は埋める（尾長グレの背中のつや）
        self.body = comps[0] | enclosed(comps[0])
        # 体の中は魚（背景に近いつやで魚の形に穴があいても、透けないように）
        self.fish = self.fish | self.body
        self._profile()
        self._fins()
        self._eyes()

    def _mask(self, img, loose=True):
        diff = np.linalg.norm(img - self.bg, axis=-1)
        mx, mn = img.max(-1), img.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-4)
        a = np.maximum(ss(0.05, 0.12, diff), ss(0.12, 0.25, sat) * ss(0.04, 0.08, diff))
        m = box_blur(a, 2) > 0.5
        if self.cfg.get("tight_body") and not loose:
            # 体の輪郭（いちばん上と下の画素）は正しく取れるので、列ごとに上から下までを体にする（背中の黒い所の穴が、
            # 輪郭につながっていても埋まる）
            # 背中の黒い所が輪郭まで届いて抜けた列は、上の端が体の中へ下がる。上と下の端を、下がった（上がった）所を外れとして
            # 除きながら、なめらかな曲線に当てはめる
            m = components(m)[0]
            cols = np.flatnonzero(m.any(0))
            x0, x1 = int(cols.min()), int(cols.max())
            xs = np.arange(x0, x1 + 1)
            top = np.array([np.flatnonzero(m[:, x])[0] if m[:, x].any() else np.nan for x in xs], float)
            bot = np.array([np.flatnonzero(m[:, x])[-1] if m[:, x].any() else np.nan for x in xs], float)
            u = (xs - x0) / max(1, x1 - x0)

            def fit(e, inward):
                ok = ~np.isnan(e)
                w = ok.astype(float)
                e0 = np.where(ok, e, 0)
                for _ in range(14):
                    c = np.polyfit(u, e0, 9, w=w + 1e-9)
                    f = np.polyval(c, u)
                    w = (ok & ((e0 - f) * inward < 2.5)).astype(float)
                return np.polyval(c, u)

            ft = fit(top, 1)
            fb = fit(bot, -1)
            yy = np.arange(m.shape[0])[:, None]
            out = np.zeros_like(m)
            out[:, x0:x1 + 1] = (yy >= ft[None, :] - 0.5) & (yy <= fb[None, :] + 0.5)
            return out | m
        if self.cfg.get("loose_mask") and loose:
            # 背景の色に近い黒っぽいひれ（キハダの尾びれ・小離鰭の黒い縁）：5 画素ぼかして、背景との差が 4.5/255 より大きい所も魚に
            # （Codex の写真の背景は無地で、ぼかすと差は 2/255 もない）
            loose = np.linalg.norm(box_blur(img, 2) - self.bg, axis=-1) > 4.5 / 255
            m |= erode(dilate(loose, 3), 3)
            m = components(m)[0]
            return m | enclosed(m)
        return components(m)[0]

    def _profile(self):
        cols = np.flatnonzero(self.body.any(0))
        self.XF, self.XB = float(cols.min()), float(cols.max())
        xs = np.arange(int(self.XF), int(self.XB) + 1)
        top = np.array([np.flatnonzero(self.body[:, x])[0] for x in xs], float)
        bot = np.array([np.flatnonzero(self.body[:, x])[-1] for x in xs], float)
        k = 7
        ker = np.ones(2 * k + 1) / (2 * k + 1)
        pt = np.pad(top, k, mode="edge"); pb = np.pad(bot, k, mode="edge")
        top = np.convolve(pt, ker, "valid"); bot = np.convolve(pb, ker, "valid")
        # body_inset（明るい背景で撮った魚）：体のふちの画素には背景の明るい色が混ざって、ふちと尾の付け根の切り口が白い線に光る。
        # 体の形をふちから少し内側で作る
        ins = float(self.cfg.get("body_inset", 0))
        if ins:
            top = top + ins
            bot = bot - ins
            self.XB -= ins
        bot = np.maximum(bot, top + 2)
        self._xs, self._top, self._bot = xs.astype(float), top, bot
        fc = np.flatnonzero(self.fish.any(0))
        self.snout_px, self.tail_px = float(fc.min()), float(fc.max())
        self.S = self.cfg["length"] / (self.tail_px - self.snout_px)
        self.X0 = (self.snout_px + self.tail_px) / 2
        self.Z0 = float(np.mean((top + bot) / 2))
        self.width = self.cfg["width"]
        self.flat = bool(self.cfg.get("flat"))

    def TOP(self, x):
        return np.interp(x, self._xs, self._top)

    def BOT(self, x):
        return np.interp(x, self._xs, self._bot)

    def HW(self, x):
        d = (self.BOT(x) - self.TOP(x)) / 2
        u = (np.asarray(x, float) - self.XF) / (self.XB - self.XF)
        # round the snout and the peduncle a little thinner than the depth would say
        taper = ss(0.0, 0.08, u) * 0.7 + 0.3
        taper = taper * (1 - 0.35 * ss(0.8, 1.0, u))
        # tail_thin（尾の付け根の太い魚。グレ）：体の後ろの端を、本物より薄く尾びれの板へ向かってすぼめる。
        # 太いまま切ると、切り口の面に光が当たって白く光り、尾びれとのつなぎ目に見える
        thin = float(self.cfg.get("tail_thin", 0))
        if thin:
            taper = taper * (1 - thin * ss(0.86, 1.0, u))
        return np.maximum(d * self.width * taper, 0.8)

    def section(self, x, t):
        x = np.asarray(x, float); t = np.asarray(t, float)
        top, bot, hw = self.TOP(x), self.BOT(x), self.HW(x)
        p, q = (0.5, 0.5) if self.flat else (0.45, 0.7)
        v = np.cos(t)
        vs = (p - q) / (p + q)
        norm = (1 + vs) ** p * (1 - vs) ** q
        shape = np.clip(1 + v, 0, 2) ** p * np.clip(1 - v, 0, 2) ** q / norm
        yp = bot + (top - bot) * (1 + v) / 2
        return yp, np.sign(np.sin(t)) * hw * shape

    def surface_y(self, x, y):
        top, bot = self.TOP(x), self.BOT(x)
        v = np.clip(2 * (y - bot) / (top - bot) - 1, -1, 1)
        _, side = self.section(x, np.arccos(v))
        return np.abs(side) * self.S

    def to_m(self, x, y):
        return (self.X0 - np.asarray(x, float)) * self.S, (self.Z0 - np.asarray(y, float)) * self.S

    def _fins(self):
        fin = self.fish & ~dilate(self.body, 2)
        area = self.fish.sum()
        # 体の輪郭のすぐ外の細い帯（輪郭の暗いふち）は、ひれではない。尾の付け根や喉で輪郭が急に曲がる所では、
        # ひれの板の上に縦の線として残るので、体の近くの細い所（6 画素より細い）は外す
        near = dilate(self.body, 8)
        fin = fin & ~(near & ~dilate(erode(fin, 3), 3))
        self.median = [c for c in components(fin) if c.sum() > 0.003 * area]
        # 尾の付け根の上を細く伝って、後ろの背びれ（しりびれ）と尾びれが 1 枚につながることがある（アジ）。1 枚のままだと、
        # 背びれが尾びれと見なされて畳めないので、尾びれの付け根（体の後ろの端）で切り分ける
        cut = np.abs(np.arange(self.W) - self.XB) <= 2
        split = []
        for c in self.median:
            xs = np.flatnonzero(c.any(0))
            if xs.min() < self.XB - 0.1 * (self.XB - self.XF) and xs.max() > self.XB + 2:
                print("split fin at tail base", int(xs.min()), int(xs.max()))
                split += [p for p in components(c & ~cut[None, :]) if p.sum() > 0.003 * area]
            else:
                split.append(c)
        self.median = split
        # 付け根の近く（体から体長の 1.5% まで）で、骨の間の膜が抜けて体の側へ開いた切れ目やくぼみ（ブリの後ろの背びれ、
        # メバルの背びれの棘とやわらかい所の間）は、ひれの形に入れる（d 画素ふくらませて縮める。layers で不透明にする）
        d = self.base_fill = max(2, int(round(0.015 * (self.tail_px - self.snout_px))))
        near_body = dilate(self.body, d) & ~self.body
        filled = []
        for c in self.median:
            # 尾びれ（体の後ろの端より後ろへ出ている）は、尾の付け根との間のくぼみを埋めない。
            # tail_overlap（尾の付け根の太い魚）：尾びれの板を体の後ろの端に重ねる（体の切り口と板の間の数画素のすき間から、
            # 向こうが細い線に透けて見えた）。体の後ろの端から tail_overlap 画素まで、魚の形の中を板に入れる
            if np.flatnonzero(c.any(0)).max() > self.XB + 2:
                ov = int(self.cfg.get("tail_overlap", 0))
                if ov:
                    xs = np.arange(self.W)[None, :]
                    c = c | (self.fish & (xs >= self.XB - ov) & (xs <= self.XB + 2 * ov) & dilate(c | self.body, 2))
                filled.append(c)
                continue
            cols = (c & near_body).any(0)
            filled.append(c | (erode(dilate(c | self.body, d), d) & near_body & cols[None, :]))
        self.median = filled
        # pectoral: the photos differ inside the body where the fin was painted out
        # compare low frequencies only: the edit also redraws scale detail everywhere
        d = np.abs(box_blur(self.src, 6) - box_blur(self.nof, 6)).sum(-1)
        inner = erode(self.body, 6)
        dv = d[inner]
        thr = max(0.06, float(np.percentile(dv, 97)) * 0.35) if dv.size else 0.06
        cand = (box_blur(d, 3) > thr) & inner
        comps = [c for c in components(cand) if c.sum() > 0.003 * area]
        self.pect = None
        self.pect_base = None
        body_area = self.body.sum()
        for c in ([] if self.flat else comps):        # a flatfish's small pectoral stays painted on the skin
            ys, xs = np.nonzero(c)
            u = (xs.mean() - self.XF) / (self.XB - self.XF)
            # (and are not a long strip along the flank, where the edit only redrew a stripe or the lateral line)
            strip = (xs.max() - xs.min()) > 4 * (ys.max() - ys.min())
            if u < 0.55 and c.sum() < 0.2 * body_area and not strip:   # pectorals sit behind the head, and are not huge
                # fill small holes so the fin is one solid sheet
                self.pect = (erode(dilate(c, 12), 12) | c) & erode(self.body, 2)
                break
        # Codex に聞いた胸びれの輪郭（refs/fish/<id>_pect.json、写真の画素）があれば、その形で切り抜く（写真の違いから取った形は、
        # 周りの体の皮ごとでこぼこになる）。体の外へ出た所も胸びれにして、縦のひれからは外す
        pj = REF + self.sid + "_pect.json"
        if os.path.exists(pj):
            yy, xx = np.mgrid[0:self.H, 0:self.W]
            xc = np.clip(xx, self.XF, self.XB)
            in_outline = (yy >= self.TOP(xc)) & (yy <= self.BOT(xc)) & (xx >= self.XF) & (xx <= self.XB)
            # 体の輪郭の中はそのまま（魚の写る所は、体の暗い斑点で穴が開いている）、外は魚の写る所だけ
            pm = erode(poly_mask(json.load(open(pj))["poly"], self.fish.shape), 1) & (in_outline | self.fish)
            self.pect = pm
            self.pect_base = json.load(open(pj)).get("base")
            # 胸びれを抜くと、重なっていたひれ（カサゴの腹びれ）が切れ切れになるので、分け直して小さなかけらは捨てる
            # （かけらは体の下に細い板として残り、縦の線に見えた）
            self.median = [p for c in self.median for p in components(c & ~dilate(pm, 3))]
            self.median = [c for c in self.median if c.sum() > 0.003 * area]
        # 小離鰭（マグロ類の、後ろの背びれ・しりびれから尾の付け根までの小さなひれの列）：1 つずつは小さく、上で捨てられるので、
        # 上と下でまとめて 1 枚ずつのひれにする（finlets）。すき間は写真のまま透かす（付け根を埋めると帯に見える）
        self.finlets = []
        if self.cfg.get("finlets"):
            mid = lambda x: 0.5 * (self.TOP(x) + self.BOT(x))
            groups = {1: np.zeros(self.fish.shape, bool), -1: np.zeros(self.fish.shape, bool)}
            for c in components(fin):
                n = c.sum()
                if not (0.0001 * area < n <= 0.003 * area):
                    continue
                ys, xs = np.nonzero(c)
                cx = xs.mean()
                if not (self.XF + 0.55 * (self.XB - self.XF) < cx < self.XB):
                    continue
                if not (c & dilate(self.body, 6)).any():
                    continue
                groups[1 if ys.mean() < mid(cx) else -1] |= c
            for g in groups.values():
                if g.sum() > 0:
                    self.median.append(g)
                    self.finlets.append(g)
            print("finlets", [int(g.sum()) for g in self.finlets])
        print("pect thr", round(thr, 3), "found", self.pect is not None,
              int(self.pect.sum()) if self.pect is not None else 0, "body", int(body_area))

    def _eyes(self):
        lum = box_blur(self.src @ np.array([0.3, 0.59, 0.11], np.float32), 3)
        x1 = self.XF + 0.2 * (self.XB - self.XF)
        h, w = lum.shape
        yy, xx = np.mgrid[0:h, 0:w]
        region = erode(self.body, 4) & (xx < x1)
        if not self.flat:
            # eyes sit in the middle band of the head, below the dark back and above the jaw
            tp = self.TOP(np.clip(xx, self.XF, self.XB)); bt = self.BOT(np.clip(xx, self.XF, self.XB))
            region &= (yy > tp + 0.18 * (bt - tp)) & (yy < tp + 0.55 * (bt - tp))
        self.eyes = []
        cand = np.where(region, lum, 9.0)
        for _ in range(2 if self.flat else 1):
            k = int(np.argmin(cand))
            ey, ex = divmod(k, w)
            depth = self.BOT(ex) - self.TOP(ex)
            r = float(np.clip(depth * (0.07 if self.flat else 0.11), 6, 80))
            # Codex に聞いた目（refs/fish/<id>_eye.json、写真の画素の中心と半径）があれば、それを使う（いちばん暗い所は瞳で、
            # 目は瞳より大きく、瞳が真ん中にあるとは限らない。タチウオは黒目のまわりの金色が広く、目玉がずれて小さく見えた）
            ej = REF + self.sid + "_eye.json"
            if os.path.exists(ej) and not self.flat:
                e = json.load(open(ej))
                ex, ey, r = int(round(e["x"])), int(round(e["y"])), float(e["r"])
            self.eyes.append((float(ex), float(ey), r))
            cand[max(0, ey - int(3 * r)):ey + int(3 * r), max(0, ex - int(3 * r)):ex + int(3 * r)] = 9.0

    # ---------- texture layers ----------
    def layers(self):
        inside = erode(self.body, 3)
        img = to_lin(self.nof)
        lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        img = np.clip(lum[..., None] + (img - lum[..., None]) * 1.1, 0, 1) ** 1.04
        filled = img * inside[..., None]
        wgt = inside.astype(np.float32)
        for r in (2, 4, 8, 16, 32, 64):
            fb = box_blur(filled, r); wb = box_blur(wgt, r)
            need = wgt < 0.5
            filled = np.where(need[..., None], fb / np.maximum(wb, 1e-4)[..., None], filled)
            wgt = np.where(need, (wb > 1e-3).astype(np.float32), wgt)
        self.skin = filled.astype(np.float32)
        self.skin_blur = box_blur(self.skin, 10)
        self.inside = inside.astype(np.float32)
        # fin plate: un-premultiplied colour over the backdrop, alpha from the fin masks
        src = to_lin(self.src)
        diff = np.linalg.norm(self.src - self.bg, axis=-1)
        mx, mn = self.src.max(-1), self.src.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-4)
        a_bg = np.maximum(np.clip((diff - 0.03) / 0.18, 0, 1), np.clip((sat - 0.1) / 0.15, 0, 1) * ss(0.05, 0.1, diff))
        finm = np.zeros(self.fish.shape, np.float32)
        holes = np.zeros(self.fish.shape, bool)
        for c in self.median:
            finm = np.maximum(finm, box_blur(dilate(c, 2).astype(np.float32), 1))
            # 囲まれた穴と、縁のすき間で外へつながった小さな穴（暗い斑点。4 画素ふくらませて 5 画素縮めて埋まる所）
            holes |= enclosed(c) | (erode(dilate(c, 4), 5) & ~c)
        alpha = finm * a_bg
        # ひれに囲まれた穴は埋める
        alpha = np.maximum(alpha, box_blur(holes.astype(np.float32), 1) * 0.9)
        # 膜に模様があって透けないひれ（マゴチ）は、縁の 2 画素より内側を不透明に（黒い斑点が背景の色に近く、透けて穴に見える）
        solid = np.zeros(self.fish.shape, np.float32)
        if self.cfg.get("solid_fins"):
            for c in self.median + ([self.pect] if self.pect is not None else []):
                # 形の穴が縁のすき間で外へつながっていることがあるので、閉じてから（8 画素ふくらませて 10 画素縮める）。
                # 小離鰭の列は閉じない（ひれの間のすき間が埋まって帯になる）
                if any(c is f for f in self.finlets):
                    solid = np.maximum(solid, box_blur(erode(c, 2).astype(np.float32), 1))
                    continue
                # 黒っぽいひれ（キハダの尾びれ）は大きな斑の穴が開くので、solid_close 画素ふくらませて閉じる（省けば 8）
                r = self.cfg.get("solid_close", 8)
                closed = erode(dilate(c, r), r + 2)
                solid = np.maximum(solid, box_blur((closed | enclosed(closed) | erode(c, 2)).astype(np.float32), 1))
            alpha = np.maximum(alpha, solid * 0.95)
        # 縦のひれの付け根の近く（体から体長の 1.5% まで）は不透明に。付け根の膜が薄くて背景が透ける所（ブリの後ろの背びれ、
        # メバルの背びれ）は、体とひれの間に穴や縦の切れ目が開いて見えた
        # （骨の間の膜が抜けた切れ目は、_fins でひれの形に入れてある）
        d = self.base_fill
        base = np.zeros(self.fish.shape, bool)
        for c in self.median:
            base |= c & dilate(self.body, d)
        base_w = box_blur(base.astype(np.float32), max(1, d // 4))
        alpha = np.maximum(alpha, base_w * 0.95)
        solid = np.maximum(solid, base_w)
        if self.pect is not None:
            # 体の上は不透明に近く、体の外へ出た所（マゴチの大きな胸びれなど）は縦のひれと同じく写真の透け具合
            # 体の上かどうかは、体の写真の色ではなく体の輪郭の上下で（体の暗い斑点を背景と見て、ひれに穴が開くので）
            yy, xx = np.mgrid[0:self.H, 0:self.W]
            xc = np.clip(xx, self.XF, self.XB)
            in_outline = (yy >= self.TOP(xc)) & (yy <= self.BOT(xc)) & (xx >= self.XF) & (xx <= self.XB)
            on_body = self.pect & in_outline
            alpha = np.maximum(alpha, box_blur(on_body.astype(np.float32), 2) * 0.92)
            alpha = np.maximum(alpha, box_blur((self.pect & ~in_outline).astype(np.float32), 1) * a_bg)
            self._pect_on_body = on_body
        bgl = to_lin(self.bg)
        col = (src - bgl * (1 - a_bg[..., None])) / np.maximum(a_bg[..., None], 0.05)
        # 不透明にした所と埋めた穴は、背景を引かずに写真の色のまま（暗い斑点で背景を引くと、色が明るく跳ね上がる）
        solid = np.maximum(solid, box_blur(holes.astype(np.float32), 1))
        col = col * (1 - solid[..., None]) + src * solid[..., None]
        if self.pect is not None:
            pm = box_blur(self._pect_on_body.astype(np.float32), 2)[..., None]
            col = col * (1 - pm) + src * pm            # over the body the photo needs no un-premultiply
        self.plate = np.concatenate([np.clip(col, 0, 1), alpha[..., None]], -1).astype(np.float32)


# ---------------- geometry ----------------

def set_attr(me, name, values):
    at = me.attributes.get(name) or me.attributes.new(name, "FLOAT_VECTOR", "POINT")
    at.data.foreach_set("vector", np.ascontiguousarray(values, np.float32).ravel())


def mesh_from(name, verts, faces, uvs):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    uvl = me.uv_layers.new(name="UVMap")
    flat = np.array([c for f in uvs for c in f], np.float32)
    uvl.data.foreach_set("uv", flat.ravel())
    for p in me.polygons:
        p.use_smooth = True
    me.validate()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def body_v(vm):
    return BODY_V0 + (1.0 - BODY_V0) * vm


def build_body(F, n_st=None, n_ring=None):
    n_st = n_st or LOD_PARAMS[0]
    n_ring = n_ring or LOD_PARAMS[1]
    u = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n_st))          # denser at both ends
    xs = F.XF + 0.5 + (F.XB - F.XF - 1.0) * u
    ts = 2 * np.pi * np.arange(n_ring) / n_ring
    XX, TT = np.meshgrid(xs, ts, indexing="ij")
    yp, side = F.section(XX, TT)
    X, Z = F.to_m(XX, yp)
    verts = np.stack([X, side * F.S, Z], -1).reshape(-1, 3)
    yf = (F.TOP(xs[0]) + F.BOT(xs[0])) / 2
    yb = (F.TOP(xs[-1]) + F.BOT(xs[-1])) / 2
    Xf, Zf = F.to_m(xs[0] - 1.0, yf)
    Xb, Zb = F.to_m(xs[-1] + 1.0, yb)
    verts = np.vstack([verts, [[Xf, 0, Zf], [Xb, 0, Zb]]])
    i_f, i_b = len(verts) - 2, len(verts) - 1
    uo = (xs - F.XF) / (F.XB - F.XF)
    faces, uvs = [], []
    vm = lambda k: 2.0 * min(k / n_ring, 1 - k / n_ring)
    for i in range(n_st - 1):
        for k in range(n_ring):
            k2 = (k + 1) % n_ring
            a, b = i * n_ring + k, i * n_ring + k2
            faces.append((a, b, (i + 1) * n_ring + k2, (i + 1) * n_ring + k))
            v0, v1 = body_v(vm(k)), body_v(vm(k + 1))
            uvs.append(((uo[i], v0), (uo[i], v1), (uo[i + 1], v1), (uo[i + 1], v0)))
    o = (n_st - 1) * n_ring
    for k in range(n_ring):
        k2 = (k + 1) % n_ring
        v0, v1, vc = body_v(vm(k)), body_v(vm(k + 1)), body_v(0.5)
        faces.append((i_f, k2, k)); uvs.append(((0, vc), (uo[0], v1), (uo[0], v0)))
        faces.append((i_b, o + k, o + k2)); uvs.append(((1, vc), (uo[-1], v0), (uo[-1], v1)))
    ob = mesh_from(F.sid + "_body", verts, faces, uvs)
    n = len(verts)
    set_attr(ob.data, "_FIN", np.zeros((n, 3)))
    set_attr(ob.data, "_PIV", np.zeros((n, 3)))
    return ob


def body_uv_of(F, xp, yp):
    u = (xp - F.XF) / (F.XB - F.XF)
    top, bot = F.TOP(xp), F.BOT(xp)
    t = np.arccos(np.clip(2 * (yp - bot) / (top - bot) - 1, -1, 1))
    return u, body_v(t / np.pi)


def build_eyes(F):
    out = []
    for (ex, ey, r) in F.eyes:
        X, Z = F.to_m(ex, ey)
        R = r * F.S
        ys = float(F.surface_y(ex, ey))
        bm = bmesh.new()
        for side in (1, -1):
            g = bmesh.ops.create_uvsphere(bm, u_segments=LOD_PARAMS[3], v_segments=LOD_PARAMS[4], radius=1.0)
            for v in g["verts"]:
                lx, ly, lz = v.co
                v.co = (X + lx * R, side * (ys - 0.25 * R + ly * R * 0.5), Z + lz * R)
        me = bpy.data.meshes.new(F.sid + "_eye"); bm.to_mesh(me); bm.free()
        co = np.array([v.co[:] for v in me.vertices])
        xp = ex - (co[:, 0] - X) / F.S * 0.9
        yp = ey - (co[:, 2] - Z) / F.S * 0.9
        u, v = body_uv_of(F, xp, yp)
        loops = np.zeros(len(me.loops), np.int64); me.loops.foreach_get("vertex_index", loops)
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.stack([u[loops], v[loops]], -1).ravel())
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new(F.sid + "_eye", me)
        bpy.context.scene.collection.objects.link(ob)
        n = len(co)
        set_attr(me, "_FIN", np.tile([6, 1, 0], (n, 1)))
        set_attr(me, "_PIV", np.zeros((n, 3)))
        out.append(ob)
    return out


def sheet(F, mask, name, cell, place, rows=2):
    """Grid over the mask's bbox, cells without fin pixels removed. place(xp, yp) -> (X, Y, Z) metres.
    rows: the fewest rows (a long low fin needs several, or it cannot fold ray by ray)"""
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min() - 2, xs.max() + 2, ys.min() - 2, ys.max() + 2
    nx = int(np.clip(round((x1 - x0) / cell), 2, 40)); ny = int(np.clip(round((y1 - y0) / cell), rows, 24))
    gx = np.linspace(x0, x1, nx + 1); gy = np.linspace(y0, y1, ny + 1)
    cov = dilate(mask, 3)
    keep = np.zeros((ny, nx), bool)
    for j in range(ny):
        for i in range(nx):
            keep[j, i] = cov[int(gy[j]):int(gy[j + 1]) + 1, int(gx[i]):int(gx[i + 1]) + 1].any()
    used = {}
    verts, faces, pix = [], [], []

    def vid(i, j):
        if (i, j) not in used:
            used[(i, j)] = len(verts)
            verts.append(place(gx[i], gy[j])); pix.append((gx[i], gy[j]))
        return used[(i, j)]
    for j in range(ny):
        for i in range(nx):
            if keep[j, i]:
                faces.append((vid(i, j), vid(i, j + 1), vid(i + 1, j + 1), vid(i + 1, j)))
    return np.array(verts), faces, np.array(pix), (x0, y0, x1, y1)


def build_fins(F):
    """Returns list of (object, rect_px, kind) ; UVs filled in later by the packer."""
    parts = []
    cell = max(F.XB - F.XF, 1) / LOD_PARAMS[2]
    for k, m in enumerate(F.median):
        verts, faces, pix, rect = sheet(F, m, f"{F.sid}_fin{k}", cell,
                                        lambda x, y: (*F.to_m(x, y)[:1], 0.0, F.to_m(x, y)[1]),
                                        F.cfg.get("fin_rows", 2) if not LOD else 2)
        parts.append(dict(verts=verts, faces=faces, pix=pix, rect=rect, part=1, kind="median%d" % k, mask=m))
    if F.pect is not None:
        ys, xs = np.nonzero(F.pect)
        xa = xs.min(); xlen = max(xs.max() - xa, 1)
        x_base, y_base = xa, ys[xs < xa + 0.12 * xlen].mean()
        if F.pect_base:
            # Codex に聞いた付け根の線（いちばん前の所は、お腹の下へ張り出した先のこともある。マゴチ）
            x_base, y_base = np.mean(F.pect_base, 0)
        # 付け根の体の幅より内へは寄せない（体の表面に沿わせると、お腹の下へ出た所が体の真ん中へ巻き込む。マゴチの大きな胸びれ）
        # 胸びれの板を置く所だけを上へずらす（pect_up：体長に対する割合。絵は写真の同じ所から切り抜く）
        up = F.cfg.get("pect_up", 0.0) * (F.tail_px - F.snout_px)
        y_base = y_base - up
        w_base = float(F.surface_y(np.clip(x_base, F.XF, F.XB), y_base))
        for side in (1, -1):
            def place(x, y, side=side):
                y = y - up
                X, Z = F.to_m(x, y)
                rr = np.clip((x - xa) / xlen, 0, 1)
                w = np.maximum(F.surface_y(np.clip(x, F.XF, F.XB), y), w_base)
                Y = side * (w + 0.0015 + 0.03 * F.cfg["length"] * rr ** 1.3)
                return (X, Y, Z)
            verts, faces, pix, rect = sheet(F, F.pect, f"{F.sid}_pect", cell * 0.7, place)
            rr = np.clip((pix[:, 0] - xa) / xlen, 0, 1)
            Xp, Zp = F.to_m(x_base, y_base)
            piv = np.array([Xp, side * w_base, Zp])
            parts.append(dict(verts=verts, faces=faces, pix=pix, rect=rect, part=4, kind="pect", mask=F.pect,
                              weight=np.clip(rr / 0.25, 0, 1) ** 1.5, piv=piv))
    return parts


def pack(rects):
    keys = list(rects)

    def shelf(k):
        order = sorted(keys, key=lambda t: -(rects[t][3] - rects[t][1]))
        x = y = float(PAD); sh = 0.0
        place = {}
        for t in order:
            w = (rects[t][2] - rects[t][0]) * k + 1; h = (rects[t][3] - rects[t][1]) * k + 1
            if w > AW - 2 * PAD:
                return None, 1e9
            if x + w > AW - PAD:
                x, y, sh = float(PAD), y + sh + PAD, 0.0
            place[t] = (x, y); x += w + PAD; sh = max(sh, h)
        return place, y + sh + PAD
    lo, hi = 0.02, 3.0
    for _ in range(40):
        k = (lo + hi) / 2
        _, used = shelf(k)
        lo, hi = (k, hi) if used <= FIN_ROWS else (lo, k)
    place, _ = shelf(lo)
    return lo, place


def bake(F, fin_parts, k, place):
    atlas = np.zeros((AH, AW, 4), np.float32)          # row 0 = V 0 (bottom)
    rows = np.arange(FIN_ROWS, AH)
    vm = ((rows + 0.5) / AH - BODY_V0) / (1 - BODY_V0)
    U = (np.arange(AW) + 0.5) / AW
    uu, vv = np.meshgrid(U, vm)
    xp = F.XF + uu * (F.XB - F.XF)
    t = vv * np.pi
    yp, side = F.section(xp, t)
    hw = np.abs(side)
    # how squarely each texel faces the camera that took the photo (projection stretch)
    dYt, dZt = np.gradient(hw, axis=0), np.gradient(-yp, axis=0)
    dx = (F.XB - F.XF) / AW
    dYx, dZx = np.gradient(hw, axis=1) / dx, np.gradient(-yp, axis=1) / dx
    nx = dYt * dZx - dZt * dYx; ny = dZt; nz = -dYt
    facing = np.abs(ny) / np.maximum(np.sqrt(nx * nx + ny * ny + nz * nz), 1e-9)
    p_in = bilinear(F.inside, xp, yp)
    w = (ss(0.15, 0.45, facing) * ss(0.2, 0.9, p_in))[..., None]
    col = bilinear(F.skin, xp, yp) * w + bilinear(F.skin_blur, xp, yp) * (1 - w)
    atlas[FIN_ROWS:, :, :3] = lin_to_srgb(col)
    atlas[FIN_ROWS:, :, 3] = 1.0
    # 背中の真ん中の線（体の輪の上の端）は、体の所の端の行（FIN_ROWS）をちょうど読む。その外はひれとの間の PAD で透明なので、
    # 読む色が半分透けて背中の真ん中が細く抜け、背びれと体の間のすき間に見えた。端の行を PAD の半分まで伸ばす
    atlas[FIN_ROWS - PAD // 2:FIN_ROWS] = atlas[FIN_ROWS]
    # 縦のひれの板は、体の輪郭の中（3 画素より内）を透明に。ひれの付け根と体の輪郭の間は「ひれに囲まれた穴」として体の色で
    # 埋まっていて、体の中に隠れるはずが、ひれの前後の端では体の下にのぞき、縦の線に見えた
    yy, xx = np.mgrid[0:F.H, 0:F.W]
    xc = np.clip(xx, F.XF, F.XB)
    inside = erode((yy >= F.TOP(xc)) & (yy <= F.BOT(xc)) & (xx >= F.XF) & (xx <= F.XB), 3)
    for p in fin_parts:
        key = p["kind"]
        x0, y0, x1, y1 = p["rect"]
        ox, oy = place[key]
        pw = int(math.ceil((x1 - x0) * k)); ph = int(math.ceil((y1 - y0) * k))
        PX, PY = np.meshgrid(np.arange(int(ox), min(AW, int(ox) + pw + 1)), np.arange(int(oy), min(FIN_ROWS, int(oy) + ph + 1)))
        sx = x0 + (PX + 0.5 - ox) / k; sy = y0 + (PY + 0.5 - oy) / k
        c = bilinear(F.plate, sx, sy)
        # そのひれの所だけ（写真のひれは全部 1 枚にあるので、四角の中のほかのひれ、尾びれの横のしりびれや腹びれの前の胸びれが、
        # 板の端のます目に細い縦の帯として出る）
        own = dilate(p["mask"], 2) & (~inside if p["part"] == 1 else True)
        c[..., 3] *= np.clip(bilinear(box_blur(own.astype(np.float32), 1)[..., None], sx, sy)[..., 0], 0, 1)
        rr = FIN_ROWS - 1 - PY
        atlas[rr, PX, :3] = lin_to_srgb(c[..., :3])
        atlas[rr, PX, 3] = c[..., 3]
    img = bpy.data.images.new(F.sid + "_atlas", AW, AH, alpha=True)
    img.pixels.foreach_set(np.ascontiguousarray(atlas, np.float32).ravel())
    img.filepath_raw = ROOT + "scripts/fishgen/logs/" + F.sid + "_atlas.png"
    img.file_format = "PNG"
    img.save()
    return img


def make(sid):
    bpy.ops.wm.read_homefile(use_empty=True)
    F = Fish(sid)
    F.layers()
    body = build_body(F)
    eyes = build_eyes(F)
    fins = build_fins(F)
    rects = {}
    for p in fins:
        rects[p["kind"]] = p["rect"]
    k, place = pack(rects)
    fin_objs = []
    for p in fins:
        x0, y0 = p["rect"][:2]
        ox, oy = place[p["kind"]]
        uv_pt = np.stack([(ox + (p["pix"][:, 0] - x0) * k) / AW, (FIN_ROWS - (oy + (p["pix"][:, 1] - y0) * k)) / AH], -1)
        uvs = [tuple(tuple(uv_pt[i]) for i in f) for f in p["faces"]]
        ob = mesh_from(F.sid + "_" + p["kind"], p["verts"], p["faces"], uvs)
        n = len(p["verts"])
        fin = np.zeros((n, 3)); fin[:, 0] = p["part"]
        fin[:, 1] = p.get("weight", np.ones(n))
        piv = np.tile(p.get("piv", np.zeros(3)), (n, 1))
        set_attr(ob.data, "_FIN", fin)
        set_attr(ob.data, "_PIV", piv)
        fin_objs.append(ob)
    img = bake(F, fins, k, place)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in [body] + eyes + fin_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    me = body.data
    mat = bpy.data.materials.new(sid)
    mat.use_nodes = True
    Nn, L = mat.node_tree.nodes, mat.node_tree.links
    b = next(n for n in Nn if n.type == "BSDF_PRINCIPLED")
    tn = Nn.new("ShaderNodeTexImage"); tn.image = img
    L.new(tn.outputs["Color"], b.inputs["Base Color"]); L.new(tn.outputs["Alpha"], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.4
    b.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = False
    me.materials.clear(); me.materials.append(mat)
    body.name = sid
    sw = F.cfg["swim"]
    snout = float(F.to_m(F.snout_px, 0)[0])
    body["swim"] = {"snout": snout, "length": F.cfg["length"], "lambda": sw["lam"], "freq": sw["freq"], "amp": sw["amp"],
                    "env": sw["env"], "flat": F.flat, "name": F.cfg["name"],
                    # 写真の画素と模型の対応：模型 x = (x0 − 画素 x) / k、模型 y = (z0 − 画素 y) / k
                    "photo": [round(F.X0, 2), round(F.Z0, 2), round(1 / F.S, 3)]}
    me.calc_loop_triangles()
    stats = dict(id=sid, tris=len(me.loop_triangles), verts=len(me.vertices), fins=len(F.median), photo=list(body["swim"]["photo"]),
                 pect=F.pect is not None, eyes=len(F.eyes), pack_scale=round(k, 3))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    body.select_set(True)
    # the light fixed version (_lo3) uses the full glb's texture in the game, so it is exported without the image
    # (FISH_LOD_TEX=1 keeps it: for a fish whose full glb was made elsewhere with a different atlas, e.g. suzuki)
    image_format = "NONE" if LOD_LEVEL == 3 and os.environ.get("FISH_LOD_TEX") != "1" else "WEBP"
    kw = dict(filepath=OUT + sid + LOD_SUFFIX + ".glb", export_format="GLB", use_selection=True, export_animations=False,
              export_skins=False, export_yup=True, export_apply=False, export_image_format=image_format,
              export_image_quality=88, export_texcoords=True, export_normals=True, export_tangents=False,
              export_attributes=True, export_extras=True, export_materials="EXPORT")
    bpy.ops.export_scene.gltf(**kw)
    stats["glb_kb"] = round(os.path.getsize(OUT + sid + LOD_SUFFIX + ".glb") / 1024)
    if LOD:
        print("FISHSTATS " + json.dumps(stats, ensure_ascii=False))
        return
    print("FISHSTATS " + json.dumps(stats, ensure_ascii=False))
    # debug overlay of the analysis
    dbg = F.src.copy()
    dbg[F.body & ~erode(F.body, 2)] = (0, 1, 1)
    for m in F.median:
        dbg[m & ~erode(m, 2)] = (1, 0, 1)
    if F.pect is not None:
        dbg[F.pect & ~erode(F.pect, 2)] = (1, 1, 0)
    for (ex, ey, r) in F.eyes:
        yy, xx = np.ogrid[0:F.H, 0:F.W]
        ring = np.abs(np.hypot(xx - ex, yy - ey) - r) < 1.5
        dbg[ring] = (0, 1, 0)
    im = bpy.data.images.new(sid + "_dbg", F.W, F.H)
    im.pixels.foreach_set(np.concatenate([dbg[::-1], np.ones((F.H, F.W, 1), np.float32)], -1).ravel())
    im.filepath_raw = ROOT + "scripts/fishgen/logs/" + sid + "_analysis.png"
    im.file_format = "PNG"
    im.save()


if __name__ == "__main__":
    ids = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(SPECIES)
    for sid in ids:
        try:
            make(sid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("FISHFAIL", sid, e)
