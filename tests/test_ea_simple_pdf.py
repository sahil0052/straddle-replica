from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "tools" / "create_ea_simple_pdf.py"


def test_simple_ea_pdf_has_six_pages_and_required_plain_language_content(tmp_path):
    assert GENERATOR.exists(), f"Missing PDF generator: {GENERATOR}"

    from tools.create_ea_simple_pdf import build_pdf

    output = tmp_path / "ea-simple-guide.pdf"

    build_pdf(output)

    assert output.exists()
    reader = PdfReader(output)
    assert len(reader.pages) == 6

    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    for required in (
        "What This EA Does",
        "How the Grid Works",
        "How Trades Are Managed",
        "One Simple Trading Cycle",
        "Real-Account Installation",
        "Risks and Operating Checklist",
        "approximately 92%",
        "RequireDemoAccount=false",
        "SafetyEnabled=false",
    ):
        assert required in text
