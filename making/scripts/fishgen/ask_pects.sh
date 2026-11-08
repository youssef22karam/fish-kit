#!/bin/bash
# 胸びれの輪郭を Codex に聞く（head_rig.py pectgrid → Codex → pectapply）。写真の違いから自動で取った胸びれは、
# 周りの体の皮ごとでこぼこに切り抜かれるので、この輪郭で切り抜く（refs/fish/<名前>_pect.json があれば fishgen.py が使う）。
# 使い方: bash scripts/fishgen/ask_pects.sh <名前> ...（同時に動かすのは JOBS（省略で 3）まで）
CODEX=${CODEX:-$(ls -t "$(cygpath -u "$LOCALAPPDATA")"/OpenAI/Codex/bin/*/codex.exe | head -1)}
H="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
JOBS=${JOBS:-3}
for k in "$@"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 5; done
  (
    python "$H/head_rig.py" pectgrid "$k" > /dev/null
    "$CODEX" -c model_reasoning_effort=high -c approval_policy=never exec --skip-git-repo-check -s read-only -C "$H/logs" \
      "$(cat "$H/logs/${k}_pectask.txt")" -i "$H/logs/${k}_pectgrid.png" < /dev/null > "$H/logs/${k}_codex_pect.log" 2>&1
    python "$H/head_rig.py" pectapply "$k" || echo "$k pect FAILED"
  ) &
done
wait
echo ALLDONE
