import re

def make_code(name):
	"""Build a record code from a display name, e.g. "Profit & Loss" -> "PROFIT_LOSS"."""
	return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")
