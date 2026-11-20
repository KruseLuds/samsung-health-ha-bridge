# Source-code safety checks for developers

**FOR DEVELOPMENT AND TESTING ONLY.**

Samsung Health Data SDK is proprietary. The SDK `.aar` is not part of this repository; obtain it separately from Samsung and keep it in the local ignored `android/SamsungHealthReporter/library/libs/` directory.

Before committing changes, developers run:

```sh
python3 tools/verify_source_only.py --repository . --history
```

The scanner rejects prohibited SDK binaries, application packages, private keys, and other blocked binary types. Git ignore rules alone do not prevent a deliberately forced commit. The source-only check is a safeguard, not a replacement for reviewing files, screenshots, credentials and Git history. Never commit personal health records, access tokens, SQLite databases, signing keys, private logs or Samsung's AAR.

The verified Gradle 9.5.1 wrapper JAR is an explicitly allowed development bootstrap file. It is not Samsung software.
