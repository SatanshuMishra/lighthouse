class FakeLink:
    def __init__(self, reply="OK"):
        self.reply = reply
        self.sent = []

    def send(self, command):
        self.sent.append(command)
        return self.reply
