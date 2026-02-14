
# Define target classes for full anonymization (people + vehicles)
TARGET_CLASSES = {
	0: "person",
	1: "bicycle",
	2: "car",
	3: "motorcycle",
	5: "bus",
	7: "truck"
}

BLUR_SIZES = {
	"person": 151,
	"bicycle": 123,
	"car": 101,
	"motorcycle": 91,
	"bus": 55,
	"truck": 55
}
