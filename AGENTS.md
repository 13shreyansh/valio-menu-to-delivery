# Junction 2026 rules for Codex (shared by every entry, dated Sat 14 Nov 19:45)

Goal: win the sponsor prizes at Junction 2026. Final deadline Sun 15 Nov 10:00 Helsinki.
Shreyansh decides taste and direction. The Chief (Claude) writes each job. You decide how to build it.

## Work rules
- Work only inside this entry's folder. Do not read other entries.
- Read only what the job needs. The entry AGENTS.md and STATUS.md carry the context.
- Before you build, write a 5-line paraphrase of the goal, scope and acceptance cases at the top of STATUS.md.
- Prove it works on the real artifact: the live URL, a real browser, real data. "It compiles" is not done.
- Every bug you find becomes a regression test before you move on.
- Label every number as measured, inferred or guess.
- For any UI work, read ~/Documents/ChatGPT/Junction/DESIGN-FLOOR.md and this entry's DESIGN-DIRECTION.md first.
- Before reporting, have a separate reviewer (6 Astra) run two passes, one on spec fit and one on build quality. It reruns the quality commands itself.

## Allowed without asking
Create repos under 13shreyansh, Vercel projects and env vars, API keys on his signed-in accounts, dataset downloads, deploys to this entry's own Vercel project or VPS.

## Never without "APPROVED BY SHREYANSH" in the job
Discord posts, video uploads, portal submissions, purchases, deletions, messages to people. Never write a key or password into a file, log or reply.

## End every job by overwriting STATUS.md, with your final reply the same text
```
ENTRY / time / commit / live URL
DONE: up to 3 bullets
NUMBERS: dev / held-out / baseline, each labelled measured, inferred or guess
SCREENSHOTS: 2-3 paths (desktop first screen, 390px first screen, key moment)
REVIEW: reviewer verdict in one line, plus what it flagged
NEXT: the next goal you propose
NEEDS DECISION: a taste or direction question, or "none"
BLOCKED: or "none"
```

## Browser and tools
- Do not use sub-agents unless necessary.
- Use Codex's inbuilt browser for all web, account and UI actions. Use IAB through cua_repl. Never open, attach to or control Shreyansh's personal browser windows or profiles. Do not launch an external browser as a workaround.
- Local tools remain appropriate when necessary for coding, builds, tests, SSH and secret-safe operations.

---

# Valio: "Next week's order is ready" (dated Sat 14 Nov 21:05)

Why it exists: a hotel head chef reorders the same 40-60 Valio items every week, by hand, late at night. When plans change (a wedding lands on Friday) they redo it all. Valio wants to be the easiest place to order, with no middleman marketplace.
The judge: Valio. Rubric: 30% request -> real lookup -> order/approval end to end; 20% solves the need; 20% autonomy with buyer-set controls; 15% exceptions (late stock, cut-offs, limits); 15% openness (MCP door for buyers with their own agents). Booth quote: most buyers will NOT have their own AI agents.
Wins if: in 2 minutes a judge sees (1) a pre-filled order that explains every quantity in kitchen maths, (2) a spoken change ("wedding Saturday, 120 guests") updating the order live with recipe-safe swaps, smart pack sizes and a budget check, (3) a whiteboard photo of the final menu updating the order, then Place order.
Out of scope: beating rival wholesalers, standing-order drift, % cookable metrics, any invented price or discount.
Hard constraints: real Valio API for price, availability and cut-offs (junction26.valioaimo.fi, key in Vercel env VALIO_API_KEY). No order endpoint exists, so Place order is a clearly mocked confirmation. Gemini (GEMINI_API_KEY) for speech/photo understanding. Kitchen words only: added, more, less, removed, swapped.
Existing code: github.com/13shreyansh/valio-menu-to-delivery (API client, catalogue, MCP at /mcp/, Vercel auto-deploy). Reuse the data layer; the UI is rebuilt from DESIGN-DIRECTION.md.
Quality commands: to be set by job 1 (wedding-order correctness test, guardrail test, whiteboard transcription check).
Design: DESIGN-DIRECTION.md. Decisions: DECISIONS.md.
Sponsor brief and booth notes: ../context/valio.md (read once at the start).
