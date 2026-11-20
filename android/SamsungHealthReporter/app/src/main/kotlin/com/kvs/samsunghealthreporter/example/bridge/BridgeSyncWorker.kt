package com.kvs.samsunghealthreporter.example.bridge

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.kvs.samsunghealthreporter.SamsungHealthReporter
import com.kvs.samsunghealthreporter.model.SourceFilter
import com.kvs.samsunghealthreporter.model.TimeRange
import com.kvs.samsunghealthreporter.model.payload.Sample
import com.kvs.samsunghealthreporter.model.type.HealthType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.concurrent.CancellationException
import android.os.Build

/** Non-resident, battery-conscious change synchronization. Never invokes SDK writer. */
class BridgeSyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    private val prefs = BridgePrefs(context)
    private val diag = BridgeDiagnostics(context)
    private val initial = setOf(HealthType.BLOOD_PRESSURE, HealthType.ENERGY_SCORE, HealthType.SLEEP)
    private val maxPagesPerRun = 8 // bound work duration; future periodic runs resume backfill

    override suspend fun doWork(): Result {
        diag.start(id.toString().take(8), inputData.getBoolean(BridgeScheduler.MANUAL_SYNC, false))
        val result = syncOnce()
        // The short-interval test chain only advances after a successful worker.
        // Failed work uses WorkManager backoff; we never spin rapidly on errors.
        val slot = inputData.getString(BridgeScheduler.RAPID_SLOT)
        if (slot != null && result is Result.Success && !isStopped) {
            BridgeScheduler.scheduleAfterSuccessfulRapid(
                applicationContext, slot,
                inputData.getInt(BridgeScheduler.SCHEDULE_GENERATION, -1)
            )
        }
        return result
    }

    private suspend fun syncOnce(): Result {
        diag.stage("checking connection")
        val endpoint = prefs.endpoint
        val token = try { prefs.token() } catch (_: Exception) { null }
        if (!endpoint.startsWith("https://") || token.isNullOrEmpty()) {
            prefs.lastResult = "NOT CONFIGURED: HTTPS HA URL/token required"
            diag.failed(diag.lastStage, "No configured connection")
            return Result.success()
        }
        if (!SamsungHealthReporter.isAvailable(applicationContext)) {
            prefs.lastResult = "Samsung Health unavailable"
            diag.failed(diag.lastStage, "Samsung Health unavailable")
            return Result.retry()
        }
        return try {
            diag.stage("connecting Samsung Health SDK")
            val reporter = SamsungHealthReporter(applicationContext)
            val requested = if (prefs.allReadTypes) BridgeExtras.allReadTypes else initial
            diag.stage("SDK: checking READ permissions")
            val granted = reporter.manager.grantedPermissions(read = requested).map { it.type }.toSet()
            if (granted.isEmpty()) {
                prefs.lastResult = "No granted Samsung READ permissions; open setup on phone"
                diag.failed(diag.lastStage, "No Samsung READ permissions")
                return Result.success()
            }
            var pagesProcessed = 0
            var totalRecords = 0
            for (type in requested) {
                if (type !in granted || !type.isReadable || !type.isObservable) continue
                if (isStopped) {
                    diag.cancelled(diag.lastStage, "Worker was stopped")
                    return Result.retry()
                }
                val key = type.identifier
                val cursor = prefs.cursor(key)
                if (cursor == 0L) {
                    // First-time snapshot. Page token and original anchor survive process death.
                    var anchor = prefs.anchor(key)
                    if (anchor == 0L) { anchor = System.currentTimeMillis(); prefs.setAnchor(key, anchor) }
                    val days = when (type) {
                        HealthType.HEART_RATE -> 2
                        HealthType.BLOOD_PRESSURE, HealthType.ENERGY_SCORE, HealthType.SLEEP -> 30
                        else -> 7
                    }
                    var nextPage = prefs.page(key)
                    do {
                        diag.stage("SDK: backfill $key page ${pagesProcessed + 1}")
                        val page = reporter.reader.readPage(
                            type, TimeRange.lastDays(days, anchor), pageSize = 50, pageToken = nextPage,
                            source = bpSource(type)
                        )
                        val rows = page.items.map { JSONObject(it.json) }
                        if (rows.isNotEmpty()) {
                            diag.stage("HA: uploading $key backfill (${rows.size} records)")
                            post(endpoint, token, key, rows, emptyList(), "backfill")
                            totalRecords += rows.size
                        }
                        nextPage = page.nextPageToken
                        prefs.setPage(key, nextPage)
                        pagesProcessed++
                        if (nextPage == null) {
                            // A small overlap guarantees updates occurring during the snapshot aren't missed.
                            prefs.setCursor(key, anchor - 60_000L)
                            prefs.setAnchor(key, 0L)
                        }
                        if (pagesProcessed >= maxPagesPerRun) {
                            prefs.lastResult = "Partial backfill; $totalRecords records accepted. Resume at next run."
                            diag.partial("$totalRecords accepted; resume on next run")
                            return Result.success()
                        }
                    } while (nextPage != null)
                } else {
                    diag.stage("SDK: incremental changes $key")
                    val result = reporter.observer.changes(type, since = cursor)
                    val rows = result.upserted.filter { bpAllowed(type, it) }.map { JSONObject(it.json) }
                    // The Samsung change API's deletions lack source details. Preserve deletion IDs
                    // for all types, with the server only removing previously imported matching IDs.
                    val deleted = result.deletedUids
                    if (rows.isNotEmpty() || deleted.isNotEmpty()) {
                        rows.chunked(50).forEach { chunk ->
                            diag.stage("HA: uploading $key changes (${chunk.size} records)")
                            post(endpoint, token, key, chunk, emptyList(), "changes")
                            totalRecords += chunk.size
                        }
                        // Commit deletes after upserts. Cursor advances only after successful ACKs.
                        deleted.chunked(100).forEach { chunk ->
                            diag.stage("HA: deleting $key (${chunk.size} record IDs)")
                            post(endpoint, token, key, emptyList(), chunk, "changes")
                        }
                    }
                    prefs.setCursor(key, result.until)
                }
            }
            var extraStatus = ""
            if (prefs.allReadTypes) {
                diag.stage("SDK: starting aggregate operations")
                val extra = BridgeExtras.sync(
                    reporter, prefs, granted,
                    forced = inputData.getBoolean(BridgeScheduler.MANUAL_SYNC, false),
                    deliver = { kind, rows ->
                        diag.stage("HA: uploading $kind (${rows.size} records)")
                        post(endpoint, token, kind, rows, emptyList(), "aggregate")
                    },
                    stage = { operation -> diag.stage(operation) },
                    note = { operation -> diag.note(operation) },
                )
                totalRecords += extra.transmitted
                if (extra.skipped.isNotEmpty()) {
                    extraStatus = " · SDK skipped ${extra.skipped.size}: ${extra.skipped.take(3).joinToString()}"
                }
            }
            prefs.lastResult = "SUCCESS ${Instant.now()} · sent $totalRecords records$extraStatus"
            diag.complete("sent $totalRecords records$extraStatus")
            Result.success()
        } catch (e: CancellationException) {
            // WorkManager can preempt jobs (Doze, constraints, job timeout, replacement).
            // This does NOT establish a Samsung SDK API failure. Keep the original stage.
            val stage = diag.lastStage
            val reason = if (Build.VERSION.SDK_INT >= 31) "stopReason=$stopReason" else "stopReason unavailable"
            prefs.lastResult = "CANCELLED ${Instant.now()} at $stage ($reason)"
            diag.cancelled(stage, reason)
            throw e
        } catch (e: Exception) {
            val stage = diag.lastStage
            val reason = e.javaClass.simpleName + when {
                e.message?.startsWith("HA returned HTTP ") == true -> " (${e.message})"
                else -> ""
            }
            prefs.lastResult = "FAILED ${Instant.now()} at $stage: $reason"
            diag.failed(stage, reason)
            Result.retry()
        }
    }

    private fun bpSource(type: HealthType): SourceFilter? =
        if (type == HealthType.BLOOD_PRESSURE) SourceFilter.App("com.samsung.android.shealthmonitor") else null

    private fun bpAllowed(type: HealthType, sample: Sample): Boolean =
        type != HealthType.BLOOD_PRESSURE || sample.dataSource?.appId == "com.samsung.android.shealthmonitor"

    private suspend fun post(
        base: String, token: String, type: String,
        records: List<JSONObject>, deleted: List<String>, mode: String
    ) = withContext(Dispatchers.IO) {
        val payload = JSONObject()
            .put("schema", 1)
            .put("type", type)
            .put("mode", mode)
            .put("records", JSONArray().apply { records.forEach { put(it) } })
            .put("deleted_uids", JSONArray().apply { deleted.forEach { put(it) } })
            .toString().toByteArray(Charsets.UTF_8)
        val url = URL("${base.trimEnd('/')}/api/samsung_health_bridge/sync")
        val conn = (url.openConnection() as HttpURLConnection)
        try {
            conn.requestMethod = "POST"
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.connectTimeout = 12000
            conn.readTimeout = 20000
            conn.doOutput = true
            conn.outputStream.use { it.write(payload) }
            val status = conn.responseCode
            if (status !in 200..299) throw IllegalStateException("HA returned HTTP $status")
        } finally {
            conn.disconnect()
        }
    }
}
