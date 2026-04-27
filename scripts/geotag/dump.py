#! /usr/bin/env python3

import os, sys, subprocess, time, json


# walk all the files in current directory and subdirectories recursively, sorted by naturalsort, invoking dump()
def main():
	for root, dirs, files in os.walk('.'):
		for file in files:
			for ext in ['.webp']:
				if str(file).lower().endswith(ext):
					dump(os.path.join(root, file))


def dump(file):
	print('Dumping ' + file)
	cmd = ['exiftool', '-json', file]
	result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if result.returncode != 0:
		print('Error dumping ' + file + ': ' + result.stderr.decode('utf-8'))
		return
	data = json.loads(result.stdout.decode('utf-8'))
	if len(data) == 0:
		print('No data found for ' + file)
		return
	user_comment_string = data[0].get('UserComment', None)
	if user_comment_string:
		user_comment = json.loads(user_comment_string)
		print(json.dumps(user_comment, indent=4))



if __name__ == '__main__':
	main()
