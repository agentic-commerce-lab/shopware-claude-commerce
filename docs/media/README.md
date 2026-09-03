# Explainer video — Shopware × Claude Commerce Agents

![Explainer poster](explainer-poster.png)

- `explainer.mp4` — 1920×1080, H.264 + AAC, 30 fps, 2:03 (122.6 s). English voiceover, captions, music bed.
- `explainer-web.mp4` — 1280×720 web variant of the same cut (3.35 MB) for GitHub's inline player, see below.
- `explainer-poster.png` — still from the closing frame (thesis line, repo lockup `github.com/sthamann/shopware_claude_commerce`, five-command quick start) for README embedding.
- `explainer/` — the HyperFrames project that produced the video (composition, storyboard, script, captured screens, generated audio).

Repository shown in the video: **https://github.com/sthamann/shopware_claude_commerce** (on screen in frames 4 and 10; the URL is not narrated — the voice points to "the repository link in the description").

## Web variant for GitHub README

`explainer-web.mp4` is a 1280×720 re-encode of `explainer.mp4` (same 122.6 s cut, 30 fps, H.264 + AAC 96 kb/s stereo, `faststart`), 3.35 MB — inside GitHub's 10 MB attachment limit with headroom. Produced with:

```bash
ffmpeg -y -i docs/media/explainer.mp4 -vf scale=-2:720 -c:v libx264 -preset slow -crf 28 \
  -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 96k -ac 2 docs/media/explainer-web.mp4
```

GitHub only renders an inline video player for files uploaded as an *attachment* (drag the file into the README editor, an issue or a PR comment; GitHub returns a `https://github.com/user-attachments/assets/…` URL) and that URL is what goes into the README. A plain repository path such as `docs/media/explainer-web.mp4` is shown as a link, not as a player. Keep the file in the repo anyway so the attachment can be regenerated after a re-render.

Current upload: `https://github.com/user-attachments/assets/00286df3-c81d-45ca-8a78-c0c2d01a4ce9` (also stored in `github-video-url.txt`) — this is the URL referenced by the root `README.md` "Demo video" section; after a re-render, upload the new `explainer-web.mp4`, then update both places.

## What the video says

Ten frames, ~123 s. The narration is locked in `explainer/SCRIPT.md`; on-screen copy is short kinetic text, the spoken words appear as captions.

| # | Frame | On screen | Narration |
|---|---|---|---|
| 1 | The moment | Date ledger: Anthropic publishes the blueprint · "One day later." · "This is Shopware's." with a green `● RUNNING` status tag | September 2nd, 2026. Anthropic publishes an open-source blueprint for commerce agents. One day later — this is Shopware's implementation. Running. |
| 2 | Not a Claude shop | "Not a Claude shop." struck through → "Shopware is the commerce execution layer — for any agent." | This is not a Claude shop. It's Shopware as the commerce execution layer — the system any agent runs on. |
| 3 | Two agents | Two cards: shopping agent (search → compare → real cart → hand off to Shopware checkout), merchant agent (analyze → stage → human approves → apply) | Two agents ship in the box. A shopping agent — search, compare, build a real cart, hand off to Shopware checkout. And a merchant agent — analyze, stage a change, a human approves — then it's applied. |
| 4 | How it's wired | Animated diagram (MASTERPLAN §4.1): Claude → `anthropics/commerce-agents` (pinned @ fd4d5922, 0 changes) → `storefront/api` + `merchant/api` under the label `github.com/sthamann/shopware_claude_commerce` → Shopware band with `/.well-known/ucp`, `/ucp/mcp`, `/ucp/v1/*`, `/api/_mcp`, `/api/search/*`, `dryRun=true` | Here's the wiring. Anthropic's blueprint packages — pinned, unmodified. Two thin Shopware backends. Shoppers go through UCP — discovery, then MCP. Merchants go through the Admin API and MCP — with dry-run previews computed on the server. |
| 5 | One curl | Terminal: `curl -s http://localhost:8080/.well-known/ucp \| jq .` streams the live discovery document (version 2026-04-08, transports rest/mcp/embedded, capabilities, ES256 signing keys) | One curl to the well-known endpoint, and Shopware announces what it speaks — catalog, cart, checkout, order, identity linking — and the keys it signs with. |
| 6 | Three advantages | Cards 01 Native UCP · 02 Dry-run previews (`before 29.99 → after 27.99`, `dryRun=true`) · 03 Commerce semantics (promotions, rules, variants, price disclosures) | Three things Shopware brings that a bolt-on can't. Native UCP — discovery, signatures, identity linking. Dry-run previews — straight from the core. And commerce semantics where they belong — promotions, rules, variants, price disclosures. |
| 7 | The model proposes | Statement relay: "Enforced. Not prompted." / "The model proposes." / "A person — or a policy — applies." / "Provenance gates: only IDs this session has seen." / "Checkout completes in Shopware. Never in the agent." | The rules are enforced, not prompted. The model proposes. A person — or a policy — applies. Provenance gates accept only IDs the session has seen. And checkout completes in Shopware — never in the agent. |
| 8 | Demo: shop to checkout | Real screenshots of `localhost:3005` (grid + assistant rail, cart drawer with "Check out on Shopware") and the real Shopware checkout showing the same cart (CA-TSHIRT ×2, €59.98) | Watch it run. Search the live catalog. Add to a real Shopware cart. Then — Check out on Shopware. Same cart, same total — in the shop's own checkout. |
| 9 | Demo: stage, approve, apply | `stage_price_update(...)` → StagedChange card (target/field/before/after, `dryRun=true` preview, guardrails ok) → host log: PATCH not sent, 0 writes, approval required → `POST /api/merchant/changes/{id}/apply` → 200, applied | On the merchant side — a price change is staged. Before and after, previewed by the server. Nothing touches the shop until someone approves. Then one call applies it. |
| 10 | Commerce Operating System | "Shopware is the Commerce Operating System for the Agent Economy." · `github.com/sthamann/shopware_claude_commerce` with an `MIT` pill · terminal typing the five README commands | Shopware is the Commerce Operating System for the Agent Economy. The repository link is in the description. Five commands — and it runs. |

Notes on the footage:

- Frames 8 uses real captures of the running stack (2026-09-03). The assistant chat turn inside the rail is an HTML overlay labelled `recreation` (the local deployment has no `ANTHROPIC_API_KEY`, so no real chat reply could be captured).
- Frame 9 is an HTML build using the real `StagedChange.items[] {target, field, before, after}` shape and route names; the price values are illustrative (labelled `example values · seeded catalog`). This version ships the merchant host as an API without a web UI, so there was no portal to capture.
- Frame 5's JSON is the live `/.well-known/ucp` response, condensed to fit (`capture/extracted/ucp-discovery.json` holds the full document).

## Re-render

Everything runs from `docs/media/explainer/` with the HyperFrames CLI (`hyperframes@0.8.27` pinned in `package.json`). Fonts (Inter, JetBrains Mono — OFL) are staged in `assets/fonts/`, narration in `assets/voice/`, the music bed in `assets/bgm/track.wav`, so a re-render needs no network beyond the GSAP CDN used by the assembled `index.html`.

```bash
cd docs/media/explainer

# 1. Validate the assembled composition
npx hyperframes lint
npx hyperframes check

# 2. Render (≈50 s on an M-series Mac) and publish the deliverable
npx hyperframes render --skill=product-launch-video --quality high --output renders/video.mp4
cp renders/video.mp4 ../explainer.mp4
ffmpeg -y -ss 121.4 -i ../explainer.mp4 -frames:v 1 ../explainer-poster.png

# Optional: contact sheet of frame midpoints for review
npx hyperframes snapshot --at 5.8,15.4,25.7,41,54.8,67.6,82.4,94.2,104.5,116.2
```

### Changing a frame

Frames are sub-compositions in `compositions/frames/NN-*.html` (one file per storyboard frame, GSAP timeline registered under the frame id). Edit the file, then re-run `lint` / `check` / `render`. If a frame's *duration* changes you must re-assemble and re-inject transitions:

```bash
SK=$(realpath ~/.cursor/skills/product-launch-video)   # workflow scripts (symlinked from ~/.claude/skills)
node $SK/scripts/assemble-index.mjs --storyboard ./STORYBOARD.md --hyperframes .
node $SK/scripts/transitions.mjs inject --storyboard ./STORYBOARD.md --hyperframes .
node $SK/scripts/transitions.mjs verify --storyboard ./STORYBOARD.md --index ./index.html
```

### Changing the narration

1. Edit the spoken lines in `SCRIPT.md` (and the matching `voiceover:` guide in `STORYBOARD.md`).
2. Regenerate the voice with Kokoro (offline; voice `bm_george`). Kokoro needs a Python with `kokoro-onnx` + `soundfile`:

```bash
python3 -m venv ~/.hyperframes-venv && ~/.hyperframes-venv/bin/pip install kokoro-onnx soundfile
export HYPERFRAMES_PYTHON=~/.hyperframes-venv/bin/python
node $SK/scripts/audio.mjs --script ./SCRIPT.md --storyboard ./STORYBOARD.md --hyperframes . \
  --out ./audio_meta.json --provider kokoro --voice bm_george
node $SK/scripts/audio.mjs sync-durations --audio-meta ./audio_meta.json --storyboard ./STORYBOARD.md
```

3. Word timings in `audio_meta.json` come from ASR and may mis-hear product names ("clawed", "ShopWear"); the captions are built from these words, so re-map them onto the script text before building captions (the original run used a small difflib alignment over `SCRIPT.md` tokens — keep the timings, replace the text).
   To regenerate a *single* line instead of all ten (as done for the hook and the close), run `npx hyperframes tts <textfile> --voice bm_george --output assets/voice/NN.wav`, then `npx hyperframes transcribe assets/voice/NN.wav --model small.en --dir <tmpdir>` for the word timings, and patch that voice's `duration_s` / `words` in `audio_meta.json` before the re-map. The last line (`10.wav`) carries 3.5 s of appended silence (`ffmpeg -af apad=pad_dur=3.5`) for the closing hold.
4. Rebuild captions, update the frame `data-duration`s to the synced values, then assemble / inject / render as above. If the total length changes, re-trim the music bed to the new total with a fresh 3.5 s fade-out (`ffmpeg -af "atrim=0:<total>,afade=t=out:st=<total-3.5>:d=3.5"`):

```bash
node $SK/scripts/captions.mjs build --storyboard ./STORYBOARD.md --audio-meta ./audio_meta.json --hyperframes . --out ./caption_groups.json
```

### Music bed

`assets/bgm/track.wav` was generated locally with MusicGen (`facebook/musicgen-small`, prompt: dark minimal technical electronic underscore, 96 BPM, no vocals), looped to the narration length, faded in 1.2 s / out 3.5 s, mounted at `data-volume="0.12"`. To regenerate: install `torch transformers soundfile numpy` into the same venv, put it first on `PATH`, and run the media-use audio engine with `bgm.mode = "generate"` (see `~/.cursor/skills/media-use/audio/references/bgm.md`). With a HeyGen credential the same step retrieves a licensed catalog track instead.

## Project layout (`explainer/`)

| Path | Purpose |
|---|---|
| `BRIEF.md` | the confirmed brief (route, message, destination, style notes) |
| `STORYBOARD.md` | ten frames with time-coded shot sequences and synced durations |
| `SCRIPT.md` | locked narration |
| `frame.md` | design system (code-editorial preset, inverted to the dark register; Shopware blue `#189EFF`, Claude warm `#D97757`) |
| `compositions/frames/*.html` | the ten frame sub-compositions |
| `compositions/captions.html` | generated caption track |
| `index.html` | assembled host composition (frames, voice, music, captions, transitions) |
| `assets/` | fonts, captured screenshots, voice WAVs, music bed, UCP discovery JSON |
| `capture/` | raw capture of `localhost:3005` + asset inventory (`extracted/asset-descriptions.md`) |
| `audio_meta.json` | voice/word timings + BGM entry consumed by captions and the assembler |
