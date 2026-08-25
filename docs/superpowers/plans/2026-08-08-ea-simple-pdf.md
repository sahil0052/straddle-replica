# StraddleReplica Simple PDF Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and visually verify a six-page, plain-English PDF explaining
how the StraddleReplica EA works and how to install the real-account build.

**Architecture:** Implement one ReportLab generator with reusable page,
heading, card, diagram, and footer helpers. Add an automated contract test for
page count and required headings, then render all pages with Poppler and inspect
the PNG output before delivery.

**Tech Stack:** Python 3, ReportLab, pypdf, pdfplumber, Poppler.

---

### Task 1: Add the PDF content contract

**Files:**
- Create: `tests/test_ea_simple_pdf.py`
- Create: `tools/create_ea_simple_pdf.py`

- [ ] **Step 1: Write the failing test**

Create a test that imports `build_pdf`, writes to a temporary path, opens the
result with `pypdf.PdfReader`, and asserts:

```python
assert len(reader.pages) == 6
```

Extract text and require these headings:

```python
required = (
    "What This EA Does",
    "How the Grid Works",
    "How Trades Are Managed",
    "One Simple Trading Cycle",
    "Real-Account Installation",
    "Risks and Operating Checklist",
)
```

Also require the phrases `approximately 92%`, `RequireDemoAccount=false`, and
`SafetyEnabled=false`.

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/test_ea_simple_pdf.py -q
```

Expected: import failure because `tools/create_ea_simple_pdf.py` does not exist.

### Task 2: Generate the six-page PDF

**Files:**
- Create: `tools/create_ea_simple_pdf.py`
- Generate: `output/pdf/StraddleReplica_EA_Simple_Guide.pdf`

- [ ] **Step 1: Implement shared drawing helpers**

Implement:

```python
def draw_header(canvas, page_number, title): ...
def draw_footer(canvas, page_number): ...
def draw_card(canvas, x, y, width, height, title, body, color): ...
def draw_grid_diagram(canvas, x, y, width, height): ...
def draw_cycle_flow(canvas, x, y, width): ...
```

Use A4 portrait pages, navy/gold/white/light-gray colors, Helvetica fonts,
consistent margins, and ASCII punctuation.

- [ ] **Step 2: Implement `build_pdf`**

Create exactly six pages matching the approved design:

1. What This EA Does
2. How the Grid Works
3. How Trades Are Managed
4. One Simple Trading Cycle
5. Real-Account Installation
6. Risks and Operating Checklist

Use short paragraphs and bullets. Include the 60-order structure, lot tiers,
one-second rearm, two-stage stop, approximate $30 basket target, two-second
restart, real preset name, account requirements, disabled safety, and the
approximately 92% estimate.

- [ ] **Step 3: Add CLI generation**

Support:

```powershell
python tools/create_ea_simple_pdf.py `
  --output output/pdf/StraddleReplica_EA_Simple_Guide.pdf
```

Create the output directory when missing and print the final path.

- [ ] **Step 4: Run the contract test and verify GREEN**

Run:

```powershell
python -m pytest tests/test_ea_simple_pdf.py -q
```

Expected: pass.

### Task 3: Render and visually verify the PDF

**Files:**
- Generate: `tmp/pdfs/StraddleReplica_EA_Simple_Guide/page-*.png`
- Final: `output/pdf/StraddleReplica_EA_Simple_Guide.pdf`

- [ ] **Step 1: Generate the final PDF**

Run the generator with the final output path.

- [ ] **Step 2: Validate structure and text**

Use `pypdf` to require six pages and `pdfplumber` to verify all headings and
that every page contains extractable text.

- [ ] **Step 3: Render every page**

Run:

```powershell
pdftoppm -png -r 130 `
  output/pdf/StraddleReplica_EA_Simple_Guide.pdf `
  tmp/pdfs/StraddleReplica_EA_Simple_Guide/page
```

Expected: six PNG files.

- [ ] **Step 4: Inspect all pages**

Open every rendered PNG or a contact sheet. Check:

- no clipped text;
- no overlapping cards or diagrams;
- readable font size;
- consistent margins and footer;
- no broken glyphs or black squares;
- balanced page density.

- [ ] **Step 5: Correct and rerender if needed**

Make only targeted layout changes, regenerate, and repeat structure and visual
checks until all six pages are clean.

- [ ] **Step 6: Final verification**

Run the PDF test once more, confirm the final file exists, and report its page
count and file size.

No commit step is included because this workspace is not a Git repository and
the user requested only the finished PDF artifact.
