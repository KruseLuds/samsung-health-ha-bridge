package com.kvs.samsunghealthreporter.example.bridge

import android.os.Bundle
import android.app.AlertDialog
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import com.kvs.samsunghealthreporter.SamsungHealthReporter
import com.kvs.samsunghealthreporter.model.type.HealthType
import kotlinx.coroutines.launch

/** Setup/diagnostics only. No permanently running Activity or foreground service. */
class BridgeActivity : ComponentActivity() {
    private lateinit var prefs: BridgePrefs
    private lateinit var status: TextView
    private lateinit var url: EditText
    private lateinit var token: EditText
    private lateinit var interval: EditText
    private lateinit var diagnosticText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = BridgePrefs(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 48, 32, 32)
        }
        fun label(t: String) = TextView(this).apply { text = t; textSize = 17f; setPadding(0, 10, 0, 10) }
        fun button(t: String, action: () -> Unit) = Button(this).apply { text = t; setOnClickListener { action() } }
        root.addView(label("Samsung Health → Home Assistant (development test)"))
        val installedVersion = try {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "unknown"
        } catch (_: Exception) { "unknown" }
        root.addView(TextView(this).apply {
            text = "Bridge version: $installedVersion"
            textSize = 14f
            setPadding(0, 0, 0, 12)
        })
        root.addView(button("Help: setup & background syncing") { showBridgeHelp() })
        url = EditText(this).apply { hint = "https://your-ha.example.com"; setSingleLine(); setText(prefs.endpoint) }
        root.addView(url)
        token = EditText(this).apply {
            hint = "Paste HA long-lived access token"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            setSingleLine()
        }
        root.addView(token)
        root.addView(button("Save connection") {
            val candidate = url.text.toString().trim().trimEnd('/')
            if (!candidate.startsWith("https://") || candidate.contains('?') || candidate.contains('#')) {
                status.text = "HTTPS URL required. Do not include query parameters or a token in the URL."
            } else {
                prefs.endpoint = candidate
                if (token.text.toString().isNotBlank()) prefs.setToken(token.text.toString())
                token.setText("")
                status.text = "Connection saved privately. No data has been transmitted yet."
            }
        })
        root.addView(label("Requested update interval (minutes): 1–1440. 1–14 = best-effort rapid testing; 15+ = battery-friendly periodic sync. Android may delay either."))
        interval = EditText(this).apply {
            hint = "Minutes (for example 1, 15 or 60)"
            inputType = InputType.TYPE_CLASS_NUMBER
            setSingleLine()
            setText(prefs.syncMinutes.toString())
        }
        root.addView(interval)
        root.addView(button("Save update interval") {
            val value = interval.text.toString().trim().toIntOrNull()
            if (value == null || value !in 1..1440) {
                status.text = "Enter a whole number from 1 to 1440 minutes."
            } else {
                BridgeScheduler.saveInterval(this, value)
                status.text = "Saved: ${BridgeScheduler.intervalDescription(value)}. " +
                    (if (prefs.periodicEnabled) "Background schedule updated." else "Enable background sync when ready.")
            }
        })
        root.addView(button("Request 3 initial READ permissions") { requestPermissions(false) })
        root.addView(button("Request ALL supported READ permissions (including steps, goals, activity totals and profile)") { requestPermissions(true) })
        root.addView(button("Sync once now (test)") { BridgeScheduler.now(this); status.text = "Sync queued. Return later and reopen setup to inspect result." })
        root.addView(button("Enable background sync (selected interval)") {
            try {
                BridgeScheduler.enable(this)
                status.text = "Enabled: ${BridgeScheduler.intervalDescription(prefs.syncMinutes)}. " +
                    "Android chooses exact execution times."
            } catch (e: Exception) {
                status.text = "Could not enable: ${e.message?.take(180)}"
            }
        })
        root.addView(button("Disable background sync") { BridgeScheduler.disable(this); status.text = "Background sync disabled." })
        status = label("Last result: ${formatLastResult(prefs.lastResult)} | Enabled: ${prefs.periodicEnabled} | Interval: ${prefs.syncMinutes} min")
        root.addView(status)
        root.addView(button("Refresh sync diagnostics") { refreshDiagnostics() })
        root.addView(button("Copy sync diagnostics") {
            val text = BridgeDiagnostics(this).report()
            val manager = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            manager.setPrimaryClip(ClipData.newPlainText("Samsung Bridge diagnostic events", text))
            status.text = "Diagnostics copied (no tokens or health values)."
        })
        diagnosticText = TextView(this).apply {
            textSize = 12f
            setPadding(0, 14, 0, 10)
        }
        root.addView(diagnosticText)
        refreshDiagnostics()
        setContentView(ScrollView(this).apply { addView(root, ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT) })
    }

    override fun onResume() {
        super.onResume()
        if (::status.isInitialized) status.text = "Last result: ${formatLastResult(prefs.lastResult)} | Enabled: ${prefs.periodicEnabled} | Interval: ${prefs.syncMinutes} min"
        refreshDiagnostics()
    }

    /** Only the displayed date changes; the worker keeps its original UTC diagnostic value. */
    private fun formatLastResult(raw: String): String {
        val utcStamp = Regex("""\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z""")
        val localFormat = DateTimeFormatter.ofPattern("EEE MM/dd '@' hh:mm:ssa", Locale.US)
            .withZone(ZoneId.systemDefault())
        return utcStamp.replace(raw) { match ->
            try {
                localFormat.format(Instant.parse(match.value))
                    .replace("AM", "am").replace("PM", "pm")
            } catch (_: Exception) {
                match.value // Retain original diagnostic text if timestamp cannot be parsed.
            }
        }
    }

    private fun showBridgeHelp() {
        val help = """
            HOW THE BRIDGE WORKS
            The app requests read-only Samsung Health data, then uploads new records to your Home Assistant HTTPS receiver. A dedicated HA long-lived token is encrypted with Android Keystore.

            DO I HAVE TO KEEP THE APP OPEN?
            No. Once background sync is enabled, Android WorkManager runs it without the screen or app being open. There is no always-on service. Closing the screen or swiping away the app normally does not cancel scheduled work.

            WHAT HAPPENS AFTER A PHONE REBOOT?
            WorkManager persists its schedule across normal app restarts and device reboots. After reboot, unlock the phone, ensure network access, and allow Android to resume eligible work. You normally do not need to reopen the app or press Enable again. Verify with Last result or Refresh sync diagnostics after enough time has passed.

            WHEN WILL IT SYNCHRONIZE?
            The interval is a request, not an exact timer. 15 minutes or longer uses Android periodic work; 1–14 minutes uses best-effort rapid TEST scheduling. Network access, battery level, Doze, power saving, Samsung SDK availability, and Android background limits may delay execution. A success with 'sent 0 records' can mean there is no new data.

            SAMSUNG BATTERY SETTINGS
            To avoid missed runs, check Settings > Battery > Background usage limits. Do not place SamsungHealthReporter in Deep sleeping apps. If the phone keeps suppressing sync, consider adding it to Never sleeping apps (name may vary), while monitoring battery usage. Force-stopping the app can suspend work until it is opened again.

            REQUIREMENTS AND RECOVERY
            Keep Samsung Health and its developer-mode READ access available. Do not uninstall the bridge or clear its app data; that can erase its token, settings, and sync checkpoints. After an OS update, reboot, or a long gap, open the app and check Enabled, Last result, and diagnostics. If access was revoked, request READ permissions again. If scheduling remains stalled, press Enable background sync to refresh the schedule.

            PRIVACY AND SECURITY
            Use HTTPS and a dedicated HA account/token with the minimum available permissions. Do not share your token or health records. This is a locally built, source-only development/test bridge; it is not a medical monitoring service.
        """.trimIndent()
        AlertDialog.Builder(this)
            .setTitle("Samsung Health Bridge help")
            .setMessage(help)
            .setPositiveButton("Close", null)
            .show()
    }

    private fun refreshDiagnostics() {
        if (::diagnosticText.isInitialized) diagnosticText.text = BridgeDiagnostics(this).report()
    }

    private fun requestPermissions(all: Boolean) {
        lifecycleScope.launch {
            try {
                val types = if (all) BridgeExtras.allReadTypes else
                    setOf(HealthType.BLOOD_PRESSURE, HealthType.ENERGY_SCORE, HealthType.SLEEP)
                val granted = SamsungHealthReporter(this@BridgeActivity).manager.requestPermissions(
                    this@BridgeActivity, read = types
                )
                prefs.allReadTypes = all
                status.text = "Read permissions granted: ${granted.size}/${types.size}. " +
                    "Any ungranted types are skipped in the worker."
            } catch (e: Exception) {
                status.text = "Read permissions failed: ${e.javaClass.simpleName}: ${e.message?.take(140)}"
            }
        }
    }
}
