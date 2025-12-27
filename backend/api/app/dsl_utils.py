import logging, yaml

def y(text):
	return yaml.safe_load(text.replace("\t", "  "))
