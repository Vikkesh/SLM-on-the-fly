"""Render a synthetic scanned inspection report as PNG (and a readings spreadsheet) for testing
without a real scan.   .venv/bin/python -m scripts.make_sample"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "samples"

LINES = [
    ("INSPECTION REPORT - PRESSURE VESSEL", 34, True),
    ("Asset ID: V-102        Unit: Crude Distillation        Class: A", 22, False),
    ("Inspection date: 14-08-2026        Inspector: R. Menon (Cert. 4471)", 22, False),
    ("Inspection type: In-service external + UT thickness", 22, False),
    ("", 10, False),
    ("READINGS", 26, True),
    ("Shell thickness (nominal 12.0 mm):  10.6 mm  (loss 11.7%)", 22, False),
    ("Operating pressure:  17.8 bar g   (MAWP 18.0 bar g)", 22, False),
    ("Relief valve PSV-102A set 19.0 bar g, popped at 19.4 bar g (+2.1%)", 22, False),
    ("External corrosion: pitting up to 1.2 mm on lower head, area 0.3 m2", 22, False),
    ("Nozzle N3 weld: no cracks found (MPI)", 22, False),
    ("Insulation: damaged near manway, exposed metal approx 0.1 m2", 22, False),
    ("", 10, False),
    ("REMARKS", 26, True),
    ("Vessel last inspected 09-2024. Recommend recoat of lower head.", 22, False),
    ("Insulation repair raised as WO-88213.", 22, False),
    ("", 10, False),
    ("Signed: R. Menon            Area Engineer: ____________", 22, False),
]


def report_png() -> Path:
    w, h = 1240, 1650
    img = Image.new("RGB", (w, h), (250, 248, 242))
    d = ImageDraw.Draw(img)
    y = 90
    for text, size, bold in LINES:
        font = ImageFont.load_default(size=size)
        if bold:
            d.text((101, y + 1), text, fill=(20, 20, 20), font=font)
        d.text((100, y), text, fill=(25, 25, 25), font=font)
        y += size + 14
    d.rectangle([60, 60, w - 60, h - 60], outline=(120, 120, 120), width=2)
    # slight blur + rotation so it reads as a scan rather than a render
    img = img.rotate(0.6, resample=Image.BICUBIC, expand=False, fillcolor=(250, 248, 242))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "inspection-report-V102.png"
    img.save(path)
    return path


def readings_xlsx() -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "P-301 readings"
    ws.append(["Time", "Bearing DE (C)", "Bearing NDE (C)", "Vibration (mm/s)", "Seal flush (bar g)", "Discharge (bar g)"])
    rows = [
        ("08:00", 68, 71, 3.9, 2.8, 20.1),
        ("10:00", 72, 74, 4.3, 2.6, 20.4),
        ("12:00", 79, 77, 5.2, 2.2, 21.0),
        ("14:00", 86, 81, 7.4, 1.4, 21.6),
        ("16:00", 88, 83, 7.9, 1.3, 21.9),
    ]
    for r in rows:
        ws.append(list(r))
    path = OUT / "p301-readings.xlsx"
    wb.save(path)
    return path


if __name__ == "__main__":
    print(report_png())
    print(readings_xlsx())
