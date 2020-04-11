from joonbot.core import ChatBot


class MockBot(ChatBot):
    def __init__(self, *args, **kwargs):
        super(MockBot, self).__init__(*args, **kwargs)
        self.message_history = {}

    async def send_message(self, channel, text, **_):
        self.message_history.setdefault(channel, []).append(text)

    def last_message(self, channel):
        return self.message_history[channel][-1] if channel in self.message_history else None
