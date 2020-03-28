import asyncio
import logging
import traceback

import slack

from .exceptions import MessageHandleAborted


class SlackBot:
    def __init__(self,
                 token,
                 name,
                 triggers=None,
                 group='__all__',
                 channels='__all__',
                 report_channels=None,
                 logger=None,
                 ):
        self.token = token
        self.name = name
        self.triggers = triggers or ['{} '.format(self.name)]
        self.client = slack.WebClient(token=token, run_async=True)
        self.commands = {}
        self.commands_meta = []
        self.group = group
        self.channels = channels
        self.report_channels = report_channels or []
        self.logger = logger or logging.getLogger(name)
        self._pre_command_hook = []
        self._pre_message_hook = []
        self._post_message_hook = []
        self._post_command_hook = []
        self._bot_user_id = None

    async def get_bot_user_id(self):
        if not self._bot_user_id:
            self._bot_user_id = (await self.client.auth_test())['user_id']
        return self._bot_user_id

    # noinspection PyBroadException
    async def message_handler(self, payload):
        try:
            if self._pre_message_hook:
                pre_message_futures = [f(**payload) for f in self._pre_message_hook]
                await asyncio.gather(*pre_message_futures)

            data = payload['event']
            text = data.get('text', '')
            for trigger in self.triggers:
                if text.startswith(trigger):
                    prefix = trigger
                    break
            else:
                return
            text = text[len(prefix):]
            args = text.split()
            channel_id = data.get('channel')
            user_id = data.get('user')
            if not args or args[0] not in self.commands:
                return
            cmd = self.commands[args[0]]

            if cmd.group != '__all__' and user_id not in cmd.group:
                return
            if cmd.channels != '__all__' and channel_id not in cmd.channels:
                return

            payload['bot'] = self
            payload['cmd'] = cmd

            if self._pre_command_hook:
                pre_command_futures = [f(*args, **payload) for f in self._pre_command_hook]
                await asyncio.gather(*pre_command_futures)

            res = await cmd(*args, **payload)

            if self._post_command_hook:
                payload['result'] = res
                post_command_futures = [f(*args, **payload) for f in self._post_command_hook]
                await asyncio.gather(*post_command_futures)

            return res

        except MessageHandleAborted as e:
            self.logger.info('Message handling aborted with message: {}'.format(e))
        except Exception:
            error_log = traceback.format_exc()
            self.logger.error(error_log)
            if self.report_channels:
                futures = [
                    self.client.chat_postMessage(
                        channel=report_channel,
                        text='```{}```'.format(error_log),
                        as_user=True
                    ) for report_channel in self.report_channels
                ]
                await asyncio.gather(*futures, return_exceptions=True)

    def register_pre_message_hook(self, f):
        self._pre_message_hook.append(f)

    def pre_message_hook(self, f):
        self.register_pre_message_hook(f)
        return f

    def register_post_message_hook(self, f):
        self._post_message_hook.append(f)

    def post_message_hook(self, f):
        self.register_post_message_hook(f)
        return f

    def register_pre_command_hook(self, f):
        self._pre_command_hook.append(f)

    def pre_command_hook(self, f):
        self.register_pre_command_hook(f)
        return f

    def register_post_command_hook(self, f):
        self._post_command_hook.append(f)

    def post_command_hook(self, f):
        self.register_post_command_hook(f)
        return f

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
            self.commands[alias] = cmd
        self.commands_meta.append(cmd)

    def get_commands(self):
        return list(set(self.commands.values()))

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
