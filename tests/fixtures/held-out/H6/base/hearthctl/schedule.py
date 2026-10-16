def parse(entry):
    time_text, celsius_text = entry.split("=", 1)
    hours, minutes = (int(part) for part in time_text.split(":", 1))
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError("{} is not a time of day".format(time_text))
    return "{:02d}:{:02d}".format(hours, minutes), float(celsius_text)


def programme(entries):
    return sorted(parse(entry) for entry in entries)
