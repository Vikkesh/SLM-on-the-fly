"""HTTP MCP server exposing the tools TrueForge does not ship with.

TrueForge's MCP client speaks Streamable HTTP / SSE only (no stdio), so this runs as a small web
service on localhost and is registered under Settings -> Connectors by URL.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", ROOT / "uploads"))
HOST = os.environ.get("MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_PORT", "9000"))

mcp = FastMCP("sovereign-tools", host=HOST, port=PORT)


# --- extract_from_scan ---------------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
    description="Run Tesseract OCR on an uploaded scan (PNG/JPG under the uploads folder) and return the exact text.",
)
def extract_from_scan(image_path: str) -> str:
    path = _inside(UPLOAD_DIR, image_path)
    try:
        import pytesseract
        from PIL import Image
    except ImportError as e:  # pragma: no cover
        return f"OCR unavailable: {e}"
    try:
        text = pytesseract.image_to_string(Image.open(path))
    except pytesseract.TesseractNotFoundError:
        return "OCR unavailable: the tesseract binary is not installed on this machine (apt install tesseract-ocr)."
    text = text.strip()
    return text or "(no text recognised)"


# --- generate_docx -------------------------------------------------------------------------------


class Section(BaseModel):
    heading: str = Field(description="Section title, e.g. 'Findings'")
    body: str = Field(default="", description="Paragraph text. Blank lines separate paragraphs.")
    bullets: list[str] = Field(default_factory=list, description="Optional bullet points after the body")


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    description=(
        "Create a formal Word (.docx) document. Provide a title, an optional metadata table "
        "(e.g. Asset ID, Inspector, Date, Risk rating), and ordered sections. Returns the saved file path."
    ),
)
def generate_docx(
    title: str,
    sections: list[Section],
    metadata: dict[str, str] | None = None,
    signoff: list[str] | None = None,
    filename: str | None = None,
) -> str:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    h = doc.add_heading(title, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if metadata:
        table = doc.add_table(rows=0, cols=2)
        table.style = "Light Grid Accent 1"
        for key, value in metadata.items():
            row = table.add_row().cells
            row[0].text = str(key)
            row[1].text = str(value)
        doc.add_paragraph()

    for s in sections:
        doc.add_heading(s.heading, level=1)
        for para in (p.strip() for p in s.body.split("\n\n")):
            if para:
                doc.add_paragraph(para)
        for b in s.bullets:
            doc.add_paragraph(b, style="List Bullet")

    if signoff:
        doc.add_heading("Sign-off", level=1)
        table = doc.add_table(rows=1, cols=len(signoff))
        table.style = "Table Grid"
        for cell, role in zip(table.rows[0].cells, signoff):
            cell.text = f"{role}\n\nName: ____________\nSignature: ________\nDate: ____________"

    path = _target(filename or title, ".docx")
    doc.save(path)
    return f"Saved: {path} ({path.stat().st_size} bytes)"


# --- generate_xlsx (stretch) ---------------------------------------------------------------------


@mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False),
    description="Create an Excel (.xlsx) workbook from a header row and data rows. Returns the saved file path.",
)
def generate_xlsx(
    headers: list[str],
    rows: list[list[str | float | int | None]],
    sheet_name: str = "Sheet1",
    filename: str | None = None,
) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(list(r))
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    path = _target(filename or sheet_name, ".xlsx")
    wb.save(path)
    return f"Saved: {path} ({path.stat().st_size} bytes)"


# --- helpers -------------------------------------------------------------------------------------


def _target(name: str, ext: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(name).stem).strip("-")[:60] or "document"
    return OUTPUT_DIR / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}{ext}"


def _inside(folder: Path, requested: str) -> Path:
    """Only files under the uploads folder may be read; a bare filename is resolved there."""
    p = Path(requested)
    candidate = (p if p.is_absolute() else folder / p).resolve()
    if folder.resolve() not in candidate.parents and candidate != folder.resolve():
        raise ValueError(f"Path must be inside {folder}")
    if not candidate.is_file():
        raise FileNotFoundError(f"No such upload: {requested}")
    return candidate


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
