import os

DEFAULT_PORT = "/dev/cu.usbmodem-hearth"


class DeviceUnavailable(Exception):
    pass


class SerialLink:
    def __init__(self, port):
        self.port = port

    def send(self, command):
        with open(self.port, "r+b", buffering=0) as line:
            line.write((command + "\n").encode("ascii"))
            return line.readline().decode("ascii").strip()


def connect():
    port = os.environ.get("HEARTH_PORT", DEFAULT_PORT)
    if not os.path.exists(port):
        raise DeviceUnavailable("no thermostat at {}".format(port))
    return SerialLink(port)
