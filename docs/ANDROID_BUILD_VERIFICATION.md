# Android source build checks for developers

**FOR SOFTWARE DEVELOPMENT AND TESTING ONLY**

The Android Studio project is [`android/SamsungHealthReporter/`](../android/SamsungHealthReporter/). The source includes Gradle 9.5.1 wrapper files. Samsung Health Data SDK is proprietary and is not bundled with the source.

1. Download Samsung Health Data SDK from [Samsung Developer](https://developer.samsung.com/health/data/overview.html). Follow Samsung's requirements and put the genuine `samsung-health-data-api*.aar` in the locally ignored `android/SamsungHealthReporter/library/libs/` directory.
2. Open `android/SamsungHealthReporter/` in Android Studio with a supported Android SDK and Java toolchain.
3. For a development APK, use Android Studio's **Run** or invoke `gradlew.bat :app:assembleDebug` (Windows) / `./gradlew :app:assembleDebug` (macOS/Linux). The build is designed to fail when the real SDK AAR is absent. Stub mode is restricted to library testing and must not be used to create a phone APK.
4. Build and deploy to a physical Android development phone. Enable Android Developer Options for deployment and Samsung Health Data SDK developer mode for authorized SDK testing. These are separate settings.
5. Follow the [Android developer installation](ANDROID_DEVELOPER_INSTALL.md) to configure the connection, permissions, manual test and background settings.
6. Before committing code, run `python3 tools/verify_source_only.py --repository . --history` from the repository root. Never add the Samsung AAR, health data, API tokens, or signing credentials to source control.

The Gradle 9.5.1 wrapper JAR SHA-256 is `497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7`.
