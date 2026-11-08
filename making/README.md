# 新しい魚の作り方

今の魚は、すべてこの手順で作りました。人は AI エージェント（Claude Code）に頼み、途中でできた画像を見て「よい」か「やり直し」かを言うだけです。
写真は Codex（OpenAI）の画像生成で作り、Blender で 3D の形にします。

All fish in this kit were made this way. A person asks an AI agent, and the agent runs these scripts.
The scripts have Codex generate the photos and read off shapes, and Blender builds the mesh. Give this file to your agent.

## 用意するもの

- AI エージェント（Claude Code など）
- Codex CLI：画像生成が使える ChatGPT の契約が要る
- Blender 5
- Python 3（numpy・scipy・Pillow）、bash

コマンドはこのフォルダ（`making/`）で動かします。写真は `refs/fish/` に、できた魚は `public/fish/` にできます。

## 手順

| # | すること | 人が見ること |
|---|---|---|
| 1 | `scripts/fishgen/gen_refs.sh` に魚の説明（学名・大きさ・体の色）を足し、`fishgen.py` の `SPECIES` に体長などを足して、`bash scripts/fishgen/gen_refs.sh <id>` を動かす。真横のひれを広げた写真と、ひれを消した写真ができる | 本物らしい色と形か。ひれが全部広がっているか |
| 2 | `blender -b -P scripts/fishgen/build.py -- <id>` で形を作る。遠く用の形は `FISH_LOD=1` を付けて同じコマンドを動かす | `scripts/fishgen/logs/<id>_analysis.png` で、体とひれが正しく分かれているか |
| 3 | `bash scripts/fishgen/ask_pects.sh <id>` と `bash scripts/fishgen/ask_eyes.sh <id>` で、胸びれと目の形を Codex に聞き、2 をやり直す | 胸びれと目がきれいに切り抜かれているか |
| 4 | `bash scripts/fishgen/ask_heads.sh <id>` で、えらぶたとあごの形を Codex に聞く | `scripts/fishgen/logs/<id>_headcheck.png` で、赤い線がえらぶたに合っているか |
| 5 | えらの見える写真を作る：`bash scripts/fishgen/gen_gills.sh <id>` → `python scripts/fishgen/head_rig.py gills <id>` → `python scripts/fishgen/head_photos.py <id>` | えらぶたの中だけが赤いえらになっているか |
| 6 | `fish-kit.js` に足す（下） | 全部の動きで、口・えら・ひれ・泳ぎがおかしくないか |

## fish-kit.js に足すもの

- `FILES`：`<id>: '<ファイル名>'`
- `GILLS`・`MOUTHS`・`HEAD_FILES`：4 でできた `scripts/fishgen/logs/<id>_head.ts` の中身
- `ALL_SPECIES`：似た魚の項目を写して、`id`・名前・大きさを変える

## 気をつけること

- **えらぶたの範囲は、必ず画像で見せる。** 言葉だけだと Codex は範囲をよく間違えます。スクリプトは赤い線で範囲を描いた画像を渡し、次の文を添えています：
  「えらぶたの範囲はこの画像の赤い線の中です。範囲を間違えないように気をつけてください。」
- 写真はすべて同じ大きさ・同じ位置にする（1672 × 941、真横、口が左、無地の濃い灰色の背景、口とえらぶたは閉じる）。
- 体の色は言葉ではっきり書く（「アカカマス」とだけ書くと真っ赤な魚を描いた）。
- 体が黒い魚は、背景を明るい灰色にする（背景と体の区別がつかず、形に穴があく）。
- Codex には画像を作らせるだけで、保存はさせない（作った画像は `recover_refs.py` が拾う）。

## 頼み方の例

> making/README.md を読んで、新しい魚として「ホウボウ（Chelidonichthys spinosus）、30cm。赤い体、青い縁取りのある大きな胸びれ」を作って。
> 写真ができたとき（手順 1）と、えらぶたの形ができたとき（手順 4）に、画像を見せて止まって。
