# Galaxy Watch setup and data-path verification

> **FOR SOFTWARE DEVELOPMENT AND TESTING ONLY.** This guide supports developers evaluating Samsung Health Bridge with Samsung's permitted SDK development/testing access. It is **not** an instruction to use Samsung Health developer mode for ordinary consumer operation or a statement of Samsung approval. Samsung's requirements and device/region eligibility remain in force.

## Do I install Samsung Health Bridge on the watch?

**No. There is no Samsung Health Bridge watch APK. Do not reinstall your existing watch apps merely to use this project.** The repository's Android application runs **on the Android phone**, and Home Assistant's integration runs **on the server**. No watch-specific developer mode, ADB session, HACS installation, or Home Assistant Wear OS Companion installation is required by the bridge.

The watch is an optional **measurement source**. The phone's Samsung Health Data SDK cannot directly query a watch over Bluetooth. It reads records that Samsung Health on the phone makes available through the SDK. The bridge does not change watch firmware or install a watch-side service.

## Components and their responsibilities

| Where | Software | Role in this project | Required? |
| --- | --- | --- | --- |
| **Galaxy Watch** | **Samsung Health app on the watch** | Records compatible fitness/wellness measurements such as heart rate, activity and sleep and participates in synchronization to Samsung Health on the paired phone. | For Galaxy Watch-derived measurements. |
| **Galaxy Watch** | **Samsung Health Monitor App on the watch** | Supplies compatible, region/device-eligible regulated features such as watch-initiated blood-pressure measurements; calibration and supported phone/watch pairing may be required. | Only for supported Health Monitor data, including watch BP. |
| **Android phone** | **Galaxy Wearable / applicable Galaxy Watch Manager plugin** | Pairs, connects and manages the watch; supports its normal watch-phone relationship. Not a Samsung Health Data SDK reader. | Normally needed for supported watch setup. |
| **Android phone** | **Samsung Health app** | Maintains Samsung Health records and its own activity/sleep/wellness interface. **The SDK reads eligible data from this phone-side Samsung Health store**, not from Google Health Connect. | Yes. |
| **Android phone** | **Samsung Health Monitor App on the phone** | Pairs with supported Health Monitor watch features and can display BP/other compatible measurements. Showing a value here does **not** guarantee that every calculated dataset is available to the SDK. | Where required by the chosen Health Monitor feature. |
| **Android phone** | **SamsungHealthReporter / Samsung Health Bridge Android development app** | Requests authorized Samsung Health Data SDK READ access and sends eligible records by authenticated HTTPS to Home Assistant. | Yes, as a separately built/installed developer test app. |
| **Android phone** | **Google Health Connect** | Android's separate health-data sharing store, used by compatible apps including the Home Assistant Companion App. **The bridge does not read from or write to Health Connect.** | Optional alongside the bridge, not a bridge dependency. |
| **Watch / phone** | **Home Assistant Companion App** | Separate Home Assistant device sensors and Wear OS features. It is not used as a transport for SamsungHealthReporter data. | Optional; not needed for the Samsung bridge. |

## Developer preparation and verification

1. **Do not change a working watch installation.** On the existing compatible Galaxy Watch, confirm that Samsung Health app works and that the watch is paired to the intended Samsung/Android phone. Make sure the normal watch-to-phone synchronization completes.
2. If evaluating **watch-initiated BP**, confirm that the watch and phone support the Samsung Health Monitor feature in the development device's region. Follow Samsung Health Monitor's own calibration and measurement requirements. Do not claim BP can be measured on every Galaxy Watch or in every country.
3. On the **phone**, open Samsung Health and Samsung Health Monitor (where applicable). Confirm the intended test measurement is visible on the phone. Some information shown in Health Monitor is not necessarily a corresponding Samsung Health Data SDK record.
4. **For authorized software development/testing only**, use Samsung's official SDK developer documentation to configure testing access on the **phone**. Do not confuse Samsung Health SDK developer mode with Android's OS-wide Developer Options, and do not activate any watch developer setting for this bridge.
5. Use Samsung's official DataViewer during development to check whether the intended record/category is actually exposed by the phone-side Samsung Health Data SDK. Health Connect Toolbox can separately confirm whether a comparable record was exported to **Health Connect**, but the two stores have different APIs and schemas.
6. Open SamsungHealthReporter on the **phone**, request only the necessary READ permissions or the expanded set for developer testing, and run **SYNC ONCE NOW (TEST)**. Check its diagnostics without exposing health values, tokens or private URLs.
7. In Home Assistant, verify the corresponding Samsung Bridge entity, source measurement timestamp, and record count/history. A successful sync sending zero records may mean that no changed records were available. It does not prove that a new record was ingested.
8. If a genuinely new record is present, confirm it arrives in the Samsung Bridge receiver and its history. Keep the normal watch, Samsung Health and Health Monitor apps updated through their own supported channels, independently of HACS/Marketplace.

## Data provenance and limits

- **Blood pressure:** The bridge can read ordinary eligible watch-origin BP records and their associated pulse if they are exposed through the Samsung Health Data SDK. The developer's prior testing found those records even though they were absent from the Health Connect route.
- **Overnight Blood Pressure Trend:** The separate overnight Blood Pressure Trend dataset is not available through the SDK investigated here. Do not promise to retrieve the proprietary trend series.
- **Sleep:** Samsung Health sleep sessions, stages, scores and the Home Assistant Companion App's Health Connect sleep data are separate paths; do not equate session times, score, and stage timeline.
- **Heart rate:** Many frequent watch measurements may be heart-rate records, not BP readings. The bridge must preserve measurement source, units and measurement timestamp.
- **Watch-only displays:** A value appearing on the watch does not prove it is present in Samsung Health on the phone, exposed through its SDK, available to Health Connect, or implemented as a HA sensor.
- **No medical certification:** This project is not a medical device or substitute for validated medical records or clinician guidance.

## Troubleshooting: first missing hop

| Where the data appears | Where it is missing | Likely check |
| --- | --- | --- |
| Watch | Samsung app on phone | Pairing, compatibility, synchronization and app-specific settings. |
| Samsung Health Monitor phone app | Samsung Health / DataViewer | Different Health Monitor dataset, SDK availability and authorization. |
| Samsung Health phone app | Samsung SDK DataViewer | SDK category, permissions, regional availability or record schema. |
| Samsung SDK DataViewer | SamsungHealthReporter | Development READ permission, data type, filters and date range. |
| SamsungHealthReporter | Home Assistant | HTTPS URL, valid HA access token, authentication, receiver readiness, diagnostic result. |
| Home Assistant record storage | Dashboard | Registered entity ID, availability, record history route and dashboard date filter. |

## Where developers obtain the Android application source

The phone app source is included in the **same** project repository: [Android Studio project (`android/SamsungHealthReporter/`)](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter). The [phone bridge Kotlin implementation](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter/app/src/main/kotlin/com/kvs/samsunghealthreporter/example/bridge) contains synchronization, scheduling, preferences and UI logic. Developers build and install this on the **phone** using the [Android developer installation guide](ANDROID_DEVELOPER_INSTALL.md). The GitHub repository does **not** contain a separate watch module or watch APK, and HACS installs neither the phone nor watch software.

## Related guides

- [Android developer installation, SDK build and UI controls](ANDROID_DEVELOPER_INSTALL.md)
- [Home Assistant receiver installation](HOME_ASSISTANT_INSTALL.md)
- [Samsung SDK requirements](SDK_REQUIREMENTS.md)

**Independent community project; not sponsored by Samsung.** The watch uses its own manufacturer's apps, and no custom watch APK is supplied or required.
