#!/usr/bin/env python3
"""Static Step 8 source-policy verification; does not compile Android or use private SDK."""
from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "android" / "SamsungHealthReporter"
W = A / "gradle" / "wrapper" / "gradle-wrapper.jar"
WRAPPER_HASH = "497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7"


def verify(root: Path = ROOT) -> list[str]:
    problems = []
    a = root / "android" / "SamsungHealthReporter"
    files = {
        "app": a / "app" / "build.gradle.kts",
        "library": a / "library" / "build.gradle.kts",
        "wrapper properties": a / "gradle" / "wrapper" / "gradle-wrapper.properties",
        "gitignore": root / ".gitignore",
        "source scanner": root / "tools" / "verify_source_only.py",
    }
    try:
        src = {k: p.read_text(encoding="utf-8") for k, p in files.items()}
    except OSError as exc:
        return [f"Missing/unreadable policy source: {exc}"]
    expected = [
        ("app", "samsungHealthDataStub", "Phone build must check the stub setting"),
        ("app", 'if (sdkAars.size != 1)', "App must require exactly one AAR at task execution"),
        ("app", "throw GradleException", "App must fail the build if requirements are violated"),
        ("app", 'name == "preBuild"', "App guard must be attached to preBuild"),
        ("library", 'providers.gradleProperty("samsungHealthDataStub")', "Library stub use must be explicit"),
        ("wrapper properties", "distributionSha256Sum=bafc141b619ad6350fd975fc903156dd5c151998cc8b058e8c1044ab5f7b031f", "Gradle 9.5.1 distribution checksum missing"),
        ("gitignore", "*.aar", "Samsung AAR ignore rule missing"),
        ("source scanner", "ALLOWED_JAR_SHA256", "Wrapper hash restriction missing"),
    ]
    for name, needle, message in expected:
        if needle not in src[name]:
            problems.append(message)
    jar = a / "gradle" / "wrapper" / "gradle-wrapper.jar"
    if not jar.exists():
        print("INFO: Gradle wrapper JAR still absent. Restore from trusted Gradle 9.5.1 tooling before clean build.")
    elif hashlib.sha256(jar.read_bytes()).hexdigest() != WRAPPER_HASH:
        problems.append("Gradle wrapper JAR does not match official Gradle 9.5.1 checksum")
    return problems


if __name__ == "__main__":
    errors = verify()
    if errors:
        for e in errors:
            print("FAIL:", e)
        sys.exit(1)
    print("PASS: Android build policy is fail-closed, SDK files are excluded, wrapper checks are configured")
    print("NOTE: Static verification only. Real Samsung-SDK build and test are still required.")
