const COMMANDS: &[&str] = &["start_sensor", "stop_sensor", "start_precise_location_listener", "stop_precise_location_listener", "register_listener"];
fn main() {
  tauri_plugin::Builder::new(COMMANDS)
    .android_path("android")
    .ios_path("ios")
    .build();
}
