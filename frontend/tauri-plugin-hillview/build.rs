const COMMANDS: &[&str] = &["start_sensor", "stop_sensor", "update_sensor_location", "registerListener"];
fn main() {
  tauri_plugin::Builder::new(COMMANDS)
    .android_path("android")
    .ios_path("ios")
    .build();
}
