import asyncio
import logging
import traceback

import discord
import slack

from .exceptions import CommandNotFound, MessageHandleAborted


class ChatBot:
    PRE_MESSAGE_SIGNAL = 'pre_message'
    PRE_COMMAND_SIGNAL = 'pre_command'
    INVALID_COMMAND_SIGNAL = 'invalid_command'
    POST_COMMAND_SIGNAL = 'post_command'

    REASON_NOT_FOUND = 'not_found'
    REASON_NO_PERMISSION = 'no_permission'
    REASON_INVALID_ARGUMENT = 'invalid_argument'

    PLATFORM = None

    def __init__(self,
                 name=None,
                 triggers=None,
                 group='__all__',
                 channels='__all__',
                 report_channels=None,
                 logger=None,
                 ):
        self.name = name
        self.triggers = triggers or ['{} '.format(self.name)]
        self._commands = {}
        self._commands_meta = []
        self.group = group
        self.channels = channels
        self.report_channels = report_channels or []
        self.logger = logger or logging.getLogger(name)
        self._signal_handler = {}

    @classmethod
    def clone(cls, bot, **kwargs):
        kwargs.setdefault('name', bot.name)
        kwargs.setdefault('triggers', bot.triggers)
        kwargs.setdefault('group', bot.group)
        kwargs.setdefault('channels', bot.channels)
        kwargs.setdefault('report_channels', bot.report_channels)
        cloned_bot = cls(**kwargs)
        for cmd in bot.commands:
            cloned_bot.add_command(
                cmd,
                aliases=cmd.aliases,
                group=cmd.group,
                override_group=True,
                channels=cmd.channels,
                override_channels=True,
            )
        for signal in bot.signal_handlers:
            for signal_handler in bot.signal_handlers[signal]:
                cloned_bot.register_signal_handler(signal, signal_handler)
        return cloned_bot

    @property
    def platform(self):
        return self.PLATFORM

    # noinspection PyBroadException
    async def handle_message(self, channel, user, text, **extra):
        try:
            payload = {
                'channel': channel,
                'user': user,
                'text': text,
                'bot': self,
                'extra': extra,
            }

            await self.send_signal(self.PRE_MESSAGE_SIGNAL, payload)

            for trigger in self.triggers:
                if text.startswith(trigger):
                    prefix = trigger
                    break
            else:
                return

            text = text[len(prefix):]
            args = text.split()
            if not args or not self.has_command(args[0]):
                print(channel)
                print('hi')
                payload['reason'] = self.REASON_NOT_FOUND
                await self.send_signal(self.INVALID_COMMAND_SIGNAL, payload)
                return
            cmd = self._commands[args[0]]

            if cmd.group != '__all__' and user not in cmd.group:
                payload['reason'] = self.REASON_NO_PERMISSION
                await self.send_signal(self.INVALID_COMMAND_SIGNAL, payload)
                return
            if cmd.channels != '__all__' and channel not in cmd.channels:
                payload['reason'] = self.REASON_NO_PERMISSION
                await self.send_signal(self.INVALID_COMMAND_SIGNAL, payload)
                return

            payload['cmd'] = cmd
            await self.send_signal(self.PRE_COMMAND_SIGNAL, payload)

            try:
                res = await cmd(*args, **payload)
            except TypeError:
                payload['reason'] = self.REASON_INVALID_ARGUMENT
                await self.send_signal(self.INVALID_COMMAND_SIGNAL, payload)
                return
            payload['result'] = res
            await self.send_signal(self.POST_COMMAND_SIGNAL, payload)

            return res

        except MessageHandleAborted as e:
            self.logger.info('Message handling aborted with message: {}'.format(e))
        except Exception:
            error_log = traceback.format_exc()
            self.logger.error(error_log)
            if self.report_channels:
                futures = [
                    self.send_message(
                        channel=report_channel,
                        text='```{}```'.format(error_log)
                    ) for report_channel in self.report_channels
                ]
                await asyncio.gather(*futures, return_exceptions=True)

    async def is_bot(self, user, **kwargs):
        return False

    @staticmethod
    def mention(user):
        return user

    async def send_message(self, channel, text, **kwargs):
        raise NotImplementedError

    @property
    def commands(self):
        return self._commands_meta

    def has_command(self, alias):
        return alias in self._commands

    def get_command(self, alias):
        if not self.has_command(alias):
            raise CommandNotFound(alias)
        return self._commands[alias]

    def add_command(self, cmd, aliases=None,
                    group='__all__', override_group=False,
                    channels='__all__', override_channels=False):
        aliases = aliases or [cmd.__name__]
        if not override_group and self.group != '__all__':
            if group == '__all__':
                group = self.group
            else:
                group = [username for username in group if username in self.group]
        if not override_channels and self.channels != '__all__':
            if channels == '__all__':
                channels = self.channels
            else:
                channels = [channel for channel in self.channels if channel in self.channels]
        channels = channels or self.channels
        cmd.aliases = aliases
        cmd.group = group
        cmd.channels = channels
        for alias in aliases:
            self._commands[alias] = cmd
        self._commands_meta.append(cmd)

    def command(self, aliases=None,
                group='__all__', override_group=False,
                channels='__all__', override_channels=False):
        def decorator(f):
            self.add_command(
                f,
                aliases=aliases,
                group=group,
                override_group=override_group,
                channels=channels,
                override_channels=override_channels,
            )
            return f
        return decorator

    @property
    def signal_handlers(self):
        return self._signal_handler

    async def send_signal(self, signal, payload):
        if signal in self._signal_handler:
            signal_futures = [f(**payload) for f in self._signal_handler[signal]]
            await asyncio.gather(*signal_futures)

    def register_signal_handler(self, signal, f):
        self._signal_handler.setdefault(signal, []).append(f)

    def on_signal(self, signal):
        def decorator(f):
            self.register_signal_handler(signal, f)
            return f
        return decorator


class SlackBot(ChatBot):
    PLATFORM = 'Slack'

    def __init__(self, token, *args, **kwargs):
        super(SlackBot, self).__init__(*args, **kwargs)
        self._token = token
        self.client = slack.WebClient(token=token, run_async=True)
        self._bot_user_id = None

    async def message_handler(self, payload):
        try:
            data = payload['event']
            text = data['text']
            channel = data['channel']
            user = data['user']
            return await self.handle_message(channel, user, text, **payload)
        except (TypeError, KeyError):
            pass

    async def get_bot_user_id(self):
        if not self._bot_user_id:
            self._bot_user_id = (await self.client.auth_test())['user_id']
        return self._bot_user_id

    async def is_bot(self, user, **_):
        user_info = (await self.client.users_info(user=user))['user']
        return user_info['is_bot']

    @staticmethod
    def mention(user):
        return '<@{}>'.format(user)

    async def send_message(self, channel, text, **_):
        await self.client.chat_postMessage(channel=channel, text=text, as_user=True)


class DiscordBot(ChatBot):
    PLATFORM = 'Discord'

    def __init__(self, token, *args, **kwargs):
        super(DiscordBot, self).__init__(*args, **kwargs)
        self._token = token
        self.client = discord.Client()
        self.client.event(self.on_message)

    async def on_message(self, message):
        user = message.author
        text = message.content
        channel = message.channel
        return await self.handle_message(channel, user, text)

    async def send_message(self, channel, text, **_):
        return await channel.send(text)

    async def start(self):
        try:
            await self.client.start(self._token)
        except asyncio.CancelledError:
            await self.client.logout()
