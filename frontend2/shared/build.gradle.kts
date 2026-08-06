import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.kotlinMultiplatform)
    alias(libs.plugins.androidMultiplatformLibrary)
    alias(libs.plugins.composeMultiplatform)
    alias(libs.plugins.composeCompiler)
    alias(libs.plugins.kotlinxSerialization)
    // Room annotation processing for the shared-kt PhotoDatabase (android target).
    alias(libs.plugins.ksp)
}

kotlin {
    // iOS targets (iosArm64/iosSimulatorArm64 + an iosApp Xcode project) can only
    // be added and built on macOS — declare them here when iOS work starts.
    androidLibrary {
        namespace = "cz.hillview.shared"
        compileSdk = libs.versions.android.compileSdk.get().toInt()
        minSdk = libs.versions.android.minSdk.get().toInt()

        compilerOptions {
            jvmTarget = JvmTarget.JVM_11
        }
        androidResources {
            enable = true
        }
    }

    jvm()

    sourceSets {
        // Crypto + file IO shared by the two JVM-family targets (java.security
        // ECDSA, MessageDigest, java.io) without duplicating into each.
        val jvmShared by creating {
            dependsOn(commonMain.get())
        }
        jvmMain.get().dependsOn(jvmShared)
        androidMain.get().dependsOn(jvmShared)

        // Kotlin shared verbatim with the Tauri app (see /shared-kt/README.md).
        // Only src/ — shared-kt/src-pending/ holds shared-in-principle files
        // whose dependency closure isn't satisfied here yet (Tauri build only);
        // graduation to src/ is a pure git mv. The upload-logic family
        // (PhotoUploadLogic/Manager/Workers, PhotoDatabase, AuthenticationManager)
        // fully graduated 2026-08-05 — src-pending is empty until the next
        // sharing wave (sensors/tracking).
        androidMain.get().kotlin.srcDir(rootDir.resolve("../shared-kt/src"))

        androidMain.dependencies {
            implementation(libs.androidx.activity.compose)
            implementation(libs.androidx.camera.camera2)
            implementation(libs.androidx.camera.core)
            implementation(libs.androidx.camera.effects)
            implementation(libs.androidx.camera.lifecycle)
            implementation(libs.androidx.camera.video)
            implementation(libs.androidx.camera.view)
            implementation(libs.androidx.core.ktx)
            implementation(libs.androidx.exifinterface)
            implementation(libs.androidx.lifecycle.process)
            implementation(libs.androidx.room.runtime)
            implementation(libs.androidx.work.runtime)
            implementation(libs.koin.android)
            implementation(libs.kotlinx.coroutines.android)
            implementation(libs.ktor.client.okhttp)
            implementation(libs.okhttp)
            implementation(libs.osmdroid)
            implementation(libs.play.services.location)
            implementation(libs.zxing.core)
        }
        commonMain.dependencies {
            implementation(libs.compose.runtime)
            implementation(libs.compose.foundation)
            implementation(libs.compose.material3)
            implementation(libs.compose.ui)
            implementation(libs.compose.components.resources)
            implementation(libs.compose.uiToolingPreview)

            implementation(libs.androidx.lifecycle.viewmodelCompose)
            implementation(libs.androidx.lifecycle.runtimeCompose)

            implementation(libs.navigation3.runtime)
            implementation(libs.navigation3.ui)

            implementation(libs.koin.core)
            implementation(libs.koin.compose)
            implementation(libs.koin.compose.viewmodel)

            implementation(libs.ktor.client.core)
            implementation(libs.ktor.client.content.negotiation)
            implementation(libs.ktor.serialization.kotlinx.json)
            implementation(libs.kotlinx.serialization.json)
        }
        commonTest.dependencies {
            implementation(libs.kotlin.test)
            implementation(libs.kotlinx.coroutines.test)
            implementation(libs.ktor.client.mock)
        }
        jvmMain.dependencies {
            implementation(libs.ktor.client.okhttp)
        }
        jvmTest.dependencies {
            implementation(libs.compose.uiTest)
            implementation(compose.desktop.currentOs)
            implementation(libs.junit)
        }
    }
}

dependencies {
    androidRuntimeClasspath(libs.compose.uiTooling)
    // Room codegen for the android target only (the KMP-target-qualified KSP
    // configuration; there is no Room usage in jvm/common).
    "kspAndroid"(libs.androidx.room.compiler)
}
