const COMMANDS: &[&str] = &["ping", "start_sensor", "stop_sensor", "update_sensor_location"];

fn main() {
  tauri_plugin::Builder::new(COMMANDS)
    .android_path("android")
    .ios_path("ios")
    .build();
}
