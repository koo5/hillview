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
    debugImplementation(libs.compose.uiTestManifest)
}

android {
    namespace = "cz.hillview"
    compileSdk = libs.versions.android.compileSdk.get().toInt()

    // AGP 9 ships this off by default; needed for the per-build-type app_name.
    buildFeatures {
        resValues = true
    }

    defaultConfig {
        applicationId = "cz.hillview"
        minSdk = libs.versions.android.minSdk.get().toInt()
        targetSdk = libs.versions.android.targetSdk.get().toInt()
        versionCode = 1
        versionName = "0.1.0"
        resValue("string", "app_name", "Hillview")
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
