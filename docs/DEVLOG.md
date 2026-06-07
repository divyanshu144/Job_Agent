# DevLog

Running log of design decisions and deferred ideas that don't belong in code comments.

---

## stage2 enrichment (deferred) — 2026-06-03

**Context.** We removed all Anthropic prompt `cache_control` (analysis path in `base.py`, and
discovery `stage2` in `discovery.py`). On the analysis path each system prompt is unique per
request, so caching only ever wrote (21K+ creation tokens, 0 reads — pure 1.25× write premium).
On discovery `stage2` the system *is* identical across all jobs in a run (the JD lives in the
user message) — the ideal burst-within-TTL shape — but it measures **~396 tokens**, ~10× below
Haiku 4.5's **4,096-token** cache minimum, so `cache_control` there never created cache either.

**Why padding to cache never pays.** To cache you'd pad the prefix ~380 → 4,096 tokens. A cached
read of a 4,096-token prefix costs `0.1 × 4096 = 409.6` effective input-tokens — already *more*
than today's full-price ~380-token prompt. The ~10.8× padding overwhelms the 10× read discount;
break-even is negative (never), at any call count. Measured: large runs fire ~85–110 stage2
calls (max 107 in run `2de843fa`).

**The only case that flips this — enrichment for quality, caching as a free consequence.**
If we independently decide stage2 should be *smarter* (not just bigger), we can give it a
genuinely larger stable prefix that clears 4,096 tokens with real signal:
- full candidate profile (not `compact[:1000]`; full profile measured ~2,545 tokens)
- a detailed relevance rubric
- 2–3 worked few-shot examples

At a real ≥4,096-token prefix, caching makes the enrichment ~90% cheaper on every read after the
first within a run's burst (409.6 vs 4,096 eff/call). Then reintroduce caching **deliberately**:
- place the stable prefix **first** (profile + rubric + examples), `cache_control` on its last block
- keep the **JD in the user message** (already the case) so the cached prefix stays byte-identical
- verify `cache_read_input_tokens > 0` across a run before trusting it

This is a "should stage2 be more accurate?" decision with a quality story — not a caching
optimization. Until then, stage2 stays uncached.
