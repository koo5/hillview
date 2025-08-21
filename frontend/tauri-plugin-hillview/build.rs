const COMMANDS: &[&str] = &["start_sensor", "stop_sensor", "update_sensor_location", "start_precise_location_listener", "stop_precise_location_listener", "registerListener"];
fn main() {
  tauri_plugin::Builder::new(COMMANDS)
    .android_path("android")
    .ios_path("ios")
    .build();
}
