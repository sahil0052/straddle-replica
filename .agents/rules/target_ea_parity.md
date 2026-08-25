---
name: target-ea-parity
description: >-
  Core operating directive for the StraddleReplica project. Enforces 100% mathematical,
  architectural, and operational lockstep parity between our replica EA (111387094) and the
  Target EA (901018 on AchieverGlobalMarkets). Read AGENTS.md at the repository root for the
  authoritative, measurement-backed invariants.
---

# Target EA Parity — see `AGENTS.md`

**`AGENTS.md` at the repository root is the single source of truth.** Read it before making any
change to `mql5/include/`.

This file previously carried its own copy of the invariant table. That copy had drifted badly out of
date and was actively dangerous — it specified the **June-regime lot schedule** (0.01/0.03/0.06 at
level boundaries 15/25/30) and a **single-stage 1.0-step trail activating at step 1**. Both are wrong
for the final regime that parity must track, and `AGENTS.md` explicitly warns against regressing to
the former. Duplicating the table is how that drift happened, so it is not duplicated here.

The three headline corrections, so that an agent reading only this file is not misled:

* **Lot tiers** are `0.01` at L1–10, `0.06` at L11–20, `0.15` at L21–30 (final regime, Jul 14–30).
* **The trail is two-stage**: activate at 2.0 favorable steps trailing 2.0 steps, tighten to a fixed
  1.0-step trail at 3.0 favorable steps. Confirmed by an empty band of exactly one step width in the
  locked-profit distribution across 2,695 SL closures.
* **`realized + floating >= $30` is the only money exit.** The 20-point auto-recenter and the
  rescue-breakeven liquidation that earlier revisions of this file specified are **refuted** and have
  been removed from the engine; together they destroyed a measured $6,362 across 100 cycles. Do not
  reintroduce them. See §2B and §3 of `AGENTS.md` for the evidence standard.
