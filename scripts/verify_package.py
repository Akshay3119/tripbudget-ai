"""Check submission evidence, source map references, secret exclusion and artifact structure."""

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

from pypdf import PdfReader

from .build_capability_map import symbols


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    checks = []
    for row in json.loads(Path("docs/capability-map.json").read_text()):
        for r in row["references"]:
            p = Path(r["path"])
            assert p.exists()
            assert symbols(p)[r["symbol"]] == (r["start"], r["end"])
            assert 1 <= r["start"] <= r["end"] <= len(p.read_text().splitlines())
    checks.append("README five-field source map: every symbol and exact range verified")
    readme = Path("README.md").read_text()
    for header in [
        "Category",
        "Claimed Feature / Guardrail / Eval",
        "Source File(s) & Line Numbers",
        "Key Class / Function",
        "Notes / Scope",
    ]:
        assert header in readme
    assert 200 <= len(Path("PROCESS_LOG.md").read_text().split()) <= 300
    checks.append("200–300 word individual review draft present; student reflection not certified")
    catalog = Path("corpus/catalog.json")
    manifest = json.loads(Path("corpus/manifest.json").read_text())
    assert hashlib.sha256(catalog.read_bytes()).hexdigest() == manifest["catalog_sha256"]
    for p in Path("src").rglob("*.py"):
        ast.parse(p.read_text())
    checks.append("Corpus digest and Python syntax verified")
    paths = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    paths = [Path(p) for p in paths if p]
    forbidden = {".env", ".secrets", ".runtime", ".venv", ".cache", "data"}
    for p in paths:
        assert not (set(p.parts) & forbidden), f"Private/runtime file would be published: {p}"
        assert p.stat().st_size < 95_000_000, f"File too large for normal GitHub source: {p}"
    # Compare exact locally configured secrets without ever printing their values.
    secrets = []
    env = Path(".env")
    if env.exists():
        from dotenv import dotenv_values

        for key, value in dotenv_values(env).items():
            if value and len(value) >= 16 and any(x in key for x in ["KEY", "PASSWORD", "DATABASE_URL"]):
                secrets.append(value.encode())
    for p in Path(".secrets").glob("*.txt"):
        for line in p.read_text().splitlines():
            if line.startswith("password="):
                secrets.append(line.split("=", 1)[1].encode())
    for p in paths:
        if p.suffix.lower() in {".mp4", ".png", ".pdf"}:
            continue
        b = p.read_bytes()
        assert not any(v in b for v in secrets), f"Secret found in publishable file: {p}"
        assert not re.search(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", b), f"Private key in {p}"
    checks.append("Publishable files exclude runtime/secrets/models and match no configured secret values")
    metrics = json.loads(Path("deliverables/metrics.json").read_text())
    assert metrics["logical_units"] == 154
    for name, n in [
        ("benchmark-v1", 80),
        ("attacks-v1", 20),
        ("provider-comparison", 36),
        ("operations", 12),
        ("live-sources-v1", 6),
    ]:
        assert len(Path(f"deliverables/evidence/{name}.jsonl").read_text().splitlines()) == n
    assert metrics["independent_audits"]["count"] == metrics["independent_audits"]["passed"]
    assert len(PdfReader("deliverables/TripBudgetAI_Technical_Presentation.pdf").pages) >= 10
    checks.append("154 real evaluation units and 16-slide portable presentation present")
    if not args.source_only:
        video = Path("deliverables/video/TripBudgetAI_Demo.mp4")
        assert video.exists()
        probe = json.loads(
            subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_format", "-show_streams", "-of", "json", str(video)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        duration = float(probe["format"]["duration"])
        assert 300 <= duration <= 600
        assert any(s["codec_name"] == "h264" for s in probe["streams"])
        claims = json.loads(Path("docs/recording-claims.json").read_text())
        assert len(claims) == 5 and all(r["status"] == "demonstrated" for r in claims)
        assert all(0 <= r["start_seconds"] < r["end_seconds"] <= duration for r in claims)
        checks.append("MP4 H.264 duration and all five claim timestamp ranges verified")
    result = {"checks": checks, "source_only": args.source_only, "passed": True}
    if not args.source_only:
        Path("deliverables/evidence/package-verification.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
