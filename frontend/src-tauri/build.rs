use chrono::prelude::*;

fn main() {
    // Let Tauri set up its stuff
    tauri_build::build();

    // Get current Git commit hash
    let git_hash = std::process::Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .expect("Failed to get Git commit hash");
    let git_hash = String::from_utf8(git_hash.stdout).expect("Invalid UTF-8 in Git hash");

    // Get current Git branch
    let git_branch = std::process::Command::new("git")
        .args(["rev-parse", "--abbrev-ref", "HEAD"])
        .output()
        .expect("Failed to get Git branch");
    let git_branch = String::from_utf8(git_branch.stdout).expect("Invalid UTF-8 in Git branch");

    // Get current build time in RFC3339 format
    let build_time = Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();

    // Determine Android package name based on DEV_MODE env var
    // This matches the logic in scripts/patch-android-gen-files.py
    let dev_mode = std::env::var("DEV_MODE").unwrap_or_else(|_| "false".to_string());
    let android_package_name = if dev_mode == "true" {
        "cz.hillviedev"
    } else {
        "cz.hillview"
    };

    // Emit values as compile-time env vars
    println!("cargo:rustc-env=GIT_HASH=\"{}\"", git_hash.trim());
    println!("cargo:rustc-env=GIT_BRANCH=\"{}\"", git_branch.trim());
    println!("cargo:rustc-env=BUILD_TIME=\"{}\"", build_time);
    println!("cargo:rustc-env=ANDROID_PACKAGE_NAME={}", android_package_name);

    // Rerun if DEV_MODE changes
    println!("cargo:rerun-if-env-changed=DEV_MODE");
}
