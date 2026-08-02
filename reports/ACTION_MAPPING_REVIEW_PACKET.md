# Action-Mapping Review Packet

**Purpose.** Provide a human reviewer with evidence-backed *candidate* disease→action
mappings for every PlantDoc class. **Nothing here is approved.** All 28 rows are
`review_status = needs_review`; the production validator continues to reject them
for evaluation until a human sets `approved` with complete evidence. This packet
addresses audit blocker #1 (*no approved authoritative mapping*) by building the
evidence toward approval **without** auto-approving anything.

**Sources.** Every cited page was **actually fetched and content-verified** by
research agents; two rows (TYLCV, corn gray leaf spot) were additionally
spot-verified by hand. Preference order: UC IPM Pest Management Guidelines →
university extension (.edu) → EPPO. Where UC IPM has no page, the fallback is
noted. **No URL, pathogen, or management claim was fabricated;** agents logged
every failed fetch and those pages were not cited.

**Files.**
`data/mapping/action_mapping_review.csv` (this packet, with `candidate_action_class`)
and `data/mapping/action_mapping_template.csv` (production mapping — same evidence,
`review_status = needs_review`, **0 approved**).

**Action rule applied** (from `PROJECT_BRIEF.md` §3.1, as *candidates only*):
fungal/oomycete → `fungicide` · bacterial → `copper_sanitation` ·
viral → `remove_vector` · healthy → `monitor`.

| Group | Count |
|---|---|
| Ready for review (disease) | 16 |
| Ready for review (healthy → monitor, definitional) | 10 |
| Ambiguous | 2 |
| Insufficient evidence | 0 |
| Excluded / out of scope | 0 |
| **Total** | **28** |

---

## 1 · Ready for review — disease classes (16)

Pathogen identity and management both trace to the cited page. Candidate action
follows the pathogen type. A reviewer must confirm the quote against the live
page and decide approval.

| Class | Pathogen | Type | Candidate | Source (fetched) | Conf. |
|---|---|---|---|---|---|
| Apple Scab Leaf | *Venturia inaequalis* | fungal | fungicide | UC IPM — Apple/apple-scab | high |
| Apple rust leaf | *Gymnosporangium juniperi-virginianae* | fungal | fungicide | OSU CFAES cedar-apple-rust | high |
| Corn Gray leaf spot | *Cercospora zeae-maydis* | fungal | fungicide | OSU Ohioline PLPATH-CER-05 | high |
| Corn leaf blight | *Exserohilum turcicum* | fungal | fungicide | OSU Ohioline PLPATH-CER-10 | high |
| Corn rust leaf | *Puccinia sorghi* | fungal | fungicide | UC IPM — Corn/common rust | high |
| Potato leaf early blight | *Alternaria solani* | fungal | fungicide | UC IPM — Potato/early-blight | high |
| Potato leaf late blight | *Phytophthora infestans* | **oomycete** | fungicide | UC IPM — Potato/late-blight | high |
| Squash Powdery mildew leaf | *Podosphaera xanthii* | fungal | fungicide | UC IPM — Cucurbits/powdery-mildew | high |
| grape leaf black rot | *Guignardia bidwellii* | fungal | fungicide | OSU Ohioline PLPATH-FRU-24 | high |
| Tomato Early blight leaf | *Alternaria solani* | fungal | fungicide | UC IPM — Tomato/early-blight | high |
| Tomato Septoria leaf spot | *Septoria lycopersici* | fungal | fungicide | NC State Extension | high |
| Tomato leaf bacterial spot | *Xanthomonas* pv. *vesicatoria* | bacterial | copper_sanitation | UC IPM — Tomato/bacterial-spot | high |
| Tomato leaf late blight | *Phytophthora infestans* | **oomycete** | fungicide | UC IPM — Tomato/late-blight | high |
| Tomato leaf yellow virus | TYLCV (begomovirus) | viral | remove_vector | UC IPM — Tomato/TYLCV | high |
| Tomato mold leaf | *Fulvia fulva* | fungal | fungicide | Univ. Missouri IPM | high |
| Bell_pepper leaf spot | *Xanthomonas* pv. *vesicatoria* | bacterial | copper_sanitation | UC IPM — Peppers/bacterial-spot | high |

**Reviewer notes:** (a) both late-blight rows are an **oomycete**, not a true
fungus — the brief groups oomycete with fungal for the `fungicide` action, but the
pathogen-type field must say `oomycete`. (b) Bacterial-spot xanthomonads have been
split into ~4 species in modern taxonomy; UC IPM uses the older name. (c) Three
rows fall back below UC IPM (no UC IPM page exists): Septoria (NC State), leaf mold
(Missouri IPM), and the three OSU rows — all authoritative but tier-2.

## 2 · Ready for review — healthy classes (10)

`Apple leaf`, `Bell_pepper leaf`, `Blueberry leaf`, `Cherry leaf`, `Peach leaf`,
`Raspberry leaf`, `Soyabean leaf`, `Strawberry leaf`, `Tomato leaf`, `grape leaf`
→ candidate **`monitor`** (no pathogen; no intervention).

**Reviewer note:** healthy→monitor is *definitional*, so these rows carry **no
external `source_url`** and therefore **cannot pass the evidence gate as-is** — by
design. A reviewer either attaches a general IPM monitoring citation or approves
them under an explicit "definitional / healthy" policy. Also recall (brief §7.1):
PlantDoc healthy classes are largely **white-background stock photography**, a
documented dataset-construction bias — relevant when these images drive a
`monitor` decision in the field.

## 3 · Ambiguous (2)

| Class | Pathogen | Type | Why ambiguous |
|---|---|---|---|
| **Tomato leaf mosaic virus** | ToMV (tobamovirus) | viral | Viral, but **mechanically transmitted — no insect vector**. The "control the vector" half of `remove_vector` does not apply; management is treated seed + roguing/sanitation. Reviewer must decide `remove_vector` (rogue plant) vs a sanitation action. |
| **Tomato two spotted spider mites leaf** | *Tetranychus urticae* | **mite** | An **arthropod pest, not a disease pathogen**. Of the four action classes only `monitor` fits; `fungicide`/`copper_sanitation`/`remove_vector` do not (the mite is the pest itself, not a vector). Arguably out of the paper's pathogen-based scope. |

## 4 · Insufficient evidence (0) · Excluded (0)

Every disease class obtained a verified authoritative source; none required an
"insufficient evidence" hold, and none is excluded. (Agents did log pages they
could **not** fetch — e.g. some UMN/PSU extension pages returned HTTP 403 — and
those were *not* cited; authoritative alternatives were used instead.)

---

## 5 · What the reviewer must do before approval

For each row: (1) open the `source_url` and confirm the pathogen and the quoted
management text; (2) confirm the pathogen **type** (watch the oomycete rows);
(3) decide the action class (resolve the two ambiguous rows and the healthy
policy); (4) set `review_status = approved` **only** when
`pathogen_type, action_class, action_summary, source_name, source_url,
source_identifier, evidence_summary, evidence_checked_at` are all present. The
validator (`ica26-validate-mapping`) enforces this, and
`ica26.mapping.validation.require_approved_lookup` is a hard stop that keeps
action-level evaluation blocked until at least one row is approved.

*No row in this packet was approved automatically.*
