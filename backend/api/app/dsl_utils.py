import yaml

def y(text):
	return yaml.safe_load(text.replace("\t", "  "))
