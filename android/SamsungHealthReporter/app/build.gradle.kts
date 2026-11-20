plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    // The Samsung Health Data SDK guide requires parcelize in the app that ships the SDK.
    alias(libs.plugins.kotlin.parcelize)
}

android {
    namespace = "com.kvs.samsunghealthreporter.example"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.kvs.samsunghealthreporter.example"
        minSdk = 29
        targetSdk = 36
        versionCode = 33
        versionName = "0.3.3"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.work:work-runtime-ktx:2.10.5")
    implementation(project(":library"))
    // The app ships the Samsung Health Data SDK; the library only compiles against it.
    val samsungHealthDataAar = fileTree("../library/libs") { include("samsung-health-data-api*.aar") }
    // Explicit opt-in for library tests only. Never silently substitute a stub in the phone app.
    val useStub = providers.gradleProperty("samsungHealthDataStub")
        .map { it.equals("true", ignoreCase = true) }.getOrElse(false)
    implementation(if (useStub) project(":samsung-health-data-stub") else samsungHealthDataAar)
    implementation(libs.gson)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)
    debugImplementation(libs.compose.ui.tooling)
}

// Guard the installable Android application before its compile/package pipeline runs.
// The reusable library can still be unit-tested explicitly with -PsamsungHealthDataStub=true.
// Do not turn this into an unconditional configuration-time failure: that would block
// the independent library tests when Samsung's proprietary AAR is absent.
tasks.configureEach {
    if (name == "preBuild" || (name.startsWith("pre") && name.endsWith("Build"))) {
        doFirst {
            val stubRequested = providers.gradleProperty("samsungHealthDataStub")
                .map { it.equals("true", ignoreCase = true) }.getOrElse(false)
            if (stubRequested) {
                throw GradleException(
                    "Samsung Health Bridge APK builds cannot use the SDK stub. " +
                    "Remove -PsamsungHealthDataStub and supply Samsung's genuine AAR locally."
                )
            }
            val sdkAars = fileTree("../library/libs") {
                include("samsung-health-data-api*.aar")
            }.files
            if (sdkAars.size != 1) {
                throw GradleException(
                    "Exactly one authorized Samsung Health Data SDK AAR must be provided " +
                    "locally in library/libs/ for an app build; found ${sdkAars.size}. " +
                    "Obtain the SDK directly from Samsung. NEVER commit the AAR."
                )
            }
        }
    }
}
