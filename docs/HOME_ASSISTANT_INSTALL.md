# Samsung Health Bridge: Home Assistant developer setup

**FOR SOFTWARE DEVELOPMENT AND TESTING ONLY.** The integration is independent of Samsung. The Android app must be installed separately on a compatible phone, and no bridge software is installed on the watch.

## Components

| System | Development component |
| --- | --- |
| Galaxy Watch | Existing Samsung Health / Samsung Health Monitor apps, if supported |
| Android phone | [`android/SamsungHealthReporter/`](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter), built with the Samsung SDK obtained separately from Samsung |
| Home Assistant | `custom_components/samsung_health_bridge/`, installed through Marketplace/HACS as a custom repository or placed manually |
| Optional standard data path | Home Assistant Companion App and Google Health Connect on the phone |

## Install the Home Assistant integration

1. Install the repository as a custom integration in Home Assistant Marketplace/HACS when that facility supports custom repositories. Developers using manual installation can place `custom_components/samsung_health_bridge/` under `/config/custom_components/`.
2. Restart Home Assistant Core when required.
3. Go to **Settings → Devices & services → Add integration** and select **Samsung Health Bridge**.
4. Submit the configuration dialog. The reference development installation registered **103 sensor entities**.
5. Check `sensor.samsung_bridge_last_received` and `sensor.samsung_bridge_watch_bp_systolic` under **Developer Tools → States**, where matching source records are available.
6. On the phone, configure the HTTPS Home Assistant base URL and long-lived access token, then press **SYNC ONCE NOW (TEST)**. Confirm `sensor.samsung_bridge_last_received` updates. A zero-record result may mean no changed records need uploading.
7. When the manual test works, enable the requested background interval in the Android app. See [phone setup and battery settings](ANDROID_DEVELOPER_INSTALL.md).

The Android app is **not** installed by Marketplace/HACS. Obtain its source separately from the [Android Studio project](https://github.com/KruseLuds/samsung-health-ha-bridge/tree/main/android/SamsungHealthReporter).

## Migrating from an older YAML receiver

Previous development installations may contain a top-level `samsung_health_bridge:` YAML entry and raw sensor states. **Never run the YAML receiver and UI-configured integration simultaneously.** That can collide with the same entity IDs or HTTP routes. Back up the HA configuration and SQLite file, remove the old entry at the controlled cutover, restart Core, configure through the UI, and check that original entity IDs are preserved.

## Data and troubleshooting

- Ingest: `/api/samsung_health_bridge/sync`
- History: `/api/samsung_health_bridge/history`
- Daily calorie/weight history: `/api/samsung_health_bridge/calorie_weight_daily`
- SQLite records in HAOS: `/config/samsung_health_bridge/records.sqlite3`, outside the integration code directory.
- Personal health records, long-lived access tokens and SQLite databases must not be added to Git.
- The integrated data does not automatically install a custom health dashboard. Developers can create their own dashboards from the sensors and historical endpoints.
- If a manual sync fails, inspect Home Assistant Core logs and the Android application's diagnostics; share only sanitized diagnostic details.

See [Android developer guide](ANDROID_DEVELOPER_INSTALL.md), [watch developer guide](WATCH_DEVELOPER_SETUP.md), and [SDK requirements](SDK_REQUIREMENTS.md).
