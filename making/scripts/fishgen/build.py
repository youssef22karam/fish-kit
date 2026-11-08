"""Builds the photo fish: fishgen.py, with an automatic stand-in for <id>_nofins.png when Codex has not made
one (the body outline is smooth, fins are bumps sticking out of it).
blender -b --factory-startup -P scripts/fishgen/build.py -- mebaru kasago
FISH_LOD=1 for the far (_lo) versions."""
import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fishgen as fg  # noqa: E402


def robust_edge(u, e, outward, deg=6, tol=4.0, iters=10):
    """Fit a smooth body edge e(u) through the silhouette edge, ignoring points that stick OUT (fins):
    outward = -1 for the upper edge (fins make it smaller), +1 for the lower edge."""
    w = np.ones_like(e)
    for _ in range(iters):
        c = np.polyfit(u, e, deg, w=w + 1e-6)
        f = np.polyval(c, u)
        w = ((e - f) * outward < tol).astype(float)
    return np.polyval(c, u)


def auto_nofins(path, out):
    src = _load_rgb(path)
    H, W = src.shape[:2]
    border = np.concatenate([src[:12].reshape(-1, 3), src[-12:].reshape(-1, 3), src[:, :12].reshape(-1, 3),
                             src[:, -12:].reshape(-1, 3)])
    bg = np.median(border, 0)
    diff = np.linalg.norm(src - bg, axis=-1)
    mx, mn = src.max(-1), src.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    a = np.maximum(fg.ss(0.05, 0.12, diff), fg.ss(0.12, 0.25, sat) * fg.ss(0.04, 0.08, diff))
    M = fg.components(fg.box_blur(a, 2) > 0.5)[0]
    cols = np.flatnonzero(M.any(0))
    xs0, xt = int(cols.min()), int(cols.max())
    L = xt - xs0
    hM = M.sum(0).astype(float)
    lo, hi = xs0 + int(0.68 * L), xs0 + int(0.95 * L)
    hs = np.convolve(hM, np.ones(9) / 9, "same")
    xp = lo + int(np.argmin(hs[lo:hi]))
    xs = np.arange(xs0, xp + 1)
    top = np.array([np.flatnonzero(M[:, x])[0] for x in xs], float)
    bot = np.array([np.flatnonzero(M[:, x])[-1] for x in xs], float)
    depth = float(np.percentile(bot - top, 75))
    u = (xs - xs0) / max(xp - xs0, 1)
    tol = max(3.0, 0.02 * depth)
    ft = robust_edge(u, top, -1, tol=tol)
    fb = robust_edge(u, bot, +1, tol=tol)
    ft = np.maximum(ft, top)
    fb = np.minimum(fb, bot)
    B = np.zeros_like(M)
    yy = np.arange(H)[:, None]
    B[:, xs0:xp + 1] = (yy >= ft[None, :]) & (yy <= fb[None, :])
    B &= M
    print("auto nofins", os.path.basename(out), "snout", xs0, "peduncle", xp, "tail", xt)
    out_img = np.where(B[..., None], src, bg[None, None, :])
    img = bpy.data.images.new("auto", W, H)
    img.pixels.foreach_set(np.concatenate([out_img[::-1], np.ones((H, W, 1), np.float32)], -1).astype(np.float32).ravel())
    img.filepath_raw = out
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


_load_rgb = fg.load_rgb


def load_or_auto(path):
    """fins-removed photo if Codex made one, else the automatic stand-in"""
    if path.endswith("_nofins.png") and not os.path.exists(path):
        auto = path.replace("_nofins.png", "_nofins_auto.png")
        if not os.path.exists(auto):
            auto_nofins(path.replace("_nofins.png", ".png"), auto)
        path = auto
    return _load_rgb(path)


fg.load_rgb = load_or_auto

if __name__ == "__main__":
    ids = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else ["mebaru", "kasago"]
    for sid in ids:
        try:
            fg.make(sid)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("FISHFAIL", sid, e)
