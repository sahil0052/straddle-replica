from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIDELITY = ROOT / "profiles" / "latest_30_fidelity.set"
REAL_SAFE = ROOT / "profiles" / "latest_30_real_safe.set"


def test_fidelity_and_real_safe_presets_are_explicitly_different() -> None:
    fidelity = FIDELITY.read_text(encoding="utf-8")
    safe = REAL_SAFE.read_text(encoding="utf-8")

    assert "Profile=4" in fidelity
    assert "RequireBoundAccount=true" in fidelity
    assert "SafetyEnabled=false" in fidelity

    assert "Profile=4" in safe
    assert "RequireBoundAccount=true" in safe
    assert "SafetyEnabled=true" in safe

    # Every numeric guard is 0.0 == OFF, and that is the parity requirement, not
    # an oversight.  Each limit is individually gated on its own ">0.0" test in
    # SafetyTriggered() (StraddleEngine.mqh), so zeroing all four makes the armed
    # preset behaviourally identical to SafetyEnabled=false while keeping the
    # master switch as an operator lever and self-documenting that the rails are
    # deliberately down.
    #
    # The values were not chosen -- they were measured against the Target's own
    # 17,632-position book (.cache/golden, 2026-06-23 .. 2026-07-30):
    #
    #   DailyLossLimit=500.0        would have HALTED the Target on 3 of 28
    #                               trading days (10.7%).  On 2026-07-14 it
    #                               fires at 14:30 with realized -640.29 and
    #                               quits the session; that day finished
    #                               +3145.20.  ~$3,785 of forgone recovery.
    #   MaxEquityLossPercent=10.0   breaches on REALIZED ALONE in 1 of 275
    #                               Target cycles (2026-06-24 00:34, -239.52 on
    #                               a 2103.64 balance = 11.39%).  That cycle
    #                               finished +25.31, so the halt converts a
    #                               winner into a -$240 loser and stops the EA.
    #                               Realized-only is a strict LOWER bound --
    #                               equity includes negative floating.
    #   MaxGrossLots=2.20           is not just a cap: ExposureAllowsRearm()
    #                               SILENTLY REFUSES new grid legs below it, and
    #                               SafetyTriggered() halts above it.  A full
    #                               30-level side is 10*0.01 + 10*0.06 +
    #                               10*0.15 = 2.20 exactly, so the cap sits
    #                               precisely on the lattice's own ceiling.
    #   MaxSpreadPoints=1000.0      = $10.00 on gold vs a $0.33 median.  It
    #                               cannot prevent a bad fill (the fill already
    #                               happened); it only halts afterwards if the
    #                               wide quote survives to the next timer tick.
    #
    # Any of the four routes to BeginClose(reason, halt_after=TRUE) -> m_halted,
    # and CloseIntervalElapsed() short-circuits on m_halted, so a guard trip also
    # flattens UNPACED at the 100 ms timer -- breaking the 20 s sweep parity that
    # commit 6c340b5 was written to enforce.  The Target EA has no guard of any
    # kind and never halts itself.
    assert "MaxEquityLossPercent=0.0" in safe
    assert "MaxGrossLots=0.0" in safe
    assert "MaxSpreadPoints=0.0" in safe
    assert "DailyLossLimit=0.0" in safe
