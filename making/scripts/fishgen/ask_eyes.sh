#!/bin/bash
# 目の円（目玉全体のふち）を Codex に聞く（head_rig.py eyeask → Codex → eyeapply）。fishgen.py は refs/fish/<名前>_eye.json があれば、
# いちばん暗い所（瞳）の代わりにそれを目玉にする。使い方: bash scripts/fishgen/ask_eyes.sh <名前> ...（同時に JOBS（省略で 3）まで）
CODEX=${CODEX:-$(ls -t "$(cygpath -u "$LOCALAPPDATA")"/OpenAI/Codex/bin/*/codex.exe | head -1)}
H="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
JOBS=${JOBS:-3}
for k in "$@"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 5; done
  (
    python "$H/head_rig.py" grid "$k" > /dev/null && python "$H/head_rig.py" eyeask "$k"
    "$CODEX" -c model_reasoning_effort=high -c approval_policy=never exec --skip-git-repo-check -s read-only -C "$H/logs" \
      "$(cat "$H/logs/${k}_eyeask.txt")" -i "$H/logs/${k}_headgrid.png" < /dev/null > "$H/logs/${k}_codex_eye.log" 2>&1
    python "$H/head_rig.py" eyeapply "$k" || echo "$k eye FAILED"
  ) &
done
wait
echo ALLDONE
