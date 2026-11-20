# Samsung SDK requirements

**FOR DEVELOPMENT AND TESTING ONLY.** Samsung Health Bridge is independent of Samsung and is not a consumer or medical-monitoring application.

- Obtain Samsung Health Data SDK directly from [Samsung Developer](https://developer.samsung.com/health/data/overview.html) and follow Samsung's current SDK terms.
- The proprietary SDK `.aar` is **not included** in GitHub and must not be committed or shared from this repository.
- [Original Samsung Developer Support reply, November 18, 2026](samsung-support-response.png). The reply distinguishes developer-owned source and APK from the proprietary SDK AAR.
- Android Developer Options and Samsung Health Data SDK developer mode are separate settings. Developer mode is intended for development, debugging and testing.
- The original project code is under [MIT](../LICENSE) where applicable. The upstream SamsungHealthReporter code retains its original attribution in [third-party notices](THIRD_PARTY_NOTICES.md).
- The Android app and Home Assistant integration are installed separately. Nothing from this repository is installed on the watch.
