from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

VERSION = "1.0.0"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / f"everloom-{VERSION}.zip"

EXACT_FILES = (
    "skills/everloom/SKILL.md",
    ".cowlsly/workflow.json",
    ".cowlsly/tasks/everloom-release.json",
    "docs/COWLSLY_DURABLE_WORKFLOW.md",
    "docs/COWLSLY_IMPLEMENTATION_TODO.md",
    "docs/task.schema.json",
    "docs/workflow-manifest.schema.json",
    "migrations/001_cowlsly_durable_queue.sql",
    "migrations/002_cowlsly_queue_functions.sql",
)
GLOBS = (
    "src/core/durable_*.py",
    "tests/test_cowlsly_durable_*.py",
)
LICENSE_CANDIDATES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision() -> str:
    revision = os.environ.get("GITHUB_SHA")
    if revision:
        return revision
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def included_files() -> list[Path]:
    files: set[Path] = set()
    for relative in EXACT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"required Everloom package file missing: {relative}")
        files.add(path)
    for pattern in GLOBS:
        matches = [path for path in ROOT.glob(pattern) if path.is_file()]
        if not matches:
            raise FileNotFoundError(f"Everloom package pattern matched no files: {pattern}")
        files.update(matches)
    for candidate in LICENSE_CANDIDATES:
        path = ROOT / candidate
        if path.is_file():
            files.add(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def build(output: Path) -> Path:
    files = included_files()
    manifest = {
        "name": "Everloom",
        "skill_id": "cowlsly-everloom",
        "version": VERSION,
        "source_revision": source_revision(),
        "files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            }
            for path in files
        ],
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("EVERLOOM-MANIFEST.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, manifest_bytes)
    return output


def validate(archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Everloom archive contains duplicate paths")
        forbidden = (".env", "__pycache__", ".pyc", ".pyo", "plugins.lock.json")
        for name in names:
            if name.startswith("/") or "../" in name or any(token in name for token in forbidden):
                raise ValueError(f"unsafe or private path in Everloom archive: {name}")
        manifest = json.loads(archive.read("EVERLOOM-MANIFEST.json"))
        if manifest["name"] != "Everloom" or manifest["skill_id"] != "cowlsly-everloom":
            raise ValueError("invalid Everloom package identity")
        for entry in manifest["files"]:
            payload = archive.read(entry["path"])
            if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
                raise ValueError(f"checksum mismatch: {entry['path']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and validate the Everloom AI skill package")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", type=Path)
    args = parser.parse_args()
    if args.validate_only:
        validate(args.validate_only)
        print(f"validated {args.validate_only}")
        return
    output = build(args.output)
    validate(output)
    print(output)


if __name__ == "__main__":
    main()
