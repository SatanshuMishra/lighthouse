class RecordingPrinter:
    def __init__(self, reply="OK"):
        self.reply = reply
        self.received = []

    def transmit(self, command):
        self.received = self.received + [command]
        return self.reply
