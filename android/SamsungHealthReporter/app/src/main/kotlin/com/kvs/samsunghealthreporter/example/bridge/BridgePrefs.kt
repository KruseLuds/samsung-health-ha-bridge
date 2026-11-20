package com.kvs.samsunghealthreporter.example.bridge

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Private configuration. Bearer token is encrypted with an Android Keystore key. */
internal class BridgePrefs(context: Context) {
    private val prefs = context.getSharedPreferences("private_samsung_ha_bridge", Context.MODE_PRIVATE)
    private val alias = "samsung_ha_bridge_token_v1"

    var endpoint: String
        get() = prefs.getString("endpoint", "") ?: ""
        set(value) { prefs.edit().putString("endpoint", value.trimEnd('/')).apply() }

    var allReadTypes: Boolean
        get() = prefs.getBoolean("all_types", false)
        set(value) { prefs.edit().putBoolean("all_types", value).apply() }

    var periodicEnabled: Boolean
        get() = prefs.getBoolean("periodic_enabled", false)
        set(value) { prefs.edit().putBoolean("periodic_enabled", value).apply() }

    /** Requested interval in minutes. Android may delay background execution. */
    var syncMinutes: Int
        get() = prefs.getInt("sync_minutes", 60).coerceIn(1, 1440)
        set(value) {
            require(value in 1..1440) { "Interval must be 1–1440 minutes" }
            prefs.edit().putInt("sync_minutes", value).apply()
        }

    /** Incrementing generation invalidates jobs from previous schedules. */
    var scheduleGeneration: Int
        get() = prefs.getInt("schedule_generation", 0)
        set(value) { prefs.edit().putInt("schedule_generation", value).commit() }

    var lastResult: String
        get() = prefs.getString("last_result", "Never run") ?: "Never run"
        set(value) { prefs.edit().putString("last_result", value.take(500)).apply() }

    fun cursor(type: String): Long = prefs.getLong("cursor_$type", 0L)
    fun setCursor(type: String, value: Long) { prefs.edit().putLong("cursor_$type", value).apply() }
    fun anchor(type: String): Long = prefs.getLong("anchor_$type", 0L)
    fun setAnchor(type: String, value: Long) { prefs.edit().putLong("anchor_$type", value).apply() }
    fun page(type: String): String? = prefs.getString("page_$type", null)
    fun setPage(type: String, value: String?) { prefs.edit().putString("page_$type", value).apply() }


    /** Persisted aggregate cache; keeps unchanged daily totals from being resent every sync. */
    var lastAggregateCheck: Long
        get() = prefs.getLong("aggregate_last_check", 0L)
        set(value) { prefs.edit().putLong("aggregate_last_check", value).apply() }

    fun payloadDigest(kind: String, uid: String): String? =
        prefs.getString("payload_digest_${kind}_$uid", null)

    fun setPayloadDigest(kind: String, uid: String, digest: String) {
        prefs.edit().putString("payload_digest_${kind}_$uid", digest).apply()
    }

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (store.getKey(alias, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder(alias,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256).build())
        }.generateKey()
    }

    fun setToken(value: String) {
        require(value.isNotBlank())
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply { init(Cipher.ENCRYPT_MODE, key()) }
        val encrypted = cipher.doFinal(value.trim().toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString("token_iv", Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
            .putString("token_ct", Base64.encodeToString(encrypted, Base64.NO_WRAP))
            .apply()
    }

    fun token(): String? {
        val iv = prefs.getString("token_iv", null) ?: return null
        val ciphertext = prefs.getString("token_ct", null) ?: return null
        val cipher = Cipher.getInstance("AES/GCM/NoPadding").apply {
            init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)))
        }
        return String(cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)), Charsets.UTF_8)
    }
}
