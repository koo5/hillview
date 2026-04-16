plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
    id("kotlin-kapt")
    id("org.jetbrains.kotlin.plugin.serialization") version "2.0.20"
}

android {
    namespace = "cz.hillview.plugin"
    compileSdk = 34

    defaultConfig {
        minSdk = 21

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        consumerProguardFiles("consumer-rules.pro")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    testOptions {
        unitTests {
            // Android's android.jar stub throws "Method not mocked" for every
            // framework call (e.g., android.util.Log.*) during JVM unit tests.
            // Returning default values instead lets pure-logic tests run without
            // Robolectric. Pure JVM classes on the test classpath (the real
            // org.json.JSONObject pulled via testImplementation) are unaffected.
            isReturnDefaultValues = true
        }
    }
}

kapt {
    arguments {
        arg("room.schemaLocation", "$projectDir/schemas")
    }
    correctErrorTypes = true
}

configurations.all {
    resolutionStrategy {
        force("org.jetbrains.kotlin:kotlin-stdlib:2.0.20")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk8:2.0.20")
        force("org.jetbrains.kotlin:kotlin-stdlib-jdk7:2.0.20")
        force("org.jetbrains.kotlin:kotlin-reflect:2.0.20")
    }
}

dependencies {

    implementation("androidx.core:core-ktx:1.9.0")
    implementation("androidx.appcompat:appcompat:1.6.0")
    implementation("com.google.android.material:material:1.7.0")

    // Lifecycle components for ProcessLifecycleOwner
    implementation("androidx.lifecycle:lifecycle-process:2.6.2")

    // Google Play Services for Fused Location Provider
    implementation("com.google.android.gms:play-services-location:21.3.0")

    // Room database
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    implementation("androidx.room:room-common:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")

    // WorkManager for background tasks
    implementation("androidx.work:work-runtime-ktx:2.8.1")

    // HTTP client for uploads
    implementation("com.squareup.okhttp3:okhttp:4.11.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.6.4")

    // Kotlinx Serialization for JSON handling
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.5.1")

    // ExifInterface for EXIF data extraction
    implementation("androidx.exifinterface:exifinterface:1.3.6")

    // UnifiedPush for push notifications
    implementation("org.unifiedpush.android:connector:3.1.2")

    // Firebase Cloud Messaging for direct FCM support
    implementation(platform("com.google.firebase:firebase-bom:32.7.0"))
    implementation("com.google.firebase:firebase-messaging-ktx")

    testImplementation("junit:junit:4.13.2")
    // Mockito 5.x runs the inline mock-maker by default (so Kotlin's default-final
    // classes are mockable) and handles JDK 17+ self-attach properly. Source/target
    // Java 1.8 above is for our own bytecode; the test JVM runs newer.
    testImplementation("org.mockito:mockito-core:5.11.0")
    // Android's android.jar stubs org.json.JSONObject with "Method not mocked"
    // throwers for JVM unit tests. Pulling in the real org.json library puts a
    // working JSONObject on the test classpath so JSObject (which extends it)
    // can be instantiated without Robolectric.
    testImplementation("org.json:json:20240303")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    implementation(project(":tauri-android"))

    implementation("org.unifiedpush.android:connector:3.1.2")
}

//kotlin {
//    compilerOptions {
//        freeCompilerArgs.add("-Xcontext-parameters")
//    }
//}
