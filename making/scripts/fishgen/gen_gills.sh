#!/bin/bash
# えらぶたを切り取って中のえらが見える写真を Codex に描かせる（refs/fish/<名前>_gills_raw.png）。
# えらぶたの範囲を間違えやすいので、必ず範囲の画像（<名前>_gill_range.png、head_rig.py apply が作る）を一緒に渡す。
# 描いた写真は head_rig.py gills で元の写真に合わせ、範囲の中だけ貼る。
# 使い方: bash scripts/fishgen/gen_gills.sh <名前> ...（同時に動かすのは JOBS（省略で 2）まで）
CODEX=${CODEX:-$(ls -t "$(cygpath -u "$LOCALAPPDATA")"/OpenAI/Codex/bin/*/codex.exe | head -1)}
ROOT="$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))"
OUT="$ROOT/refs/fish"
LOG="$ROOT/scripts/fishgen/logs"
mkdir -p "$LOG"
P="Use your image generation/editing tool to edit the FIRST attached image (a photograph of a fish facing left). Cut away the gill cover so that the gills underneath are exposed: inside the gill cover area show the bright red, finely combed gill filaments on curved pale gill arches, darker deep red toward the inside, wet and glossy, lit the same way as the photo, as in a real dissected fish. The SECOND attached image shows the exact gill cover area: the gill cover is exactly the area inside the red outline in that image. えらぶたの範囲はこの画像の赤い線の中です。範囲を間違えないように気をつけてください。(Be careful not to get its extent wrong: change only the inside of the red outline, all of it, and nothing outside it.) Do NOT draw any red outline in the result. Keep everything outside that area pixel-identical to the first image: exactly the same framing, image size and aspect ratio, fish position and size, the closed mouth, the eye, colours, lighting and the plain dark background. Do not run any commands or scripts and do not try to save or open the file; just generate the edited image."
JOBS=${JOBS:-2}
for k in "$@"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 5; done
  (
    "$CODEX" -c model_reasoning_effort=low -c approval_policy=never exec --skip-git-repo-check -s read-only -C "$ROOT" \
      "$P" -i "$OUT/$k.png" -i "$OUT/${k}_gill_range.png" < /dev/null > "$LOG/gills_${k}.log" 2>&1
    echo "$k gills exit=$?"
    python "$ROOT/scripts/fishgen/recover_refs.py"
  ) &
done
wait
echo ALLDONE
