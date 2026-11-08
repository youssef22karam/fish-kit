"""Codex が画像を作ったのに refs/fish/ へ保存できなかった（Windows がコピーを止めた）ときに、Codex の作った画像を拾って置く。
ログ（scripts/fishgen/logs/ref_<名前>.log、nofins_<名前>.log、gills_<名前>.log → <名前>_gills_raw.png）に書かれた generated_images の PNG の場所から写す。
python scripts/fishgen/recover_refs.py
"""
import glob
import os
import re
import shutil

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
LOG = os.path.join(ROOT, "scripts/fishgen/logs")
OUT = os.path.join(ROOT, "refs/fish")

for log in sorted(glob.glob(os.path.join(LOG, "ref_*.log")) + glob.glob(os.path.join(LOG, "nofins_*.log")) + glob.glob(os.path.join(LOG, "gills_*.log"))):
    base = os.path.basename(log)[:-4]
    kind, name = base.split("_", 1)
    dst = os.path.join(OUT, name + {"nofins": "_nofins", "gills": "_gills_raw"}.get(kind, "") + ".png")
    if os.path.exists(dst):
        continue
    text = open(log, encoding="utf-8", errors="replace").read()
    found = [p for p in re.findall(r"[A-Za-z]:[\\/][^\s\)\]\"'`]*generated_images[^\s\)\]\"'`]*\.png", text) if os.path.exists(p)]
    # 場所が書かれていなければ、その回（session id）の generated_images の中のいちばん新しい PNG
    sid = re.search(r"session id: ([0-9a-f-]+)", text)
    if not found and sid:
        found = sorted(glob.glob(os.path.join(os.path.expanduser("~"), ".codex/generated_images", sid.group(1), "*.png")), key=os.path.getmtime)
    if found:
        shutil.copy(found[-1], dst)
        print("recovered", dst, "<-", found[-1])
