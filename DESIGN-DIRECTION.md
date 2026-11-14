# Valio design spec: The Kitchen Sheet

For Codex. Replaces the look in valio.md; DESIGN-FLOOR.md applies underneath. Figures and product names here are illustrative; the build shows real catalogue values. UI copy is English; product names stay Finnish exactly as the catalogue gives them.

## 1. Direction contract

- **THESIS:** The week's order arrives already written, like a sheet a good sales rep hands over. The chef checks it, corrects it by thumb or voice, and signs it off.
- **OWN-WORLD:** The kitchen's own order sheet: white sheet on a steel-grey bench, dark day bands, big numerals. Bright kitchen light and arm's length, so light theme and high contrast. Blue appears only where Valio speaks or changed something.
- **STORY:** Ready → told about the wedding → the sheet grows and every new number shows its working → three checks → whiteboard photo → placed.
- **FIRST VIEWPORT (hero frame, after the wedding is added):** heading, "3 things to check", first delivery day with cut-off, five or more rows with steppers, dock (Tell Valio, budget, Place order).
- **SIGNATURE:** "The working": every row carries its sum, and the sum ends in the number shown in the stepper.
- **RISK:** Reads as a spreadsheet. Counter: 72 px rows, dark day bands, one column of rows (no cell grid), sums in plain words.

Rejected: **webshop with cart** (chefs reorder, they don't browse); **rep chat thread** (hides the order, reads as a chatbot); **live table of system calls** (developer tool, the owner's explicit rejection).

## 2. Tokens

**Font:** Atkinson Hyperlegible Next (Google Fonts / Fontsource), self-hosted, 400/600/700. Reason: 1/l/I and 0/O cannot be confused in quantities and pack sizes at arm's length. `tabular-nums` on all numerals; if the face lacks it, set only quantity and price columns in Atkinson Hyperlegible Mono. No other family.

**Type (px, fixed):** 13 meta (minimum) · 15 working line, tags · 17 body, product name (600) · 20 day band, stepper quantity (700) · 24 totals (700) · 30 heading (700) · 40 order number (700).

| Token | Hex | Job |
|---|---|---|
| bench | #EDEFF0 | page ground |
| sheet | #FFFFFF | order sheet, panels |
| ink | #0F1B26 | text, day bands, Place order |
| ink-2 | #4A5763 | secondary text |
| rule | #D5DADE | 1 px rules, borders |
| valio | #0B3FA8 | Valio's voice only: Tell Valio, change tags, links |
| valio-tint | #E6EDFB | wash on rows Valio just changed |
| ok / tint | #1B7A47 / #E3F3EA | OK'd, cut-off safe |
| attention / tint | #9A5200 / #FFF0D4 | needs your OK, cut-off under 3 h |
| problem / tint | #B3241C / #FCE9E7 | over budget, unavailable, cut-off passed |

Every state also carries an icon and a word. **Spacing:** 4, 8, 12, 16, 24, 32, 48. **Radii:** 6 controls, 10 panels, pill for tags only. **Elevation:** sheet flat with rule border; dock `0 -4px 16px rgba(15,27,38,.08)`; open Tell Valio panel `0 12px 32px rgba(15,27,38,.16)`; nothing else. **Icons:** Lucide, 1.75 px stroke, 20 px. Selection valio-tint; focus ring 2 px valio, 2 px offset.

**Signature, exactly.** Under each product name, one 15 px line:
`80 covers × 150 g = 12 kg  →  2 × 6 kg`
Terms ink-2 400, operators #8A959E, final pack quantity ink 700; the stepper beside it shows the same count at 20 px 700. When a quantity changes, only the changed terms roll. Tapping the line opens it in place as a stacked sum (need, minus stock, rounded to pack, price per sales unit, comparison price per kg/l) with a "How this was decided" link.

## 3. Home screen anatomy

1. **Top bar, 64 px:** Valio name, kitchen name with a neutral "Demo account" tag, week switcher ("Week 47 · 16–22 Nov"), "Add a product" search button. Search opens a side panel of catalogue results; it is never the default focus.
2. **Heading:** "Next week's order is ready" plus one sentence: "62 products, 3 deliveries. Built from your menu, 412 booked covers and your stock."
3. **Checks panel:** one panel of rows.
4. **Order sheet:** delivery-day groups, each a dark band plus rows.
5. **Dock, fixed bottom, 88 px:** Tell Valio and camera left, budget bar centre, Place order right.

**Tablet 1024 × 768 (primary):** single column, 24 px gutters. First viewport: top bar, heading, checks collapsed to one 56 px line each, first day band, three rows, dock. Portrait: budget bar becomes a slim line above the two buttons.

**Laptop 1440 × 900:** content 1240 centred. Sheet column 800; sticky 400 rail with checks (expanded) and "Covers this week" (day, booked covers, events such as "Wedding 120"). First viewport: heading, first day band, six rows, three full checks, dock.

**Density:** rows 72 px at both widths; touch targets 56 px minimum.

## 4. The story, beat by beat

Easing `cubic-bezier(0.16,1,0.3,1)` throughout. Reduced motion: 150 ms opacity only.

**(a) Friday, order ready.** Loads straight into the full sheet, no entrance. Checks panel is one ok line, "Nothing needs your OK"; budget within limit; Place order active. Eye: heading, then the band "Mon 16 Nov · order by Fri 15:00 · 4 h 12 min left".

**(b) Wedding call.** Chef holds Tell Valio. Dock panel grows to 200 px (height, 220 ms). A level bar follows the voice (scaleX, 80 ms linear). Transcript appears at 22 px: "Add the wedding on Saturday, 120 guests. Order everything for next week." On release, three steps tick as they finish: "Read the wedding menu · Checked your stock · Checked Valio availability for 14 products". Eye: the transcript.

**(c) Lines arrive (the one authored moment).** Sheet scrolls to the first new row (400 ms). New rows open in place: grid row 0fr→1fr 280 ms, opacity 200 ms, 60 ms stagger for the first eight. Each sits on valio-tint fading to white over 2.4 s; its tag stays. Changed quantities, day subtotals and the total roll (translateY per digit, 400 ms). Budget fill widens (width, 500 ms), crosses the limit tick, turns red past it. Place order becomes "3 things to check first". Panel settles to: "Added 9, more of 4, swapped 1. €2,840 → €4,115." with "Show only what changed" and "Undo". Eye: first new row, "120 guests × 150 g = 18 kg → 3 × 6 kg", tagged "Added · for Saturday wedding".

**(d) Three checks.** Each row gives issue, proposal and proof in one sentence, a 56 px OK and a quieter alternative. On OK the row collapses to "OK'd 21:14 · Undo" with a green tick (height 220 ms, icon crossfade 150 ms). After the third, Place order activates (colour, 200 ms). The chef then taps "+" on the cream row: that check reopens in attention colour, "You changed Kuohukerma, so this needs your OK again", and Place order locks. Eye: the reopened row.

**(e) Whiteboard photo.** Camera opens the device camera or file picker. Panel shows the photo (240 px) beside "What we read": "Removed: Lohikeitto", "Added: Paistettu siika, 120 portions", "More: Juustolautanen, 120 → 140". Uncertain words get a dotted attention underline and "Check this word"; entries edit in place. Tapping an entry outlines its handwriting on the photo (2 px valio, 150 ms). "Update order" replays (c) with tags "for the new wedding menu". Eye: the "What we read" list.

**(f) Place order.** The sheet is replaced by the confirmation (crossfade 200 ms, no modal). Eye: the order number.

## 5. Components

**Order row, 72 px.** Left: product name (17 px 600, one line) with pack size in ink-2; the working line; a change tag if any. Right: line price, then stepper: 56 px "−", quantity in sales units (20 px 700), 56 px "+", in a rule box. Long-press repeats. Zero strikes the row and offers "Put back". No thumbnail slot. States: pressed (bench fill), changed (tint), unavailable (problem icon, "Not available until Tue 17"), loading (skeleton bars).

**Day band.** Sticky ink bar, 48 px, white 20 px 700: "Wed 18 Nov delivery". Right: "Order by Tue 15:00" and a countdown pill: ok-tint above 3 h, attention-tint under 3 h, problem-tint "Cut-off passed, moves to Fri". Updates each minute, no animation. Day subtotal below the group. Terminal items get an in-row note "Arrives via terminal".

**Checks panel.** Heading "3 things to check", counting down to "All checked". Row: state icon, sentence, two buttons. "Lohifilee arrives Tuesday, too late for Monday. Swap to Kirjolohifilee: same weight, works in your Lohikeitto, no new allergens." [OK, swap] [Keep salmon]. "Kuohukerma: buy 12, not 6. €0.42 less per litre; you use 11 l by Friday." [OK, 12] [Keep 6]. "The wedding takes this order €315 over your weekly budget of €3,800." [OK this week] [Show costliest]. The proof phrase links to its row.

**Tell Valio.** Idle: 64 px valio button, mic icon, "Hold to tell Valio"; 56 px outline buttons for keyboard and camera. Listening: "Listening… release to send", level bar, transcript. Thinking: steps tick in place. Done: one-sentence result, "Show only what changed", "Undo"; collapses to a dock chip after 8 s. Error: "Didn't catch that. Hold and say it again, or type it."

**Budget bar.** "This week" with total (24 px 700) "of €3,800 budget". 12 px track; limit tick at 80 % so an overrun has room. Fill ink within budget, red past the tick with "€315 over". The amount is the chef's own setting (the plan's €500 limit works the same way); never hard-code it.

**Change tag.** Pill, 15 px, valio on valio-tint: one kitchen word plus reason. "Added · for Saturday wedding", "More · +6 kg", "Less", "Swapped · was Lohifilee", "Removed".

**Place order.** 64 px ink button, white 20 px 700. Locked: rule-grey, "3 things to check first"; tapping scrolls to the checks.

**Confirmation.** "Order placed" with green tick; order number at 40 px ("VO-47-0183"); delivery days with product count, subtotal, "cut-off met"; total against budget; link "How this was decided" (what the chef said, what was read from the photo, each OK with time, the budget rule; its footer says demo account, nothing ships). Last line, 13 px ink-2: "Buying with your own ordering agent? It connects to Valio directly over MCP."

## 6. Don't

1. No command bar, slash commands or shortcut hints.
2. No "diff", "lines", "sync", "agent", "AI", "generated", "prompt" in labels (only exception: the MCP sentence).
3. No sparkle, wand or robot icons; no gradient or glow.
4. No chat bubbles or message thread.
5. No blue on anything Valio did not say or change.
6. No product photo placeholders or initials tiles.
7. No translated or tidied Finnish product names.
8. No invented prices, discounts or stock; hide a field the catalogue lacks.
9. No modal for checks, the working or confirmation.
10. No three equal cards for the checks.
11. No red/green plus-minus code colouring or monospace rows.
12. No stepper target under 56 px; no text under 13 px.
13. No "simulated", "mock" or lorem on the main flow.
14. No load choreography, confetti or bounce.
15. No rings, sparklines or KPI tiles; the budget is one bar.
16. No endpoint names, latency or JSON within two taps of home.

## 7. Acceptance checks (screenshots)

1. 1440 × 900 after (c): heading, first day band with countdown, six or more rows, three full checks, budget bar and Place order visible without scrolling.
2. 1024 × 768 after (c): heading, checks, first day band, three rows, full dock; no horizontal scroll.
3. Every row's working line ends in the same number as its stepper.
4. Every day band shows delivery date, "Order by" time and time left.
5. Stepper buttons at least 56 × 56 px.
6. Blue only on Tell Valio, change tags, tint washes and links.
7. After (c): new rows carry a tag starting added, more, less, removed or swapped; budget shows the overrun in red with its amount; Place order reads "3 things to check first".
8. After three OKs Place order is active; one stepper tap on a checked product reopens that check and locks it.
9. Whiteboard state shows photo and "What we read" side by side.
10. Confirmation shows order number, delivery days, total versus budget, "How this was decided" and the MCP sentence.
11. One font family loaded; quantity and price numerals align vertically.
12. Text contrast at least 4.5:1, including on tints.
