# StraddleReplica Simple PDF Guide Design

## Goal

Create a six-page PDF that explains how the StraddleReplica EA works in plain
English for a non-technical owner who plans to install it manually in MT5.

## Audience and Tone

- Use short sentences and familiar words.
- Explain unavoidable trading terms immediately.
- Avoid code, formulas, implementation details, and dense tables.
- Be direct about risk and avoid promising profit or exact future results.

## Page Structure

### Page 1: What This EA Does

- Introduce the EA as an automated XAUUSD buy-stop and sell-stop grid.
- Explain that it tries to benefit when price moves strongly.
- State the current evidence-based similarity estimate of approximately 92%.
- Clearly state that it is not proven 100% identical to the target EA.

### Page 2: How the Grid Works

- Show a simple price ladder with buy orders above the starting price and sell
  orders below it.
- Explain the 30 levels on each side and 60 pending orders in total.
- Explain the three lot groups: 0.01, 0.06, and 0.15.
- Explain that the distance between levels changes with the gold price.

### Page 3: How Trades Are Managed

- Explain how pending orders become open trades.
- Explain the two-stage protective stop in simple language.
- Explain one-second rearming after a stop, when the price is valid.
- Explain the approximate $30 basket target, cancellation, position closing,
  and restart.

### Page 4: One Simple Trading Cycle

- Present a numbered example from grid creation to restart.
- Use a simple horizontal flow diagram.
- Explain that small wins can be followed by a larger losing basket.

### Page 5: Real-Account Installation

- Give concise MT5 installation steps.
- Explain loading `LATEST_30_REAL_EXACT.set`.
- Require a hedging account and capacity for at least 60 pending orders.
- Explain symbol suffixes such as `XAUUSDm`.
- State that `RequireDemoAccount=false` and `SafetyEnabled=false`.

### Page 6: Risks and Operating Checklist

- Explain major risks: large exposure, fast gold moves, gaps, slippage, spread,
  broker limits, and no optional loss protection.
- Provide a before-starting checklist.
- Explain what logs and telemetry to keep.
- Repeat that approximately 92% is an engineering estimate, not a guarantee.

## Visual Style

- A4 portrait layout.
- Clean navy, gold, white, and light-gray palette.
- Large section titles and generous spacing.
- One price-grid illustration and one cycle-flow diagram.
- Small callout boxes for key facts and warnings.
- Page number and short footer on every page.

## Output and Verification

- Final file:
  `output/pdf/StraddleReplica_EA_Simple_Guide.pdf`.
- Generate with ReportLab.
- Reopen with `pypdf` and verify six pages.
- Extract text with `pdfplumber` to confirm all page headings.
- Render all pages to PNG using Poppler.
- Visually inspect every rendered page for clipped, overlapping, or unreadable
  content before delivery.
