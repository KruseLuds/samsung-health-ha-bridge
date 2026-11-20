#!/usr/bin/env python3
"""Reject proprietary SDK binaries and build/signing artifacts in source publication.

This scanner is intentionally strict, standard-library-only, and never opens a
network connection. Its strongest automated modes inspect tracked Git blobs,
reachable Git history, and the *actual source ZIP* being distributed.

It cannot prevent someone from altering their fork, bypassing repository rules,
or hiding data behind deliberate obfuscation. GitHub must separately require the
CI check before merges; release assets require explicit scanning too.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import pathlib
import subprocess
import sys
import zipfile

BAD_EXTENSIONS = {".aar", ".apk", ".aab", ".ap_", ".dex", ".class", ".jks", ".keystore", ".p12", ".pfx", ".pem", ".key", ".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".db", ".sqlite", ".sqlite3", ".csv", ".tsv"}
ALLOWED_JAR = "android/SamsungHealthReporter/gradle/wrapper/gradle-wrapper.jar"
# Official Gradle 9.5.1 wrapper JAR SHA-256: https://gradle.org/release-checksums/
ALLOWED_JAR_SHA256 = "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"
BINARY_NAME_FRAGMENTS = ("samsung-health-data-api", "samsung-health-data-sdk")
MAX_INSPECT = 30 * 1024 * 1024


def relpath(name: str) -> str:
    """Strip archive root folder if present and canonicalize separators."""
    p = name.replace("\\", "/").lstrip("./")
    k = "samsung-health-ha-bridge-main/"
    return p[len(k):] if p.startswith(k) else p


def prohibited_name(name: str) -> str | None:
    p = relpath(name)
    if not p or p.endswith("/"):
        return None
    lower = p.lower()
    suffix = pathlib.PurePosixPath(lower).suffix
    if suffix in BAD_EXTENSIONS:
        return f"forbidden {suffix} file"
    if suffix == ".jar" and p != ALLOWED_JAR:
        return "compiled JAR outside the trusted Gradle wrapper location"
    if any(fragment in lower for fragment in BINARY_NAME_FRAGMENTS):
        if suffix not in {".md", ".txt", ".kt", ".kts", ".py", ".yml", ".yaml", ".gitignore"}:
            return "potential proprietary Samsung SDK package"
    return None


def embedded_aar(data: bytes) -> bool:
    """Heuristic AAR-format detector, including binaries renamed with another extension."""
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = set(z.namelist())
            return ("AndroidManifest.xml" in names and "classes.jar" in names and
                    ("R.txt" in names or any(x.startswith("res/") for x in names)))
    except (OSError, zipfile.BadZipFile, ValueError):
        return False


def inspect_file(name: str, data: bytes, problems: list[str], prefix: str) -> None:
    reason = prohibited_name(name)
    if reason:
        problems.append(f"{prefix}: {name}: {reason}")
        return
    if len(data) > MAX_INSPECT:
        problems.append(f"{prefix}: {name}: exceeds {MAX_INSPECT} byte scan limit; manual review required")
        return
    if relpath(name) == ALLOWED_JAR:
        if hashlib.sha256(data).hexdigest() != ALLOWED_JAR_SHA256:
            problems.append(f"{prefix}: {name}: Gradle wrapper JAR checksum is not the verified 9.5.1 value")
        return
    if embedded_aar(data):
        problems.append(f"{prefix}: {name}: appears to contain an Android AAR package")
        return
    if data.startswith(b"PK\x03\x04") and relpath(name) != ALLOWED_JAR:
        problems.append(f"{prefix}: {name}: unapproved embedded ZIP/JAR archive")


def scan_archive(path: pathlib.Path, problems: list[str]) -> int:
    if not zipfile.is_zipfile(path):
        problems.append(f"archive: {path.name}: not a readable ZIP archive")
        return 0
    seen = 0
    with zipfile.ZipFile(path) as z:
        for item in z.infolist():
            if item.is_dir():
                continue
            seen += 1
            name = relpath(item.filename)
            reason = prohibited_name(name)
            if reason:
                problems.append(f"source ZIP: {name}: {reason}")
                continue
            if item.file_size > MAX_INSPECT:
                problems.append(f"source ZIP: {name}: too large to inspect; manual review needed")
                continue
            with z.open(item) as f:
                inspect_file(name, f.read(MAX_INSPECT + 1), problems, "source ZIP")
    return seen


def git(cwd: pathlib.Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode:
        raise RuntimeError(f"git {' '.join(args[:3])} failed: {p.stderr.decode(errors='replace')[:200]}")
    return p.stdout


def scan_git(repo: pathlib.Path, history: bool, problems: list[str]) -> int:
    try:
        git(repo, "rev-parse", "--show-toplevel")
    except (FileNotFoundError, RuntimeError):
        problems.append("Git checkout unavailable. Provide a real clone with .git to scan tracked files/history.")
        return 0
    inspected: set[str] = set()
    count = 0
    # Staged index blobs, not worktree files. An ignored local AAR in library/libs/ is
    # deliberately excluded. `git add -f` changes the index and is caught here.
    items = git(repo, "ls-files", "--stage", "-z").split(b"\x00")
    for item in items:
        if not item:
            continue
        meta, name = item.split(b"\t", 1)
        oid = meta.split()[1].decode("ascii")
        label = name.decode("utf-8", errors="replace")
        if oid not in inspected:
            content = git(repo, "cat-file", "blob", oid)
            inspect_file(label, content, problems, "tracked")
            inspected.add(oid)
        else:
            reason = prohibited_name(label)
            if reason:
                problems.append(f"tracked: {label}: {reason}")
        count += 1
    if history:
        records = git(repo, "rev-list", "--objects", "--all").splitlines()
        if not records:
            problems.append("No Git history available. This check cannot certify prior commits.")
        for line in records:
            if b" " not in line:
                continue
            raw_oid, raw_path = line.split(b" ", 1)
            oid = raw_oid.decode("ascii")
            label = raw_path.decode("utf-8", errors="replace")
            reason = prohibited_name(label)
            if reason:
                problems.append(f"history: {label}: {reason}")
                continue
            if oid in inspected:
                continue
            if git(repo, "cat-file", "-t", oid).strip() != b"blob":
                continue
            content = git(repo, "cat-file", "blob", oid)
            inspect_file(label, content, problems, "history")
            inspected.add(oid)
    return count


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--archive", type=pathlib.Path, help="Inspect exact source ZIP before release")
    group.add_argument("--repository", type=pathlib.Path, help="Inspect Git checkout tracked files")
    p.add_argument("--history", action="store_true", help="Also scan every reachable Git commit (requires --repository)")
    args = p.parse_args()
    if args.history and args.repository is None:
        p.error("--history requires --repository")
    issues: list[str] = []
    count = scan_archive(args.archive, issues) if args.archive else scan_git(args.repository, args.history, issues)
    if issues:
        print(f"BLOCKED: {len(issues)} suspicious/forbidden publication entries found; inspected {count} items")
        for issue in sorted(set(issues))[:80]:
            print("  -", issue)
        if len(issues) > 80:
            print(f"  ... {len(issues) - 80} additional entries")
        return 1
    print(f"PASS: source-only check inspected {count} items, with no blocked SDK/binary artifacts detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
