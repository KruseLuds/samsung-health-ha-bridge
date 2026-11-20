# Android developer installation and testing

**ANDROID ONLY | FOR SOFTWARE DEVELOPMENT AND TESTING ONLY**

This guide covers the separate Android application in [`android/SamsungHealthReporter/`](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter). It reads permitted Samsung Health data through Samsung Health Data SDK and sends records to the Home Assistant integration. The SDK AAR is proprietary, must be obtained directly from Samsung at [Samsung Developer](https://developer.samsung.com/health/data/overview.html) and must never be committed to this repository. This application is independent of Samsung and is not intended for general consumer installation or medical monitoring.

## 1. Understand what you are installing

There are three components, but only two custom software installations:

1. **Galaxy Watch:** Use Samsung's existing Samsung Health and, where supported, Samsung Health Monitor applications. The current repository contains **no separately installable watch app**. The watch synchronizes measurements to Samsung Health on the phone through Samsung's existing ecosystem.
2. **Android phone:** Build and install the **SamsungHealthReporter example app with Samsung Health Bridge additions**. It uses the Samsung Health Data SDK to read permitted Samsung Health records, then sends them to Home Assistant over authenticated HTTPS.
3. **Home Assistant:** The UI-configured development receiver is installed from `custom_components/samsung_health_bridge/`. It has a working configuration flow and 103 registered entities in the developer's HA Core 2026.11.2 environment. Public HACS/Marketplace installation is still being prepared and has not yet been independently validated from a clean checkout.

**Google Health Connect is not required for this bridge's data path.** The phone app only reads Samsung Health using Samsung's Data SDK, not the Health Connect API, and makes that data available in HA. The regular Home Assistant Companion App is not used to carry this bridge's data.

### Android project and source links

The source is maintained **inside the same repository as the HACS/Marketplace Home Assistant integration**:

- [Android Studio project: `android/SamsungHealthReporter/`](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter)
- [Phone bridge source: Kotlin `bridge/` package](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter/app/src/main/kotlin/com/kvs/samsunghealthreporter/example/bridge)
- [Android setup screen: `BridgeActivity.kt`](https://github.com/KruseLuds/samsung-health-ha-bridge/blob/main/android/SamsungHealthReporter/app/src/main/kotlin/com/kvs/samsunghealthreporter/example/bridge/BridgeActivity.kt)
- [SamsungHealthReporter library module source](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter/library)
- [Home Assistant integration source](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/custom_components/samsung_health_bridge)

The **phone** app must be built and installed separately by developers for individual development and testing only. **HACS/Marketplace never installs the Android app**, and no additional Galaxy Watch application exists. **Samsung's proprietary SDK AAR is deliberately excluded** and must be obtained separately from Samsung under its terms here [Samsung Developer](https://developer.samsung.com/health/data/overview.html).

## 2. Development prerequisites

- A physical Android phone running **Android 10 / API 29 or newer**. Samsung's Data SDK does not support Android emulators.
- A current version of **Samsung Health on the phone, version 6.30.2 or newer**, installed and set up with the developer's own test data.
- For watch-derived records, a compatible, paired Galaxy Watch with its normal Samsung Health software. For supported watch blood-pressure records, Samsung Health Monitor must be available and the records must reach Samsung Health on the phone. Features and availability vary by device and region.
- A Samsung Developer account and acceptance of Samsung's applicable SDK terms.
- **Samsung Health Data SDK v1.1.0**, downloaded directly from Samsung. The SDK archive supplies `samsung-health-data-api-1.1.0.aar` (check the downloaded filename).
- Android Studio with Android SDK Platform **36**, Android SDK Build Tools/platform tools as needed, and a **JDK 17-compatible toolchain**. The project's Gradle version is **9.5.1**, Android Gradle Plugin **8.13.2**, and Kotlin **2.4.21** in this source snapshot.
- As this is only for development and testing purposes, USB debugging or another Android Studio-supported device-deployment method, plus a USB cable or configured wireless debugging.
- A reachable, externally reacheable HTTPS-enabled Home Assistant installation and a dedicated Home Assistant account with a long-lived access token.

Official references: [Samsung Data SDK](https://developer.samsung.com/health/data/overview.html), [Samsung Health developer mode](https://developer.samsung.com/health/data/guide/developer-mode.html), and [Android phone developer options](https://developer.samsung.com/health/data/guide/phone-developer-options.html).

## 3. Obtain and open the Android source

1. Download the repository ZIP or clone the repository when it is public.
2. Extract it to your development computer.
3. In Android Studio, select **Open** and open the **inner Gradle project**, not the repository root:

   ```text
   samsung-health-ha-bridge-main/
     android/
       SamsungHealthReporter/
         settings.gradle.kts
         app/
         library/
         samsung-health-data-stub/
   ```

4. Install any Android SDK Platform or tools prompted by Android Studio. Verify that Android Studio is using the correct JDK and Gradle toolchain.

### Gradle wrapper

The repository includes the verified Gradle 9.5.1 wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` and `gradle-wrapper.properties`). Developers can use `./gradlew` (or `gradlew.bat` on Windows) from the inner Android Studio project directory. The wrapper JAR is checked against its official SHA-256, `497c8c2a7e5031f6aa847f88104aa80a93532ec32ee17bdb8d1d2f67a194a9c7`.

## 4. Install Samsung's real SDK AAR locally

1. Sign into the [Samsung Health Data SDK download page](https://developer.samsung.com/health/data/overview.html) and obtain the SDK under and agreeing to Samsung's terms to use this only for development and testing.
2. Extract the downloaded SDK package.
3. Create this directory if it does not exist:

   ```text
   android/SamsungHealthReporter/library/libs/
   ```

4. Copy the official AAR into that directory, for example:

   ```text
   android/SamsungHealthReporter/library/libs/samsung-health-data-api-1.1.0.aar
   ```

5. **Do not commit the AAR to Git, include it in a project ZIP, or upload it as a separate download.** The source repository intentionally excludes it.

**Build safeguard:** Installable APK builds require the genuine Samsung SDK AAR and fail if it is absent. The stub is available only through explicit library-only unit testing. Never use a stub build as a replacement for SDK access.

The `:library` module uses Samsung's SDK as a compile-only dependency; `:app` packages it as an app implementation dependency when the real AAR is present.

## 5. Prepare the development phone

There are **two different developer settings**, serving different purposes:

**A. Android Developer Options and USB debugging.** These let Android Studio install/debug the app on the phone. Follow [Samsung's phone developer-options guide](https://developer.samsung.com/health/data/guide/phone-developer-options.html), then enable USB debugging for your chosen deployment method. Accept the debugging authorization prompt for your trusted computer.

**B. Samsung Health Data SDK developer mode, with READ access.** This allows an unregistered developer build to connect to the Samsung Health Data SDK for legitimate development/debugging. It is configured *inside Samsung Health*, not Android's system-wide Developer Options. Follow [Samsung's developer-mode procedure](https://developer.samsung.com/health/data/guide/developer-mode.html), accept Samsung's notice, and enable **Developer Mode for Data Read**. The bridge reads data; it does not need data-write privileges or a write access code.

Samsung explicitly restricts SDK developer mode to development/testing and says not to provide its setup guide to consumer installations. Keep this section in **developer documentation**, not in a consumer installation flow.

## 6. Install the Android developer build

In Android Studio:

1. Connect your unlocked physical Android phone and confirm that it appears as an authorized deployment target.
2. Select the **`app`** run configuration.
3. Select a **debug** build, with the **real SDK AAR** present and no stub-forcing Gradle property.
4. Click **Run**. Android Studio should build, sign with the developer's debug key, install, and launch the app.

Command-line alternative, from `android/SamsungHealthReporter` **after repairing the wrapper**:

**Windows PowerShell:**

```powershell
.\gradlew.bat :app:installDebug
```

**macOS/Linux:**

```sh
./gradlew :app:installDebug
```

If you need only a debug APK for an authorized development device:

```sh
# macOS/Linux; on Windows use .\gradlew.bat
./gradlew :app:assembleDebug
```

The expected Gradle output location is `app/build/outputs/apk/debug/app-debug.apk`. This is a **developer build**, not a Play Store listing or a completed consumer APK.

The current Android application ID is `com.kvs.samsunghealthreporter.example` and the app version is **0.3.3**. Changing signing keys between computers can prevent an in-place update; uninstalling to resolve such conflicts may erase stored setup, encrypted token and synchronization cursors. Back up your setup through secure means and do not put credentials into source control.

## 7. Prepare the current Home Assistant development receiver

> **DEVELOPMENT AND TESTING ONLY.** The developer completed the migration from the legacy YAML receiver to a UI-configured integration with 103 registered sensor entities on November 19, 2026. The Home Assistant receiver and Android app are configured independently for development testing.

1. Locate the [Home Assistant integration sources](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/custom_components/samsung_health_bridge) in the project root, at `custom_components/samsung_health_bridge/`. Do not install any legacy `ha/custom_components/` source tree.
2. For manual development installation, place the approved files into `/config/custom_components/samsung_health_bridge/`, first backing up any existing installation. Marketplace/HACS can manage the integration files when configured to use the development repository. **It never installs the Android APK.**
3. Validate the Home Assistant configuration and restart HA Core as needed for file changes.
4. Open **Settings → Devices & services → Add integration**, search for **Samsung Health Bridge**, then complete the one-step configuration flow. **Do not add a new `samsung_health_bridge:` entry to `configuration.yaml`** for UI-based installation. Do not run the legacy YAML receiver alongside the registered-entity version.
5. Confirm that the integration appears with registered `sensor.samsung_bridge_*` entities. The current implementation declares 103 potential entities, not necessarily 103 populated values.
6. On the Home Assistant server, create an appropriate long-lived access token under the intended development/testing account's profile, and keep it private. The Android application must be able to reach the server using an **HTTPS base URL**, such as `https://ha.example.org`; the app adds `/api/samsung_health_bridge/sync` automatically.
7. On the **phone**, configure the token and URL, request authorized Samsung Health READ permissions, press **SYNC ONCE NOW (TEST)**, and confirm `sensor.samsung_bridge_last_received` and the applicable health measurements update. Only then enable background synchronization as appropriate for the test.

The receiver stores health records in its own private SQLite database; in the developer's HAOS setup it is `/config/samsung_health_bridge/records.sqlite3`, outside the installed integration directory. Never commit that database, HA tokens, or private configuration. See [Home Assistant developer installation](HOME_ASSISTANT_INSTALL.md) and [Galaxy Watch data-path setup](WATCH_DEVELOPER_SETUP.md).

## Samsung Galaxy phone: background operation and battery setup

For development testing on Samsung Galaxy phones, configure the installed **SamsungHealthReporter / Samsung Health Bridge** app before testing hourly synchronization.

1. Go to **Settings → Battery → Background usage limits**. Under **Never auto sleeping apps** or **Never sleeping apps**, add the development app. If listed under **Sleeping apps** or **Deep sleeping apps**, remove it from those lists.
2. Open **Settings → Apps → SamsungHealthReporter → Battery**. If offered, select **Unrestricted** background battery use. This may increase battery consumption.
3. Open **Settings → Apps → SamsungHealthReporter → Mobile data**. Allow background network activity, and permit Data Saver exceptions if the test requires mobile data.
4. Avoid using **Force stop** or clearing the development app's storage. Either may affect scheduled work, saved connection configuration or sync checkpoints.
5. Verify Samsung Health and, where applicable, Samsung Health Monitor have synchronized the watch measurements to the phone.
6. After any phone reboot or app update, open the app, check **Enabled: true**, run **SYNC ONCE NOW (TEST)** as needed and examine **REFRESH SYNC DIAGNOSTICS**.

A requested 60-minute interval is not a fixed deadline. WorkManager can be delayed by Doze, battery-saving policies, network connectivity and other constraints. Samsung's battery instructions: https://www.samsung.com/us/support/answer/ANS10003442/ ; Android's scheduling reference: https://developer.android.com/reference/androidx/work/PeriodicWorkRequest .

## 8. Every control on the Android development screen (v0.3.3)

The screenshot and the repository's `BridgeActivity.kt` match the following interface. This is a **developer/testing configuration screen**. No separate Galaxy Watch application is supplied by this repository. The regular Samsung watch apps handle watch-to-phone synchronization.

### 8.1 Header and application version

- **Samsung Health → Home Assistant (development test)** identifies the screen and its intended use.
- **Bridge version: 0.3.3** comes from the installed Android application's package version. It can differ from the version in the Home Assistant receiver's `manifest.json`.
- **Help: setup & background syncing** opens the built-in help dialog. It explains the architecture, how to recover after a phone reboot, WorkManager scheduling delays, Samsung battery restrictions, security, and troubleshooting. It does not request permissions or trigger synchronization.

### 8.2 Home Assistant server URL field

The first editable field contains the **HTTPS base address** of your Home Assistant installation, such as `https://ha.example.org`.

- Use the ordinary Home Assistant root URL. **Do not** append `/api/samsung_health_bridge/sync` because the bridge adds that path automatically.
- Do not add an access token, query parameters (`?`), or fragments (`#`) to the URL.
- The app requires `https://` and strips a trailing `/` when the connection is saved.
- The phone must be able to reach this address, including from the network used for background work.
- A URL accepted by the form is **not** proof that the receiver is installed, reachable, or authenticated. Verify with a manual sync.

### 8.3 Home Assistant long-lived access token field

The next field accepts a **Home Assistant long-lived access token** created in Home Assistant under the intended testing account's profile. The field masks the token while typing.

- Use a dedicated account/token if possible, understanding that Home Assistant's long-lived tokens carry the permissions of their associated account.
- Pressing **Save connection** encrypts the token using Android Keystore-backed AES-GCM and stores the ciphertext privately on the phone.
- The form clears its visible token field immediately after saving.
- **Leaving the token field blank while saving preserves the previously stored token.** It does not erase or rotate it.
- Never send a token in screenshots, source code, GitHub issues, diagnostic excerpts, or forum posts. If exposed, revoke it in HA and replace it.

### 8.4 Save connection

**SAVE CONNECTION** stores the HTTPS URL and optionally a new token. It does **not** contact Home Assistant or transmit any health data. The status line changes to *Connection saved privately. No data has been transmitted yet.*

A rejected URL produces an error on the status line. After changing HA servers or tokens, run a manual synchronization to verify the new endpoint before enabling background work. Note that changing the endpoint does not automatically reset previously saved record checkpoints.

### 8.5 Requested update interval (minutes)

The numeric field accepts a whole number from **1 through 1440**, inclusive (one minute through 24 hours). It initially shows the stored setting, **60** on a fresh install.

| Entered value | Scheduling behavior | Intended use |
| --- | --- | --- |
| **1–14 minutes** | Best-effort chain of delayed one-time WorkManager jobs | Rapid development testing; not a guaranteed short-interval timer |
| **15–1440 minutes** | Standard WorkManager periodic work | Normal lower-power development testing; Android may delay execution |
| **60 minutes** | Periodic work, requested hourly | The current default and a sensible first test setting |

Both modes require network connectivity and that Android does not consider the battery low. Android Doze, battery policies, and job scheduling may delay or skip the expected clock time. This is **not** continuous recording or a real-time medical alert.

### 8.6 Save update interval

**SAVE UPDATE INTERVAL** validates and stores the number entered above.

- Rejects blank, nonnumeric, zero, negative, or greater-than-1440 values.
- When background synchronization is already enabled **and the value changes**, it replaces the existing background schedule with a new one.
- When background synchronization is disabled, it saves the preference but does **not** start automatic work.
- The visible **Last result** line is not necessarily a record of this button's message. It is a separate status area and may be refreshed when the screen resumes.

### 8.7 Request 3 initial READ permissions (core mode)

**REQUEST 3 INITIAL READ PERMISSIONS** asks Samsung Health for read access to:

1. `BLOOD_PRESSURE`
2. `ENERGY_SCORE`
3. `SLEEP`

This selects the **core synchronization scope** for future work. It does not remove Samsung permissions previously granted for other data types; it simply restricts what the bridge requests and processes in core mode.

A status such as `Read permissions granted: 3/3` reports the authorization results. If fewer are granted, the worker skips those it cannot read. Some watch-origin blood-pressure records are filtered by the Samsung Health Monitor source application, so manually entered BP records may not be forwarded by this bridge.

### 8.8 Request ALL supported READ permissions (expanded mode)

**REQUEST ALL SUPPORTED READ PERMISSIONS (INCLUDING STEPS, GOALS, ACTIVITY TOTALS AND PROFILE)** requests the wider set of categories defined by the included SamsungHealthReporter library, including supported observable records, aggregate-only types, and profile-record access.

- This is the correct option when testing the bridge's **expanded mode**.
- The request uses **READ permissions**. It does not grant the bridge data-writing privileges.
- The number of requested types is based on the library and version. In the project's previous test, the app reported **24/24**, but other devices, SDK releases, or authorization choices may differ.
- The bridge tracks this expanded-mode selection even if some permissions are denied. Denied/unsupported categories are skipped.
- The separate exercise GPS route/location permission is intentionally not included by default.
- Expanded mode uses additional daily aggregates over the most recent seven days, as well as individual record categories where permitted.

For testing one or two data categories only, avoid broad permission grants unless the expanded paths are specifically what you are evaluating. Profile data can be sensitive.

### 8.9 Sync once now (test)

**SYNC ONCE NOW (TEST)** queues a one-time WorkManager synchronization. It does **not** require background syncing to be enabled.

- It is queued, **not necessarily executed immediately**, because Android still applies its network and battery constraints.
- If a manual job is already queued/running, the app uses the existing job rather than creating a duplicate.
- When first run on a clean installation, the worker can backfill older data in bounded pages. It handles **up to eight pages of 50 records per run** across the observable categories and resumes on later runs if incomplete.
- Default first-pass lookback: **30 days** for blood pressure, Energy Score, and sleep; **2 days** for heart rate; **7 days** for most other records. Daily aggregates cover the **last seven days**.
- Later runs use change checkpoints and send newly added/modified records and deletions. Unchanged aggregate data is not resent simply because the button was pressed.
- A result such as `SUCCESS ... sent 0 records` can be entirely normal: no changes were found to transmit. It **does not** prove that all permissions, data types, and HA entities are present.
- When successful, the Home Assistant receiver acknowledges the POST before the sender advances its checkpoint. On an HTTP failure, the worker retries according to WorkManager policy.

After pressing the button, use **REFRESH SYNC DIAGNOSTICS** and review the status fields; do not interpret *Sync queued* as *Sync succeeded*.

### 8.10 Enable background sync (selected interval)

**ENABLE BACKGROUND SYNC (SELECTED INTERVAL)** schedules repeated syncing using the saved interval.

- Requires a previously saved HTTPS base URL and a nonempty stored HA token.
- Saves `Enabled: true` and refreshes/replaces its automatic WorkManager job.
- Executes without leaving this screen open or keeping the phone awake. Normal app switching, screen timeout, and reboot do not ordinarily require you to press Enable again.
- An Android **force stop**, disabled network access, severe battery restrictions, revoked Samsung permissions, or clearing the app's data can prevent further delivery.
- The requested interval is **not a guarantee** of an exact execution time.

The worker is not an always-running background service. It wakes when Android decides eligible work can run, retrieves changes, uploads them, and exits.

### 8.11 Disable background sync

**DISABLE BACKGROUND SYNC** sets the enabled flag to false and cancels the automatic periodic/rapid schedule. It also cancels pending work in the app's dedicated manual-work queue.

It does **not** erase stored Samsung readings in Home Assistant, delete the receiver's SQLite data, remove Samsung permissions, or clear your saved connection token. To test manually again afterward, press **SYNC ONCE NOW (TEST)**.

### 8.12 Last result / Enabled / Interval status

The gray status line summarizes three independent facts:

| On-screen part | Meaning |
| --- | --- |
| `Last result: SUCCESS ... sent N records` | Last worker-reported result and number of records uploaded during that worker run |
| `Last result: FAILED ...` | A run hit a failure, with diagnostic stage and exception/status context |
| `Last result: CANCELLED ...` | Android or WorkManager interrupted a running job; this is not automatically an SDK defect |
| `Last result: Partial backfill ...` | The bounded initial upload needs one or more additional runs to finish |
| `Enabled: true / false` | Whether automatic recurring work is enabled, not whether a job is running right now |
| `Interval: 60 min` | Saved requested schedule interval, not a promised exact wall-clock execution time |

The **Last result** timestamp is formatted in the phone's local timezone. The detailed diagnostic event time below it is stored in UTC.

### 8.13 Refresh sync diagnostics

**REFRESH SYNC DIAGNOSTICS** reloads the diagnostic text in the lower portion of the screen from the app's private diagnostic store. It does not initiate a new Samsung read or HA upload. Use it after a queued run has had time to execute or after reopening the screen.

### 8.14 Copy sync diagnostics

**COPY SYNC DIAGNOSTICS** places the same diagnostic report on the Android clipboard and displays a confirmation. The reporter intentionally excludes tokens, full URLs, personal health values and measurement-source identifiers from its diagnostic event report.

**Review the copied text before sharing it anyway.** It can contain timestamps, job fragments, operational labels, and HTTP status. The system clipboard can also be accessed by some other applications or keyboard services according to Android rules, so clear it when finished.

### 8.15 Diagnostic fields and recent operations (lower screen)

The scrollable diagnostic section contains:

| Field | What it tells you |
| --- | --- |
| `State` | Latest stored diagnostic state such as RUNNING, SUCCESS, NOTE, FAILED, PARTIAL, or CANCELLED |
| `Last operation` | Last named phase of the worker, e.g. checking connection, checking Samsung READ permissions, uploading an aggregate, or finished |
| `Time (UTC)` | UTC timestamp of the most recent recorded diagnostic event, with a trailing `Z` |
| `Summary` | Summary from the latest finished/partial/failed work, such as `sent 0 records`; it is not a list of medical measurements |
| `Recent operations` | Up to roughly 36 recent dated operation lines. Scroll down to inspect the sequence of jobs and stages |

The worker writes stage markers before operations that may suspend or be interrupted, which helps distinguish **Samsung SDK waiting**, **HA upload errors**, **Android cancellation**, and **normal completion**.

### 8.16 Practical first-use sequence

1. Confirm that Samsung Health on the phone is working and Samsung SDK development READ access is enabled for authorized debugging.
2. Install/start the Home Assistant receiver first.
3. Enter the **HTTPS base URL** and **HA long-lived token**, then press **SAVE CONNECTION**.
4. Press **REQUEST ALL SUPPORTED READ PERMISSIONS** for expanded testing. Confirm how many grants were actually approved.
5. Leave the requested interval at **60**, and press **SAVE UPDATE INTERVAL**.
6. Press **SYNC ONCE NOW (TEST)**, then review **Last result** and **REFRESH SYNC DIAGNOSTICS**. Verify the Home Assistant last-received sensor and relevant entities.
7. Only after a successful end-to-end test, press **ENABLE BACKGROUND SYNC**.
8. If later troubleshooting is needed, press **COPY SYNC DIAGNOSTICS** and review the content before posting a sanitized excerpt to GitHub.

**No extra bridge application goes on the watch.** The existing Samsung watch apps must first synchronize their measurements to Samsung Health on the phone.

## 9. Verify the end-to-end development test

On the phone:

- Confirm permissions were granted rather than merely requested.
- Check **Last result** after **Sync once now**; a successful run may legitimately report **0 new records**.
- Use **Refresh sync diagnostics** if permission, SDK, or HTTP stages fail. **Copy sync diagnostics** is designed to exclude tokens and individual health values, but review any diagnostics before sharing.

In Home Assistant:

- Look for `sensor.samsung_bridge_last_received` updating after a successful request.
- Look for available `sensor.samsung_bridge_*` entities and record counters that correspond to data actually present and permitted.
- If an entity is absent, check the phone's SDK permissions and the app diagnostic stages before assuming the receiver is broken.

Useful troubleshooting distinctions:

| Symptom | Likely next check |
| --- | --- |
| App builds but cannot read Samsung Health | Real AAR present instead of stub? Samsung Health Data SDK developer read mode active? |
| Samsung SDK policy/permission error 2003 | Development-mode access, app identity/signature, and Samsung's app verification rules |
| No permissions granted | Developer authorization in Samsung Health; Samsung Health version; supported data type |
| HTTP 401 or 403 | Home Assistant token, account and authorization |
| HTTP 404 | HA receiver loaded, URL points to correct HA server, `/api/.../sync` route registered |
| Background sync delayed | Android Doze, background restrictions, battery settings, network access |
| Successful sync, no new records | No changes since previous checkpoint or data not present in Samsung Health |
| Cannot update an installed debug APK | Debug signing certificate mismatch; changing certificates can require reinstall and configuration loss |

## 10. Watch setup and limitations

This repository does **not** contain a watch module or Wear OS APK. Nothing from it is installed on the watch. For watch-derived data, use supported Samsung Health and Samsung Health Monitor functionality on the watch, confirm synchronization to their corresponding phone apps, and verify relevant records are available in Samsung Health's store on the phone. Samsung Health Data SDK visibility varies by record type, device, region, and Samsung policy. It does not follow that everything visible in Samsung Health Monitor is SDK-readable.

## Security and SDK rules for developers

- Keep tokens and private health data out of source control and screenshots.
- Keep the genuine Samsung SDK AAR local in the ignored `library/libs/` directory. Obtain it from Samsung.
- Use developer mode only for development and testing under Samsung's SDK requirements.
- For source-only checks, run `python3 tools/verify_source_only.py --repository . --history` from the repository root.
- The Home Assistant integration, Android phone app and Samsung watch software are separate components. The phone app is not installed by HACS.

