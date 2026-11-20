# SamsungHealthReporter: Android developer project

**ANDROID ONLY | FOR DEVELOPMENT AND TESTING ONLY**

This folder is the Android Studio project for the Samsung Health Bridge development phone app. It reads permitted Samsung Health records using Samsung's Health Data SDK and forwards eligible measurements over authenticated HTTPS to the separate Home Assistant integration.

- **Android Studio project:** open this folder, `android/SamsungHealthReporter/`.
- **Samsung SDK:** obtain the genuine proprietary SDK AAR directly from [Samsung Developer](https://developer.samsung.com/health/data/overview.html) and place it locally under `library/libs/`. Do not commit it to Git.
- **Build:** run `gradlew.bat :app:assembleDebug` on Windows or `./gradlew :app:assembleDebug` on macOS/Linux, or run the project from Android Studio. Installable builds require the real SDK and must not use the library stub.
- **Watch:** the existing Samsung Health and Samsung Health Monitor apps handle watch measurements and synchronization. There is no bridge watch APK.
- **Phone:** use the v0.3.3 developer interface to configure an HTTPS Home Assistant URL, development access token, Samsung READ permissions, manual sync and WorkManager background sync.
- **Home Assistant:** install `custom_components/samsung_health_bridge/` separately and add Samsung Health Bridge using the Devices & services UI.

**Complete instructions:** [Android developer setup](../../docs/ANDROID_DEVELOPER_INSTALL.md), [phone background settings](../../docs/ANDROID_DEVELOPER_INSTALL.md#samsung-galaxy-phone-background-operation-and-battery-setup), [watch development checks](../../docs/WATCH_DEVELOPER_SETUP.md), [Home Assistant setup](../../docs/HOME_ASSISTANT_INSTALL.md), and [SDK requirements](../../docs/SDK_REQUIREMENTS.md).

Upstream acknowledgments and license are preserved in this project; see the [third-party notices](../../docs/THIRD_PARTY_NOTICES.md) and the upstream [`LICENSE`](LICENSE).
