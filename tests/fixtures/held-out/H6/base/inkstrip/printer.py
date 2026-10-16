import os

FALLBACK_DEVICE = "/dev/cu.usbserial-inkstrip"
LABEL_PITCH_MM = 28


class PrinterUnavailable(Exception):
    pass


class LabelPrinter:
    def __init__(self, device):
        self.device = device

    def transmit(self, instruction):
        with open(self.device, "r+b", buffering=0) as stream:
            stream.write(instruction.encode("ascii") + b"\n")
            return stream.readline().decode("ascii").strip()


def open_printer():
    port = os.environ.get("INKSTRIP_PORT", FALLBACK_DEVICE)
    if not os.path.exists(port):
        raise PrinterUnavailable("no label printer at {}".format(port))
    return LabelPrinter(port)


def feed(link):
    return link.transmit("FEED {}".format(LABEL_PITCH_MM))


def print_label(link, lines):
    for line in lines:
        link.transmit("TEXT {}".format(line))
    return link.transmit("PRINT")
