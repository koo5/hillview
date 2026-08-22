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

        // Host tests: commonTest also runs on the Android target's JVM
        // (task :shared:testAndroidHostTest) — same rules, one more
        // compiler's opinion, and it silences the per-build Gradle warning
        // that the source set exists but is unwired.
        withHostTest {}

        // Instrumented tests: the contracts that only exist on a device —
        // EXIF written by Android's ExifInterface, the storage targets, and
        // what the platform reports about them.
        withDeviceTestBuilder {
            sourceSetTreeName = "test"
        }.configure {
            instrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
            // Native auth: Credential Manager + Sign in with Google
            // (CredentialGateway.android.kt).
            implementation(libs.androidx.credentials)
            implementation(libs.androidx.credentials.play)
            implementation(libs.googleid)
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

            // Image loading for the viewer pane's slots — multiplatform, and
            // sharing ktor with everything else here.
            implementation(libs.coil.compose)
            implementation(libs.coil.network.ktor)

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
        getByName("androidDeviceTest").dependencies {
            implementation(libs.androidx.test.runner)
            implementation(libs.androidx.test.junit)
        }
        jvmTest.dependencies {
            implementation(libs.compose.uiTest)
            implementation(compose.desktop.currentOs)
            implementation(libs.junit)
        }
    }
}

// Room schema export. shared-kt's entities are compiled by BOTH apps, with
// different Room versions (2.8.4 here, 2.6.1 in the Tauri plugin's kapt), so
// each build gets its OWN directory — one shared directory would have the two
// overwriting each other's JSON on every build. They agree on the identityHash
// (the value Room checks at runtime); 2.6.1 just also writes the defaults that
// 2.8.4 omits.
//
// KNOWN HOLE: a processor argument is an opaque string to Gradle, so the schema
// directory is NOT a declared task output. It takes no part in up-to-date
// checks or the build cache: delete the JSON and nothing notices it is gone,
// and a build that finds KSP up-to-date leaves whatever is on disk. Treat the
// files as "written when KSP last ran", not as a build guarantee — if an entity
// change ever appears to produce no schema diff, force KSP (touch the entity,
// or clean) before believing it.
//
// The fix, when it is worth it: the `androidx.room` Gradle plugin
// (`room { schemaDirectory(...) }`), which registers the directory properly.
// Not adopted yet — it needs a version-catalog entry and, the real unknown,
// compatibility with AGP 9.3.1 + the KMP androidLibrary plugin, both new.
ksp {
    arg(
        "room.schemaLocation",
        rootDir.resolve("../shared-kt/schemas/frontend2").absolutePath,
    )
}

dependencies {
    androidRuntimeClasspath(libs.compose.uiTooling)
    // Room codegen for the android target only (the KMP-target-qualified KSP
    // configuration; there is no Room usage in jvm/common).
    "kspAndroid"(libs.androidx.room.compiler)
}

// OneStateArchitectureTest reads the SOURCE TREE, not the classpath: it
// enforces that nothing outside the geo boundary talks to the hardware (see
// docs/one-state.md). Gradle cannot see that dependency, so a violation added
// under androidMain — which is not on the jvm target's classpath — left the
// task up to date and the check silently unrun. Declaring src/ as an input
// makes any source change re-run it, which is the whole point of a fitness
// test: it has to fire when the code moves, not when the test does.
tasks.named<Test>("jvmTest") {
    inputs.dir(layout.projectDirectory.dir("src"))
        .withPathSensitivity(PathSensitivity.RELATIVE)
        .withPropertyName("sourceTreeForArchitectureTest")
}
