---
format: 1920x1080
duration: 120s
message: "Shopware is the Commerce Operating System for the Agent Economy — the Anthropic commerce-agent blueprint runs on it unmodified."
arc: Future Pacing with feature-benefit progression — hook (the moment) → name the idea → the two agents → mechanism (wiring, discovery) → advantages → safety → proof (two demos) → CTA
audience: developers, Shopware partners, the Anthropic / agentic-commerce ecosystem
mode: autonomous
music: dark minimal technical electronic underscore, steady pulse, no drums until late, confident
language: en
---

## Video direction

- **Palette system (from `frame.md`, inverted register):** ground = `cream` `#0B1220` on every frame (painted as a full-duration background clip); half-step surfaces `tile` `#111A2E` / `tile-strong` `#1B2740` for cards and panels; text = `ink` `#F3F6FA`, secondary text `muted` `#8A94A6`; the ONE voltage per frame = `coral` = Shopware blue `#189EFF` (a rule, an underline, a kicker ✱, a CTA, or one highlighted word); `warm` `#D97757` only marks the Claude / Anthropic / blueprint side of a diagram or one word — never a fill, never beside the blue on the same element. Terminal / code surfaces sit on `navy` `#060B16` with a `navy-elev` `#141F36` title bar and an ink@14% hairline. Syntax: keys in `ink`, strings teal `#5DB8A6`, numbers amber `#E8A55A`, success `#5DB872`. Hairline 1px ink@12% is the only border; one soft dark shadow max on floating windows. A faint 1px grid (ink@4%, 96px cells) may sit on the ground for the terminal/diagram aesthetic — static, never animated.
- **Type by role:** `display` / `headline` Inter 400 sentence case, negative tracking, for every statement; `kicker` JetBrains Mono uppercase 0.16em with the blue ✱ opens each frame's region; `code` JetBrains Mono for terminals, endpoints, JSON, repo names; `body` / `lead` Inter 400. Weights 400 and 700 only. Legibility floor 1.4cqw for load-bearing text.
- **Motion grammar + reveal model:** long-tail `power3` settles (`expo.out` on a fast arrival); no overshoot, no bounce. Every frame reveals on the VO: at t=0 only what the voice is saying; each further element enters on its spoken cue, most of them in the back half; the final window is a held read. During a hold: stillness, or subtle jitter / a live SVG internal at most — no breathing, no back-half pan or push. Entrances are `fromTo`; internal seams are velocity-matched cuts (`cut-catalog.md`). Between-frame transitions are story's `transition_in`, injected by the harness.
- **Rhythm / held frames:** Frame 2 (statement) and Frame 7 (safety) are the deliberate held reads — few elements, long holds; Frame 10 holds its lockup for the tail. Frames 4, 5, 8, 9 are the dense, continuously developing shots.
- **Caption band:** bottom ~17% (below y≈896px) stays clear on every frame; content lives in the top ~83%.
- **Negative list:** no pure white / pure black grounds, no purple-blue "AI" gradients, bokeh, glows over 0.45 opacity, or decorative shapes standing in for a real asset; no browser chrome, real cursors, scrollbars, nav bars; no slideshow (front-load then freeze) and no screensaver (elements floating independently); no `repeat: -1`, no `Math.random`, no CSS transitions on animated elements; no fabricated numbers — every figure on screen traces to the repo or the captured shop (prices, totals, endpoint names, capability names, version `2026-04-08`).

## Frame 1 — The moment

- scene: Kinetic date line — "September 2, 2026" — then three claims stack: Anthropic publishes the blueprint · One day later. · "This is Shopware's." with a green `● RUNNING` status tag.
- voiceover: "September 2nd, 2026. Anthropic publishes an open-source blueprint for commerce agents. One day later — this is Shopware's implementation. Running."
- duration: 11.584s
- transition_in: cut
- status: animated
- src: compositions/frames/01-the-moment.html
- type: hook
- persuasion: Urgency by association — a dated industry moment the viewer already knows, resolved on "this is ours"
- beat: tension → intrigue
- blueprint: kinetic-type-beats (Adapt)
- focal: (typography-only)
- roles: none
- sfx: none

narrativeRole: Plant the stakes in outcome language (a race is on; Shopware answered) before any technology appears.
keyMessage: The blueprint is real, the race is on, and Shopware has an implementation.

Adapt: keep the signature — the words ARE the motion, each claim landing as its own full-frame beat by hard cut — but the beats stack into a left-aligned ledger instead of swapping in place, so the three claims can be read together when the payoff lands.
Scene 1 (0.0–1.6s): ground only, faint static grid. A mono kicker `✱ 2026-09-02` sits upper-left; the date "September 2, 2026" enters as `display` via **per-word staggered reveal** (`waterfall-entry`, word granularity) with a long-tail settle — left-aligned, upper third, ~60% width; nothing else on screen.
Scene 2 (3.2–7.3s): as the voice says "Anthropic publishes", the date shrinks to `headline` scale and rises (a velocity-matched slow-fast-slow nudge, power3); line 1 "Anthropic publishes an open-source blueprint for commerce agents." arrives as a **waterfall entry** (`waterfall-entry`) beneath it, `headline` size, with a small `warm` word-mark tag "anthropics/commerce-agents" in mono to its right — the only warm element of the frame.
Scene 3 (7.3–8.6s): on "One day later", line 2 "One day later." waterfalls in under line 1 (`waterfall-entry`); a thin ink@20% **section rule draws on** between the lines (`svg-path-draw`). Ledger layout, asymmetric 70/30, the right 30% empty.
Scene 4 (8.6–11.6s): on "this is Shopware's implementation", lines 1–2 dim to `muted`; line 3 "This is Shopware's." slams in at `display` scale (a single scale-slam arrival via `waterfall-entry`, no overshoot) and a **blue underline draws on** beneath "Shopware's" (`svg-path-draw`, `coral`) — the frame's one voltage. On "Running." a small mono status tag `● RUNNING` (success green `#5DB872`) lands to the right of the underline. Hold still to the cut.

## Frame 2 — Not a Claude shop

- scene: A single statement builds: "Not a Claude shop." strikes through → "Shopware is the commerce execution layer any agent runs on." Blue underline draws on under "execution layer".
- voiceover: "This is not a Claude shop. It's Shopware as the commerce execution layer — the system any agent runs on."
- duration: 7.275s
- transition_in: crossfade
- status: animated
- src: compositions/frames/02-execution-layer.html
- type: product_intro
- persuasion: Negative contrast — reject the obvious framing, then name the real one
- beat: clarity
- blueprint: kinetic-type-beats (Reproduce)
- focal: (typography-only)
- roles: none
- sfx: none

narrativeRole: Land the message (the brief's `message`) by beat 2; everything after is evidence.
keyMessage: Shopware is the execution layer, not another chatbot storefront.

Held read. Two statements, centered, one strike-through, one underline.
Scene 1 (0.0–2.4s): ground + grid. Kicker `✱ THE IDEA`. "Not a Claude shop." enters centered as `display-italic` via **per-word staggered reveal** (`waterfall-entry`, word granularity); on "not" a **strike-through line draws on** through the words in `muted` (`svg-path-draw`) — rejection read.
Scene 2 (2.4–5.6s): the struck line **nudges** up (slow-fast-slow, power3) and dims to `muted` at `headline` size; as the voice says "Shopware as the commerce execution layer", the statement "Shopware is the commerce execution layer" arrives centered at `display` scale via **waterfall entry** (`waterfall-entry`); centered template, ~70% width, upper-middle.
Scene 3 (5.6–8.0s): on "any agent runs on", the tail "— any agent runs on." waterfalls in as the second line; a **blue underline draws on** under "execution layer" (`svg-path-draw`, `coral`). Hold, still.

## Frame 3 — Two agents

- scene: Two columns open like a book: SHOPPING AGENT (search → compare → real cart → hand off to Shopware checkout) and MERCHANT AGENT (analyze → stage change → human approves → apply). Steps light up as the voice names them.
- voiceover: "Two agents ship in the box. A shopping agent — search, compare, build a real cart, hand off to Shopware checkout. And a merchant agent — analyze, stage a change, a human approves — then it's applied."
- duration: 13.163s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/03-two-agents.html
- type: feature_showcase
- persuasion: Rule of two — two complementary capabilities weighed at once
- beat: clarity + control
- blueprint: comparison-split (Adapt)
- focal: (typography-only)
- roles: none
- sfx: none

narrativeRole: Introduce the two products the repo ships, each as a four-step loop the viewer can hold in mind.
keyMessage: One repo, two agents: shopper-facing and merchant-facing, both ending in Shopware.

Adapt: keep the signature — two equal-weight cards entering from opposite wings with mirrored book-open tilts (`split-tilt-cards`) — but the inner-edge badge becomes the mono kicker on each card, and the cards' contents (four steps each) reveal one by one on the VO instead of arriving filled; no continuous float after the settle.
Scene 1 (0.0–1.8s): ground + grid; kicker `✱ TWO AGENTS` upper-left; headline "Two agents ship in the box." enters upper-third via **per-word staggered reveal** (`dynamic-content-sequencing`), then **nudges** up-left to `card-title` scale as the cards need the room (`nudge-curve`).
Scene 2 (1.8–3.0s): on "A shopping agent", the LEFT card (tile surface, hairline, 12px radius) slides in from the left wing with a mirrored rotateY tilt and settles flat (`split-tilt-cards`, entry only); its kicker `✱ SHOPPING AGENT` and a mono sub-label `storefront/api · UCP` are the only content. Split-screen, each card ~42% width, centered vertically in the safe area.
Scene 3 (3.0–6.4s): four step rows reveal in the left card, one per spoken cue — "search" · "compare" · "build a real cart" · "hand off to Shopware checkout" — each a **staggered reveal** row with a mono index 01–04 (`dynamic-content-sequencing`); a thin connector ticks down between rows (`svg-path-draw`). Row 04 carries the frame's one blue: the word "Shopware" in `coral`.
Scene 4 (6.4–7.6s): on "And a merchant agent", the RIGHT card enters from the right wing with the opposite tilt (`split-tilt-cards`) — kicker `✱ MERCHANT AGENT`, sub-label `merchant/api · Admin API / MCP`.
Scene 5 (7.6–11.6s): four step rows reveal in the right card on the cues — "analyze" · "stage a change" · "a human approves" · "apply" — same row treatment; row 03 "a human approves" gets a small hairline pill "approval gate" in `muted`.
Scene 6 (11.6–13.0s): both cards hold; a **section rule draws on** across the bottom of both cards with the mono label `both end in Shopware` centered (`svg-path-draw`). Still.

## Frame 4 — How it's wired

- scene: Animated architecture diagram (from MASTERPLAN §4.1) draws top-down: Claude → `anthropics/commerce-agents` (pinned, unmodified) → `storefront/api` + `merchant/api` (thin backends) → the SHOPWARE band with `/.well-known/ucp`, `/ucp/mcp`, `/api/_mcp`, `dryRun=true`. Connectors draw as the voice names each layer.
- voiceover: "Here's the wiring. Anthropic's blueprint packages — pinned, unmodified. Two thin Shopware backends. Shoppers go through UCP — discovery, then MCP. Merchants go through the Admin API and MCP — with dry-run previews computed on the server."
- duration: 17.451s
- transition_in: crossfade
- status: animated
- src: compositions/frames/04-wiring.html
- type: feature_showcase
- persuasion: Show-don't-tell mechanism — the real layer names and endpoints, drawn in the order the request travels
- beat: trust
- blueprint: spatial-pan-stations (Adapt)
- focal: (diagram, typography-only)
- roles: none
- sfx: none

narrativeRole: The mechanism beat: prove "runs unmodified" with the actual package/endpoint topology.
keyMessage: Blueprint untouched on top, thin adapters in the middle, Shopware surfaces underneath.

Adapt: keep the signature — labeled stations on one canvas revealed in traversal order with callouts — but the camera stays locked (a vertical diagram fits the frame) and the traversal is the **connector drawing on** top-down (`svg-path-draw`) from station to station; each station reveals on its cue.
Scene 1 (0.0–1.4s): ground + grid; kicker `✱ HOW IT'S WIRED` upper-left; only the TOP station appears: a small hairline pill "Claude" (Messages API · Agent SDK) centered in the upper band, with a `warm` dot — the frame's only warm.
Scene 2 (1.4–4.6s): on "Anthropic's blueprint packages", a connector draws down (`svg-path-draw`) into station 2: a wide tile card `anthropics/commerce-agents` with two mono chips `shopping_agent · StorefrontBackend` and `merchant_agent · MerchantBackend`; on "pinned, unmodified" a mono badge `pinned @ fd4d5922 · 0 changes` **spring-pops** in on its right edge (`spring-pop-entrance`, smooth settle). Layout: vertical stack, centered, ~72% width, four bands within the safe area.
Scene 3 (4.6–7.0s): on "Two thin Shopware backends", two connectors draw down in parallel (`svg-path-draw`) into two side-by-side tile cards: `storefront/api` (mono: `ucp_client.py · shopware_backend.py`) and `merchant/api` (mono: `admin_transport.py · staging.py`), both under the mono label `github.com/sthamann/shopware_claude_commerce`. Reveal left then right via **staggered reveal** (`dynamic-content-sequencing`).
Scene 4 (7.0–10.4s): on "Shoppers go through UCP — discovery, then MCP", the LEFT connector draws down into the SHOPWARE band (a wide `tile-strong` card with a **blue hairline top rule** — the frame's one blue, drawn on with `svg-path-draw`) and two endpoint chips light up in order on their cues: `/.well-known/ucp` then `/ucp/mcp` (**keyword glow** on each chip as named → `asr-keyword-glow`).
Scene 5 (10.4–13.6s): on "Merchants go through the Admin API and MCP", the RIGHT connector draws down into the same band; chips `/api/_mcp` and `/api/search/*` light in order; on "dry-run previews" a chip `dryRun=true` glows and a mono callout `preview computed server-side` **spring-pops** beside it (`spring-pop-entrance`).
Scene 6 (13.6–15.0s): the band label "SHOPWARE 6.7" (mono, kicker style) fades up at the band's left; the whole diagram holds still.

## Frame 5 — One curl

- scene: Terminal surface. `curl -s http://localhost:8080/.well-known/ucp` types in; the live discovery JSON streams back — version, transports rest/mcp/embedded, capabilities catalog · cart · checkout · discount · order · identity_linking, ES256 signing keys. Capability names highlight as spoken.
- voiceover: "One curl to the well-known endpoint, and Shopware announces what it speaks — catalog, cart, checkout, order, identity linking — and the keys it signs with."
- duration: 10.069s
- transition_in: crossfade
- status: animated
- src: compositions/frames/05-curl-ucp.html
- type: feature_showcase
- persuasion: Show-don't-tell proof — real output from the running shop
- beat: confidence
- blueprint: prompt-type-submit-generate (Reproduce)
- focal: assets/ucp-discovery.json
- roles: ucp-discovery.json = supporting (source text for the streamed JSON; rendered as typed code, not embedded as a file)
- sfx: none
- asset_candidates: assets/ucp-discovery.json — live discovery document from the running Shopware (source text for the streamed JSON)

narrativeRole: One concrete, verifiable proof of "native UCP" — the viewer could run this line.
keyMessage: Discovery is live, standard, and signed.

Reproduce: the command types into a real terminal surface, the machine answers, the answer streams in.
Scene 1 (0.0–2.2s): ground + grid; a terminal `code-surface` (navy body, `navy-elev` title bar reading `shopware — zsh`, ink@14% hairline, 8px radius) sits centered at ~78% width, ~62% height, top-aligned in the safe area; a `$` prompt with a **blinking caret** (`context-sensitive-cursor`); the command `curl -s http://localhost:8080/.well-known/ucp | jq .ucp` **types on** (`discrete-text-sequence`) at a human pace and lands as "One curl" is said.
Scene 2 (2.2–3.4s): on "Shopware announces", the caret drops a line and the JSON begins to **stream** line-by-line (`dynamic-content-sequencing`, binary reveals — never fades): `"version": "2026-04-08"` (amber number-like string treated as a value), `"services": { "dev.ucp.shopping": [ rest · mcp · embedded ] }` collapsed to three transport lines with their endpoints (`/ucp/v1`, `/ucp/mcp`, `/ucp/embedded`).
Scene 3 (3.4–7.4s): the `"capabilities"` block streams in — one key per spoken cue: `dev.ucp.shopping.catalog` · `.cart` · `.checkout` · `.order` · `dev.ucp.common.identity_linking` (+ `.discount` appearing between checkout and order without emphasis) — each line arriving as the word is spoken and receiving a `coral` keyword highlight (color + slight scale on its `dynamic-content-sequencing` window) — the blue is the highlighted key only.
Scene 4 (7.4–10.0s): on "the keys it signs with", the panel **scrolls up** one step (a translateY step on the code body, power3) to reveal `"signing_keys": [{ "kid": "default", "kty": "EC", "alg": "ES256", "crv": "P-256" }, { "kid": "key-20260903084820", … }]`; a mono status strip at the panel foot reads `200 OK · application/json · signature-policy=log`. Hold with the caret blinking.

## Frame 6 — Three advantages

- scene: Three cards assemble left→right with mono kickers 01 · 02 · 03: NATIVE UCP (discovery · signatures · identity linking) — DRY-RUN PREVIEWS from the core (`dryRun=true` → before/after) — COMMERCE SEMANTICS in the core (promotions · rules · variants · price disclosures). Each card lands as named.
- voiceover: "Three things Shopware brings that a bolt-on can't. Native UCP — discovery, signatures, identity linking. Dry-run previews — straight from the core. And commerce semantics where they belong — promotions, rules, variants, price disclosures."
- duration: 15.744s
- transition_in: push-slide LEFT
- status: animated
- src: compositions/frames/06-three-advantages.html
- type: benefit_highlight
- persuasion: Rule of three + feature-to-benefit translation (structural advantages a competitor cannot bolt on)
- beat: confidence → aspiration
- blueprint: grid-card-assemble (Reproduce)
- focal: (typography-only)
- roles: none
- sfx: none

narrativeRole: Turn the mechanism into the "why Shopware" argument from MASTERPLAN §0.
keyMessage: UCP, dry-run, and commerce semantics are in the core — that is the differentiator.

Reproduce: N=3 cards self-assemble in a staggered cascade into a triptych and hold; each card's sub-items cascade in on the VO.
Scene 1 (0.0–2.4s): ground + grid; kicker `✱ THREE ADVANTAGES`; headline "Three things Shopware brings that a bolt-on can't." enters upper-third via **per-word staggered reveal** (`dynamic-content-sequencing`), then **nudges** up to `card-title` scale (`nudge-curve`). Nothing else.
Scene 2 (2.4–5.8s): on "Native UCP", card 01 rises into the left third (tile surface, hairline, 12px radius; mono index `01`, title "Native UCP" at `card-title`) via **spring-pop entrance** with a smooth settle (`spring-pop-entrance`); its three rows "discovery" · "signatures (RFC 9421)" · "identity linking (OAuth)" cascade in on the cues (`dynamic-content-sequencing`). Triptych, three equal columns, cards ~28% width each, ~55% height.
Scene 3 (5.8–8.6s): on "Dry-run previews", card 02 rises into the center column; a tiny mono diff `before 29.99 → after 27.99` and a chip `dryRun=true` cascade in under "straight from the core". The chip is the frame's one blue (`coral` text on a blue@12% fill).
Scene 4 (8.6–12.8s): on "commerce semantics", card 03 rises into the right column; rows "promotions" · "rules" · "variants" · "price disclosures (PAngV)" cascade in on each spoken cue.
Scene 5 (12.8–14.0s): a **section rule draws on** under the three cards (`svg-path-draw`) with the mono label `in the core — not bolted on`. Hold still.

## Frame 7 — The model proposes

- scene: Kinetic statements on a bare ground: "The model proposes." / "A person — or a policy — applies." / "Provenance gates: only IDs this session has seen." / "Checkout completes in Shopware. Never in the agent." Each lands alone; the last holds.
- voiceover: "The rules are enforced, not prompted. The model proposes. A person — or a policy — applies. Provenance gates accept only IDs the session has seen. And checkout completes in Shopware — never in the agent."
- duration: 13.696s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/07-safety.html
- type: benefit_highlight
- persuasion: Risk reversal — name the failure modes the architecture makes impossible
- beat: peace of mind
- blueprint: kinetic-type-beats (Reproduce)
- focal: (typography-only)
- roles: none
- sfx: none

narrativeRole: Address the objection every merchant has about agents: who is allowed to change what.
keyMessage: Enforcement lives in the harness and in Shopware, not in a prompt.

Reproduce: a statement relay — each line lands alone at center by hard cut and holds ~1.5s+, resolving on a locked finale. Held read; the slowest frame in the film.
Scene 1 (0.0–2.2s): ground, no grid (the bare canvas is the point); kicker `✱ ENFORCED, NOT PROMPTED` centered above; line A "Enforced. Not prompted." lands centered at `display` via a scale-slam arrival (`discrete-text-sequence` state 1, scale 1.08→1 on power3, no overshoot).
Scene 2 (2.2–4.4s): **hard-cut word-swap** (`discrete-text-sequence`): line A is replaced by "The model proposes." — same position, `display`.
Scene 3 (4.4–7.0s): hard cut to "A person — or a policy — applies."; on "policy" a small mono chip `Rule Builder · Flow Builder` fades up beneath in `muted`.
Scene 4 (7.0–9.8s): hard cut to "Provenance gates: only IDs this session has seen." at `headline` scale (longer line, fit to measure); a thin hairline frame draws around it (`svg-path-draw`) — a gate.
Scene 5 (9.8–13.0s): hard cut to the finale, two lines: "Checkout completes in Shopware." / "Never in the agent." — "Never" in `coral`, the frame's one blue. Locked finale; hold still to the transition.

## Frame 8 — Demo: shop to checkout

- scene: Captured screens held as hero in a floating window: the product grid with the assistant rail → a search/compare turn appears in the rail (HTML recreation, labelled) → the cart drawer opens with the T-Shirt and "Check out on Shopware" → cut to the real Shopware checkout showing the same cart (CA-TSHIRT, €59.98).
- voiceover: "Watch it run. Search the live catalog. Add to a real Shopware cart. Then — Check out on Shopware. Same cart, same total — in the shop's own checkout."
- duration: 9.92s
- transition_in: crossfade
- status: animated
- src: compositions/frames/08-demo-shopping.html
- type: feature_showcase
- persuasion: Show-don't-tell proof on real screens
- beat: excitement → trust
- blueprint: device-surface-showcase (Adapt)
- focal: assets/ui-cart-open.png
- roles: ui-grid-cart.png = cutout (the floating window's first screen) · ui-cart-open.png = cutout (second screen, the hero) · shopware-checkout.png = cutout (third screen, the payoff)
- sfx: none
- asset_candidates: assets/ui-grid-cart.png — shopping UI with product grid and assistant rail; assets/ui-cart-open.png — cart drawer with Claude Commerce T-Shirt and "Check out on Shopware"; assets/shopware-checkout.png — real Shopware checkout with the same cart (CA-TSHIRT, €59.98)

narrativeRole: The shopping proof: the loop from Frame 3 on real screens, ending in Shopware.
keyMessage: The cart the agent built is the cart Shopware checks out.

Adapt: keep the signature — a floating window held as hero while its screens cycle through a real flow, cursorless — with the three captured screenshots as the screens; the "agent turn" in the rail is a small HTML overlay card labelled `recreation` in mono (no fabricated screenshot). Camera: one push-in onto the cart drawer at the handoff, then a hard cut to the checkout screen.
Scene 1 (0.0–2.6s): ground + grid; kicker `✱ DEMO · SHOPPING AGENT` upper-left; a floating window (8px radius, hairline, one soft shadow; window ~76% width, centered slightly right, top-aligned in the safe area) **spring-pops** in with a smooth settle (`spring-pop-entrance`) showing `ui-grid-cart.png` (the grid + assistant rail). Mono label above the window: `localhost:3005 · storefront/web`.
Scene 2 (2.6–5.4s): on "Search the live catalog", a compact HTML card **rises** into the assistant-rail area of the window (`waterfall-entry`): user line "Find me a gift under 50 €." then an agent line "Two options under 50 €: Claude Commerce T-Shirt €29.99 · Extra Virgin Olive Oil 500 ml €12.90" with a tiny mono tag `recreation`; on "Add to a real Shopware cart" a `coral` hairline highlight ring **draws on** around the T-Shirt card in the grid (`svg-path-draw`).
Scene 3 (5.4–8.6s): hard cut inside the window (**cut-the-curve**, `cut-catalog.md`) to `ui-cart-open.png`; the camera **zooms to target** on the cart drawer's lower half (`coordinate-target-zoom`) so "Cart · 2 items · Claude Commerce T-Shirt · Subtotal €59.98" reads; on "Check out on Shopware" a **blue hairline ring draws on** around the "Check out on Shopware" button (`svg-path-draw`, `coral`) — the frame's one blue.
Scene 4 (8.6–13.0s): on "Same cart, same total", **inverse zoom-through** (`cut-catalog.md`) to `shopware-checkout.png` filling the window; a mono label above the window swaps to `localhost:8080 · Shopware checkout`; two hairline callouts fade up pointing at "Grand total €59.98" and "CA-TSHIRT · Quantity 2" (`svg-path-draw` for the leader lines, text arriving as binary reveals). Hold still.

## Frame 9 — Demo: stage, approve, apply

- scene: A staged-change card builds in a dark panel: `stage_price_update` → items {target: Claude Commerce T-Shirt · field: price · before: 29.99 · after: 27.99} with a "preview: dryRun=true" chip → status "pending approval" → an approve action fires → `POST /api/merchant/changes/{id}/apply` → status flips to "applied". No chat, no cursor: the state mutation is the demo.
- voiceover: "On the merchant side — a price change is staged. Before and after, previewed by the server. Nothing touches the shop until someone approves. Then one call applies it."
- duration: 10.88s
- transition_in: push-slide LEFT
- status: animated
- src: compositions/frames/09-demo-merchant.html
- type: feature_showcase
- persuasion: Show-don't-tell of the approval gate itself
- beat: control
- blueprint: agent-progress-theater (Adapt)
- focal: (HTML-built staged-change card)
- roles: none
- sfx: none

narrativeRole: The merchant proof: stage → preview → approve → apply, using the real change shape and route name.
keyMessage: Staging writes nothing; only an approved apply writes.

Adapt: keep the signature — a trigger hands the frame to the machine, status theater, then a receipt whose rows check off — but the trigger is the `stage_price_update` call (typed as a mono line, no cursor) and the receipt is one StagedChange card whose status pill flips `staged → pending approval → applied`. Values are illustrative but plausible for the seeded catalog (T-Shirt 29.99 → 27.99) and labelled `example` in mono.
Scene 1 (0.0–2.2s): ground + grid; kicker `✱ DEMO · MERCHANT AGENT` upper-left; a mono call line **types on** (`discrete-text-sequence`) at upper-left: `stage_price_update(listing="Claude Commerce T-Shirt", price=27.99)`; below, an empty `tile` panel (≈60% width, left-of-center) with a status strip reading `staging…` and a working indicator (three dots stepping — finite `dynamic-content-sequencing`, not a loop).
Scene 2 (2.2–5.6s): on "Before and after, previewed by the server", the panel fills as a **receipt cascade** (`dynamic-content-sequencing`, rows land one by one): header `StagedChange · kind: price_update`; row `target  Claude Commerce T-Shirt`; row `field   price`; row `before  29.99 EUR` (amber) ; row `after   27.99 EUR` (amber) with a `tile-strong` highlight sweep behind the after value (scaleX 0→1 on power3); chip `preview: dryRun=true · shopware-entity-upsert` fades up at the row's right. Status pill flips to `pending approval` (`muted`).
Scene 3 (5.6–8.6s): on "Nothing touches the shop until someone approves", a right-hand mono log column (~30% width) reveals three lines in cascade: `PATCH /api/product/{id}   — not sent`, `ledger: staged, 0 writes`, `approval: required (host)`; a hairline gate icon **draws on** between panel and log (`svg-path-draw`).
Scene 4 (8.6–12.0s): on "Then one call applies it", the log column gets `POST /api/merchant/changes/{id}/apply` typed on (`discrete-text-sequence`), then `PATCH /api/product/{id}  200` and `ledger: applied`; the status pill flips to `applied` in success green `#5DB872` and the panel's top hairline turns `coral` (**rule draws on**, `svg-path-draw`) — the frame's one blue. Hold still.

## Frame 10 — Commerce Operating System

- scene: Statement lands — "Shopware is the Commerce Operating System for the Agent Economy." — then the repo lockup `github.com/sthamann/shopware_claude_commerce` (on screen only; the voice points to the link in the description) and a terminal pill types the five-command quick start (docker compose up · bootstrap · venv + pip · env · uvicorn). Holds on the lockup.
- voiceover: "Shopware is the Commerce Operating System for the Agent Economy. The repository link is in the description. Five commands — and it runs."
- duration: 12.801s
- transition_in: zoom-through
- status: animated
- src: compositions/frames/10-close.html
- type: cta
- persuasion: Friction reduction — the whole install fits on one screen
- beat: inevitability → motivation
- blueprint: prompt-type-submit-generate (Adapt)
- focal: (typography + terminal)
- roles: none
- sfx: none

narrativeRole: Land the thesis line verbatim, then hand over the concrete next action.
keyMessage: The tagline, the repo, five commands.

Adapt: keep the signature of the install-command end card — the headline demotes, a terminal springs in, the commands type and hold with a blinking caret — with five commands instead of one, typed in cascade, and the thesis line as the headline.
Scene 1 (0.0–4.2s): ground + grid; kicker `✱ SHOPWARE × CLAUDE COMMERCE AGENTS` centered; the thesis "Shopware is the Commerce Operating System for the Agent Economy." enters centered at `display` via **per-word staggered reveal** (`dynamic-content-sequencing`), each word on its spoken beat; "Commerce Operating System" carries the frame's one blue (`coral`). Hold briefly.
Scene 2 (4.4–6.6s): on "The repository link", the thesis **nudges** up to `headline` scale (slow-fast-slow, power3); a mono lockup `github.com/sthamann/shopware_claude_commerce` with a hairline pill `MIT` **spring-pops** beneath it (`spring-pop-entrance`, smooth settle).
Scene 3 (6.6–12.0s): on "Five commands", a terminal pill (`code-surface`, ~70% width, centered, upper-middle so the caption band stays clear) springs in; the five README commands **type on** in cascade (`discrete-text-sequence`), one per line, each with a `$` prompt: `docker compose -f docker/compose.yaml up -d` · `./docker/bootstrap.sh` · `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt` · `cp .env.example .env && cat docker/.generated.env >> .env` · `uvicorn storefront.api.main:app --port 8004`; a status line `→ http://localhost:8004 · http://localhost:3005` fades up on "and it runs".
Scene 4 (12.0–12.8s): caret blinks (square-wave on timeline time); everything else still — the film's final held frame. No exit motion beyond the hold.
