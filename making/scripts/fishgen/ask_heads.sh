#!/bin/bash
# 頭の形（えらぶた・あご）を Codex に聞いて、形を photo-fish.ts に入れるまで（head_rig.py grid → Codex → answer → apply → ts）。
# 例として、えらぶたの範囲を赤い線で描いたシーバスの画像（refs/fish/suzuki_gill_range.png）を必ず一緒に見せる。
# 使い方: bash scripts/fishgen/ask_heads.sh <名前> ...（同時に動かすのは JOBS（省略で 3）まで。ts は最後に順に）
CODEX=${CODEX:-$(ls -t "$(cygpath -u "$LOCALAPPDATA")"/OpenAI/Codex/bin/*/codex.exe | head -1)}
ROOT="$(cd "$(dirname "$0")/../.." && (pwd -W 2>/dev/null || pwd))"
H="$ROOT/scripts/fishgen"
JOBS=${JOBS:-3}
for k in "$@"; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 5; done
  (
    python "$H/head_rig.py" grid "$k" > /dev/null
    "$CODEX" -c model_reasoning_effort=high -c approval_policy=never exec --skip-git-repo-check -s read-only -C "$H/logs" \
      "$(cat "$H/logs/${k}_ask.txt")" -i "$H/logs/${k}_headgrid.png" -i "$ROOT/refs/fish/suzuki_gill_range.png" < /dev/null > "$H/logs/${k}_codex_head.log" 2>&1
    python "$H/head_rig.py" answer "$k" && python "$H/head_rig.py" apply "$k" > /dev/null && echo "$k head ok" || echo "$k head FAILED"
  ) &
done
wait
# ゲームのソースがあれば、形を photo-fish.ts に入れる（キットでは logs/<名前>_head.ts を fish-kit.js に写す）
[ -f "$ROOT/src/game/fish/photo-fish.ts" ] && for k in "$@"; do [ -f "$H/logs/${k}_head.ts" ] && python "$H/head_rig.py" ts "$k"; done
echo ALLDONE
