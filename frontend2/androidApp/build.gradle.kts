import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// AGP 9 has built-in Kotlin support — org.jetbrains.kotlin.android must NOT be
// applied here anymore, only the Compose compiler plugin.
plugins {
    alias(libs.plugins.androidApplication)
    alias(libs.plugins.composeCompiler)
}

dependencies {
    implementation(projects.shared)
    implementation(libs.androidx.activity.compose)
    implementation(libs.compose.foundation)
    implementation(libs.compose.uiToolingPreview)
    implementation(libs.koin.android)
    implementation(libs.koin.core)

    // App-level instrumented tests: the Appium behaviour ports drive the
    // real MainActivity through Compose semantics.
    androidTestImplementation(libs.compose.uiTestJunit4)
    androidTestImplementation(libs.androidx.test.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.rules)
    // The behaviour ports read the shared-kt Room DB directly (the rows the
    // Tauri suites reach through cmd.get_device_photos); shared's Room dep
    // is implementation-scoped, so the supertype needs naming here.
    androidTestImplementation(libs.androidx.room.runtime)
    // MockGps drives the fused provider's official mock mode — the
    // LocationManager test provider alone leaks GMS's system-wide cache
    // across test boundaries.
    androidTestImplementation(libs.play.services.location)
    debugImplementation(libs.compose.uiTestManifest)
}

android {
    namespace = "cz.hillview"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    // AGP 9 ships this off by default; needed for the per-build-type app_name.
    buildFeatures {
        resValues = true
        buildConfig = true
    }

    defaultConfig {
        applicationId = "cz.hillview"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
        resValue("string", "app_name", "Hillview")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        // The photo folder under DCIM/. "Hillview2" in BOTH build types —
        // this app generation keeps its own folder, never mixing with the
        // Tauri app's DCIM/Hillview on the same device; the HILLVIEW_FOLDER
        // env var at build time overrides it.
        buildConfigField(
            "String",
            "HILLVIEW_FOLDER",
            "\"${System.getenv("HILLVIEW_FOLDER") ?: "Hillview2"}\"",
        )
        // Native Sign in with Google: the backend's GOOGLE_CLIENT_ID (the
        // WEB client id — it lands in the ID token's `aud`, which the
        // server verifies). Empty keeps the Google button hidden.
        buildConfigField(
            "String",
            "HILLVIEW_GOOGLE_CLIENT_ID",
            "\"${System.getenv("HILLVIEW_GOOGLE_CLIENT_ID") ?: ""}\"",
        )
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
    buildTypes {
        getByName("debug") {
            // Coexist with the installed production (Tauri) cz.hillview app.
            applicationIdSuffix = ".debug"
            resValue("string", "app_name", "Hillview Dev")
        }
        getByName("release") {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.JVM_11
    }
}
