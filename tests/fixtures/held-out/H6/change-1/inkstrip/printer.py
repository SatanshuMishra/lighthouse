import os

DEFAULT_PORT = "/dev/cu.usbserial-inkstrip"
LABEL_PITCH_MM = 28


class PrinterUnavailable(Exception):
    pass


class SerialLink:
    def __init__(self, port):
        self.port = port

    def send(self, command):
        with open(self.port, "r+b", buffering=0) as line:
            line.write((command + "\n").encode("ascii"))
            return line.readline().decode("ascii").strip()


def connect():
    port = os.environ.get("INKSTRIP_PORT", DEFAULT_PORT)
    if not os.path.exists(port):
        raise PrinterUnavailable("no label printer at {}".format(port))
    return SerialLink(port)


def feed(link):
    return link.send("FEED {}".format(LABEL_PITCH_MM))


def print_label(link, lines):
    for line in lines:
        link.send("TEXT {}".format(line))
    printed = link.send("PRINT")
    feed(link)
    return printed
