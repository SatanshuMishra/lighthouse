class FakeLink:
    def __init__(self, reply="OK"):
        self.reply = reply
        self.sent = []

    def send(self, command):
        self.sent = self.sent + [command]
        return self.reply
