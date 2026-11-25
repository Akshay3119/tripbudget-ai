"""Inventory publishable files without self-referential commit hashes or private runtime files."""

import hashlib
import json
import subprocess
import tomllib
from pathlib import Path


def main():
    target = Path("deliverables/release-manifest.json")
    names = (
        subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    entries = []
    for name in sorted(set(names)):
        p = Path(name)
        if not name or p == target or not p.is_file():
            continue
        data = p.read_bytes()
        entries.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    code = [
        r
        for r in entries
        if r["path"].startswith(("src/", "static/", "corpus/", "config/"))
        or r["path"] in {"Dockerfile", "pyproject.toml", "uv.lock"}
    ]
    value = {
        "version": tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"],
        "date": "2026-11-25",
        "source_revision": "The Git commit containing this manifest identifies the release; a content inventory avoids self-referential hashes. Evaluation release IDs and cloud image digests are recorded separately.",
        "code_inventory_sha256": hashlib.sha256(json.dumps(code, sort_keys=True).encode()).hexdigest(),
        "files": entries,
    }
    target.write_text(json.dumps(value, indent=2) + "\n")
    print(
        "Inventoried", len(entries), "publishable files; private/runtime paths excluded by Git ignore rules."
    )


if __name__ == "__main__":
    main()
