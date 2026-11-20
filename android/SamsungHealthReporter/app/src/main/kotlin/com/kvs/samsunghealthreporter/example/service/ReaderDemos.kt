package com.kvs.samsunghealthreporter.example.service

import android.app.Activity
import com.kvs.samsunghealthreporter.SamsungHealthReporter
import com.kvs.samsunghealthreporter.example.demo.DemoRow
import com.kvs.samsunghealthreporter.example.demo.DemoSection
import com.kvs.samsunghealthreporter.model.SourceFilter
import com.kvs.samsunghealthreporter.model.TimeGroup
import com.kvs.samsunghealthreporter.model.TimeRange
import com.kvs.samsunghealthreporter.model.type.Aggregation
import com.kvs.samsunghealthreporter.model.type.HealthType
import com.kvs.samsunghealthreporter.model.type.TimeGroupUnit
import com.kvs.samsunghealthreporter.model.payload.BloodPressure
import com.kvs.samsunghealthreporter.model.payload.EnergyScore
import com.kvs.samsunghealthreporter.model.payload.Sleep
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import com.kvs.samsunghealthreporter.service.aggregate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/** Demos of **SamsungHealthReader**: every readable type, every aggregation, paging and the user profile. */
class ReaderDemos(
    private val reporter: () -> SamsungHealthReporter,
) : DemoPerformer {
    private val readRows =
        HealthType.entries.filter { it.isReadable }.associateBy { type ->
            DemoRow("reader.read.${type.identifier}", "Read ${type.identifier}, last 7 days", "reader.read")
        }
    private val aggregateRows =
        Aggregation.entries.associateBy { aggregation ->
            DemoRow(
                "reader.aggregate.${aggregation.name}",
                "${aggregation.name.lowercase()} per day, last 7 days",
                "reader.aggregate",
            )
        }
    // Focused, read-only proof tests for the HA Health Data Bridge project.
    private val watchBpProof = DemoRow(
        "reader.proof.watch_bp", "PROOF: Watch BP (30 days)", "reader.read(BLOOD_PRESSURE)",
    )
    private val energyProof = DemoRow(
        "reader.proof.energy", "PROOF: Energy Score (30 days)", "reader.read(ENERGY_SCORE)",
    )
    private val sleepScoreProof = DemoRow(
        "reader.proof.sleep_score", "PROOF: Sleep Score (30 days)", "reader.read(SLEEP)",
    )
    private val stepsHourly = DemoRow("reader.stepsHourly", "Steps per hour today", "reader.aggregate + TimeGroup")
    private val samsungHealthOnly =
        DemoRow("reader.source", "Heart rate measured by Samsung Health today", "reader.read + SourceFilter")
    private val paging = DemoRow("reader.page", "Heart rate, two pages of 5", "reader.readPage")
    private val userProfile = DemoRow("reader.userProfile", "User profile", "reader.userProfile")

    override val section =
        DemoSection(
            "Reader",
            listOf(watchBpProof, energyProof, sleepScoreProof, userProfile, paging, samsungHealthOnly, stepsHourly) +
                readRows.keys + aggregateRows.keys,
        )

    override fun perform(
        row: DemoRow,
        activity: Activity,
    ): Flow<String> =
        flow {
            val reader = reporter().reader
            val week = TimeRange.lastDays(7)
            val output =
                when (row) {
                    watchBpProof -> proofWatchBp(reader)
                    energyProof -> proofEnergy(reader)
                    sleepScoreProof -> proofSleepScore(reader)
                    userProfile -> reader.userProfile()?.json?.pretty() ?: "No profile"
                    paging -> {
                        val first = reader.readPage(HealthType.HEART_RATE, week, pageSize = 5)
                        val second =
                            first.nextPageToken?.let { reader.readPage(HealthType.HEART_RATE, week, 5, it) }
                        "Page 1 (${first.items.size}):\n${first.items.map { it.json }.prettyList()}\n\n" +
                            "Page 2 (${second?.items?.size ?: 0}):\n${second?.items.orEmpty().map {
                                it.json
                            }.prettyList()}"
                    }
                    samsungHealthOnly ->
                        reader
                            .read(
                                HealthType.HEART_RATE,
                                TimeRange.day(),
                                limit = 10,
                                source = SourceFilter.SamsungHealth,
                            ).map { it.json }
                            .prettyList()
                    stepsHourly ->
                        reader
                            .aggregate(Aggregation.STEPS_TOTAL, TimeRange.day(), TimeGroup(TimeGroupUnit.HOURLY))
                            .filter { it.value != null }
                            .map { it.json }
                            .prettyList()
                    in readRows -> reader.read(readRows.getValue(row), week, limit = 20).map { it.json }.prettyList()
                    in aggregateRows ->
                        reader
                            .aggregate(aggregateRows.getValue(row), week, TimeGroup(TimeGroupUnit.DAILY))
                            .map { it.json }
                            .prettyList()
                    else -> error("Unknown row ${row.id}")
                }
            emit(output)
        }

    // This phase does NOT send anything over the network or write to Samsung Health.
    private suspend fun proofWatchBp(
        reader: com.kvs.samsunghealthreporter.service.SamsungHealthReader,
    ): String {
        val all = reader.read(
            HealthType.BLOOD_PRESSURE, TimeRange.lastDays(30), limit = 100,
        ).filterIsInstance<BloodPressure>()
        val sourceCounts = all.groupingBy { it.dataSource?.appId ?: "<no source>" }.eachCount()
        val fromWatch = all.filter { it.dataSource?.appId == "com.samsung.android.shealthmonitor" }
        val header = "BP records fetched: ${all.size} (latest 100, 30 days)\n" +
            "Source app counts: $sourceCounts\n" +
            "Samsung Health Monitor (watch): ${fromWatch.size}\n"
        if (fromWatch.isEmpty()) {
            return header + "No watch-originated record in this window. Do not assume permission success means data is present."
        }
        return header + fromWatch.take(30).joinToString("\n\n") { r ->
            "Time=${localTime(r.startTimestamp)}; BP=${r.harmonized.systolic}/${r.harmonized.diastolic} mmHg; " +
                "pulse=${r.harmonized.pulseRate ?: "N/A"} bpm; mean=${r.harmonized.mean}; " +
                "app=${r.dataSource?.appId}; uid=${r.uid ?: "N/A"}"
        }
    }

    private suspend fun proofEnergy(
        reader: com.kvs.samsunghealthreporter.service.SamsungHealthReader,
    ): String {
        val values = reader.read(HealthType.ENERGY_SCORE, TimeRange.lastDays(30), limit = 50)
            .filterIsInstance<EnergyScore>()
        if (values.isEmpty()) return "No Energy Score records in last 30 days."
        return "Energy Score records: ${values.size}\n" + values.joinToString("\n\n") { r ->
            "Date=${localTime(r.startTimestamp)}; score=${r.harmonized.score}; " +
                "app=${r.dataSource?.appId ?: "N/A"}; uid=${r.uid ?: "N/A"}"
        }
    }

    private suspend fun proofSleepScore(
        reader: com.kvs.samsunghealthreporter.service.SamsungHealthReader,
    ): String {
        val values = reader.read(HealthType.SLEEP, TimeRange.lastDays(30), limit = 50)
            .filterIsInstance<Sleep>()
        if (values.isEmpty()) return "No Sleep records in last 30 days."
        return "Sleep sessions: ${values.size}\n" + values.joinToString("\n\n") { r ->
            "Start=${localTime(r.startTimestamp)}; end=${localTime(r.endTimestamp)}; " +
                "sleepScore=${r.harmonized.sleepScore ?: "N/A"}; " +
                "durationMinutes=${r.harmonized.durationMillis / 60000}; " +
                "app=${r.dataSource?.appId ?: "N/A"}; uid=${r.uid ?: "N/A"}"
        }
    }

    private fun localTime(epochMillis: Long): String =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss z")
            .format(Instant.ofEpochMilli(epochMillis).atZone(ZoneId.systemDefault()))
}
