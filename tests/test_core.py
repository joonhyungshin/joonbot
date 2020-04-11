import asyncio
import unittest

from .models import MockBot


class TestCore(unittest.TestCase):
    def setUp(self):
        self.bot = MockBot(
            name='mockingbird',
            triggers=['bot '],
        )
        self.loop = asyncio.get_event_loop()

        @self.bot.command(aliases=['echo'])
        async def echo(*args, bot, channel, **_):
            await bot.send_message(channel=channel, text=' '.join(args[1:]))

    def test_echo(self):
        self.loop.run_until_complete(self.bot.handle_message(1, 1, 'bot echo hi'))
        self.assertEqual(self.bot.last_message(1), 'hi')
