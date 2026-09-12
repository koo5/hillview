#!/usr/bin/env python3

def subject_height_table(
	focal_length_mm=200,
	sensor_height_mm=36,
	max_distance_m=200,
	step_m=10
):
	# Convert mm → meters
	f = focal_length_mm / 1000
	S = sensor_height_mm / 1000

	print(f"Focal length: {focal_length_mm} mm")
	print(f"Sensor height: {sensor_height_mm} mm")
	print()
	print("Distance (m) | Subject height filling frame (m)")
	print("-" * 45)

	for D in range(step_m, max_distance_m + 1, step_m):
		H = (D * S) / f
		print(f"{D:12} | {H:30.2f}")


if __name__ == "__main__":
	subject_height_table()

