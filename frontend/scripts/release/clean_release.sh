#!/bin/fish

rm -rf src-tauri/gen

JAVA_HOME=/snap/android-studio/current/jbr/  CMAKE_MAKE_PROGRAM=/bin/make ANDROID_NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/   NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/  ANDROID_HOME=/home/koom/Android/Sdk/ bun run tauri android init
JAVA_HOME=/snap/android-studio/current/jbr/  CMAKE_MAKE_PROGRAM=/bin/make ANDROID_NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/   NDK_HOME=/home/koom/Android/Sdk/ndk/29.0.13113456/  ANDROID_HOME=/home/koom/Android/Sdk/ bun run tauri android build


