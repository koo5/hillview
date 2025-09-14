import fire
import os
import logging

def process_directory(input_dir, output_dir, force_copy_all_images=False):
	os.makedirs(output_dir, exist_ok=True)
	logging.info("Starting anonymization...")

	for filename in sorted(os.listdir(input_dir)):
		anonymize_image(input_dir, output_dir, filename, force_copy_all_images)
	logging.info("Anonymization complete.")


if __name__ == "__main__":
	fire.Fire(process_directory)
