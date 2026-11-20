package com.kvs.samsunghealthreporter.example.bridge

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.Data
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

/**
 * >=15 minutes: normal periodic WorkManager, inexact due to Doze/OS policies.
 * 1..14 minutes: best-effort test mode, alternating one-time work names.
 * Test mode is NOT a guaranteed timer; OS throttling still applies.
 */
internal object BridgeScheduler {
    private const val PERIODIC = "samsung_health_ha_periodic"
    private const val RAPID_A = "samsung_health_ha_rapid_a"
    private const val RAPID_B = "samsung_health_ha_rapid_b"
    private const val NOW = "samsung_health_ha_manual"

    const val RAPID_SLOT = "rapid_slot"
    const val SCHEDULE_GENERATION = "schedule_generation"
    const val MANUAL_SYNC = "manual_sync"

    private val constraints = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .setRequiresBatteryNotLow(true)
        .build()

    fun intervalDescription(minutes: Int): String = when {
        minutes < 15 -> "$minutes-minute rapid TEST mode (best effort, higher battery usage)"
        else -> "$minutes-minute normal periodic mode (best effort)"
    }

    fun saveInterval(context: Context, minutes: Int) {
        require(minutes in 1..1440)
        val prefs = BridgePrefs(context)
        val changed = prefs.syncMinutes != minutes
        prefs.syncMinutes = minutes
        if (changed && prefs.periodicEnabled) reschedule(context, prefs)
    }

    fun enable(context: Context) {
        val prefs = BridgePrefs(context)
        check(prefs.endpoint.startsWith("https://") && !prefs.token().isNullOrBlank()) {
            "Save a valid HTTPS HA URL and access token first"
        }
        prefs.periodicEnabled = true
        reschedule(context, prefs)
    }

    fun disable(context: Context) {
        val prefs = BridgePrefs(context)
        prefs.periodicEnabled = false
        prefs.scheduleGeneration += 1
        cancelAutomatic(context)
        WorkManager.getInstance(context).cancelUniqueWork(NOW)
    }

    private fun cancelAutomatic(context: Context) {
        val manager = WorkManager.getInstance(context)
        manager.cancelUniqueWork(PERIODIC)
        manager.cancelUniqueWork(RAPID_A)
        manager.cancelUniqueWork(RAPID_B)
    }

    private fun reschedule(context: Context, prefs: BridgePrefs) {
        prefs.scheduleGeneration += 1
        val generation = prefs.scheduleGeneration
        cancelAutomatic(context)
        val minutes = prefs.syncMinutes
        if (minutes >= 15) {
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                PERIODIC, ExistingPeriodicWorkPolicy.REPLACE,
                PeriodicWorkRequestBuilder<BridgeSyncWorker>(minutes.toLong(), TimeUnit.MINUTES)
                    .setConstraints(constraints)
                    .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.MINUTES)
                    .build()
            )
        } else {
            enqueueRapid(context, RAPID_A, "a", minutes, generation)
        }
    }

    private fun enqueueRapid(
        context: Context, name: String, slot: String, minutes: Int, generation: Int
    ) {
        val request = OneTimeWorkRequestBuilder<BridgeSyncWorker>()
            .setInitialDelay(minutes.toLong(), TimeUnit.MINUTES)
            .setInputData(Data.Builder()
                .putString(RAPID_SLOT, slot)
                .putInt(SCHEDULE_GENERATION, generation)
                .build())
            .setConstraints(constraints)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.MINUTES)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(name, ExistingWorkPolicy.REPLACE, request)
    }

    /** Called only after a successful rapid worker. Other slot prevents self-cancellation. */
    fun scheduleAfterSuccessfulRapid(context: Context, slot: String, generation: Int) {
        val prefs = BridgePrefs(context)
        if (!prefs.periodicEnabled || prefs.syncMinutes >= 15 ||
            prefs.scheduleGeneration != generation) return
        val minutes = prefs.syncMinutes
        when (slot) {
            "a" -> enqueueRapid(context, RAPID_B, "b", minutes, generation)
            "b" -> enqueueRapid(context, RAPID_A, "a", minutes, generation)
        }
    }

    fun now(context: Context) {
        WorkManager.getInstance(context).enqueueUniqueWork(
            NOW, ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<BridgeSyncWorker>()
                .setInputData(Data.Builder().putBoolean(MANUAL_SYNC, true).build())
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.MINUTES)
                .build()
        )
    }
}
