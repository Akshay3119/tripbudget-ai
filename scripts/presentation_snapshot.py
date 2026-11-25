"""Portable PDF snapshot of the reviewed editable Spaces presentation renders."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from reportlab.pdfgen import canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("render_directory", type=Path)
    args = parser.parse_args()
    out = Path("deliverables/slides")
    out.mkdir(parents=True, exist_ok=True)
    files = sorted(args.render_directory.glob("slide-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    assert len(files) == 16
    pdf = Path("deliverables/TripBudgetAI_Technical_Presentation.pdf")
    c = canvas.Canvas(str(pdf), pagesize=(960, 540))
    c.setTitle("TripBudgetAI — CSCI599 Capstone Technical Presentation")
    c.setAuthor("Akshay Mathur; AI-assisted development disclosed in process log")
    manifest = []
    for path in files:
        target = out / path.name
        shutil.copyfile(path, target)
        layout = path.with_name(path.stem + ".layout.json")
        if layout.exists():
            shutil.copyfile(layout, out / layout.name)
        c.drawImage(str(target), 0, 0, width=960, height=540)
        c.showPage()
        manifest.append({"file": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    c.save()
    (out / "snapshot-manifest.json").write_text(
        json.dumps(
            {
                "origin": "Reviewed native editable Spaces presentation, rendered PNGs; PDF is a visual snapshot, not a PPTX export",
                "slides": manifest,
            },
            indent=2,
        )
    )
    print("Saved 16-page portable PDF and reviewed slide renders.")


if __name__ == "__main__":
    main()
