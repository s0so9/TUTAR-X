---
version: 1
slug: "frontend-src-pages-matchdetailv2-tsx"
primary_target: "frontend/src/pages/MatchDetailV2.tsx"
related_targets: ["frontend/src/components/layout/AppLayout.tsx"]
---

# Surface brief — Maç detayı (match decision + live)

Scope: `/matches/:id` (pre-match decision and live on one page); the shell (nav rail, header) and the kombine slip ship with it and set the system for every other route.
Mode: Operate.
Audience & task: the two builders, desktop, match nights. In three seconds: what the model says, what the market says, whether there is credible value; one click deeper for score distribution, squad/injuries, form; add a pick to the kombine in one click; follow the score live; later see whether picks landed.
Constraints: honesty rules from PRODUCT.md ("veri yok", unverified odds labelled, MODEL_MARKET_CONFLICT is a warning, never value); Turkish copy; standard web controls; restrained, purposeful motion; never shout like a betting site.

## Direction contract

THESIS: A match is a two-sided page: home in the left column, away in the right, and a centre rail of market keys between them that carries every decision. Refuses the category default of stacked same-size cards with progress bars and neon accents.

OWN-WORLD: Inverted reference setting for match nights: iron-black stock (#161513), bone ink (#ece6d8), one vermilion rubric (#d9533b) for keys, live state and the primary action; slate-blue away series, ash draw, muted pitch-green for credible value, ochre for conflict. Every rule a 1px hairline with "+" terminals; square detents; no radius, no shadows, no gradients. Source Serif 4 throughout, tracked small caps for apparatus, tabular figures for all numbers.

STORY: The visitor reads the rail top to bottom (1·X·2, goals, KG), sees model and market side by side on each key, presses a key to open its apparatus in the margin (fair odds, market odds, edge, source), adds it to the kombine, and follows the same rail live as the score and minute take its top.

FIRST VIEWPORT: Narrow keyed nav rail at left. Header line: competition, kickoff, status. Home name large left-aligned, away name large right-aligned, the rail head between them holds kickoff time or live score. Below: rail rows for 1·X·2, 2.5, 3.5, KG with model % on each side and market % beneath; the TUTAR X seçimi and kombine sit in the right annotation margin. Signature move: the centre rail of keys; pressing one fills its detent and slides its apparatus open on a single damped axis.

FORM: Centre-rail reference setting (catalog challenger, chosen by the user over the roll); seed key b966a4b5. Raises carried: live timeline at exact minutes (labanotation), every number one click from its source (monochrome), one tabular numeral face (ikeda).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
