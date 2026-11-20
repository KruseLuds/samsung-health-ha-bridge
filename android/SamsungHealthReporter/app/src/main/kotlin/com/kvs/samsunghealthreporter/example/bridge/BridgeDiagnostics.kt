package com.kvs.samsunghealthreporter.example.bridge

import android.content.Context
import java.time.Instant

/**
 * Private diagnostics: operation names, run state, and exception class only.
 * Never log health records, source IDs, URLs, or bearer tokens.
 * Synchronous persistence of stage markers survives a killed worker process.
 */
internal class BridgeDiagnostics(context: Context) {
    private val prefs = context.getSharedPreferences("samsung_ha_bridge_diagnostics", Context.MODE_PRIVATE)
    private val maxLines = 36

    @Synchronized private fun event(status: String, stage: String, summary: String? = null) {
        val now = Instant.now().toString()
        val lines = (prefs.getString("events", "") ?: "").lines()
            .filter { it.isNotBlank() }.takeLast(maxLines - 1).toMutableList()
        lines.add("$now | $status | $stage")
        val edit = prefs.edit()
            .putString("events", lines.joinToString("\n"))
            .putString("last_stage", stage)
            .putString("run_state", status)
            .putString("last_event_time", now)
        if (summary != null) edit.putString("last_summary", summary.take(200))
        // commit() is intentional for durable breadcrumbs before suspend/OS cancellation.
        edit.commit()
    }

    fun start(id: String, manual: Boolean) =
        event("RUNNING", "start ${if (manual) "manual" else "scheduled"} job=$id")
    fun stage(name: String) = event("RUNNING", name)
    fun note(name: String) = event("NOTE", name)
    fun complete(summary: String) = event("SUCCESS", "finished", summary)
    fun partial(summary: String) = event("PARTIAL", "backfill paused", summary)
    fun failed(stage: String, reason: String) = event("FAILED", stage, reason)
    fun cancelled(stage: String, reason: String) = event("CANCELLED", stage, reason)

    val lastStage: String get() = prefs.getString("last_stage", "none") ?: "none"
    fun report(): String = buildString {
        append("State: ").append(prefs.getString("run_state", "Never run")).append('\n')
        append("Last operation: ").append(lastStage).append('\n')
        append("Time (UTC): ").append(prefs.getString("last_event_time", "-")).append('\n')
        append("Summary: ").append(prefs.getString("last_summary", "-")).append('\n')
        append("\nRecent operations (no health values or credentials):\n")
        append(prefs.getString("events", "-") ?: "-")
    }
}
