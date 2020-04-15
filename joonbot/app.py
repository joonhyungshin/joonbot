import asyncio
import hashlib
import hmac
import os

import slack
from aiohttp import web

from .bot import joonbot
from .core import DiscordBot


class SlackEventHandler:
    def __init__(self, slack_signing_secret=None):
        self._slack_signing_secret = slack_signing_secret or os.getenv('SLACK_SIGNING_SECRET')
        if not self._slack_signing_secret:
            raise ValueError('Slack signing secret not found.')
        self._handler_dict = {}

    async def verify_request(self, request):
        if not request.can_read_body:
            return False
        timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
        slack_signature = request.headers.get('X-Slack-Signature', '')
        request_body = await request.text()
        sig_basestring = 'v0:{}:{}'.format(timestamp, request_body)
        signature = 'v0={}'.format(hmac.new(self._slack_signing_secret.encode(),
                                   sig_basestring.encode(),
                                   hashlib.sha256).hexdigest())
        return hmac.compare_digest(signature, slack_signature)

    async def handle_event(self, request):
        if not await self.verify_request(request):
            raise web.HTTPForbidden()
        data = await request.json()
        request_type = data['type']
        if request_type == 'url_verification':
            return web.Response(text=data['challenge'])
        elif request_type != 'event_callback':
            return web.Response(text='ok')
        event_type = data['event']['type']

        if event_type in self._handler_dict:
            for handler in self._handler_dict[event_type]:
                if asyncio.iscoroutinefunction(handler):
                    asyncio.ensure_future(handler(data))
                else:
                    handler(data)

        return web.Response(text='ok')

    def register_handler(self, event_type, func):
        self._handler_dict.setdefault(event_type, []).append(func)

    def on(self, event_type):
        register_handler = self.register_handler

        def decorator(func):
            register_handler(event_type, func)
            return func
        return decorator


slack_event_handler = SlackEventHandler()
slack_event_handler.register_handler('message', joonbot.message_handler)


# 슬랙 버그로 인해 커맨드 삭제
# @slack_event_handler.on('reaction_added')
async def no_touch(data):
    client = slack.WebClient(token=os.getenv('SLACK_API_TOKEN'), run_async=True)
    reaction = data['event']['reaction']
    user = data['event']['user']
    if reaction == 'blobfacepalm' and data['event']['item']['type'] == 'message':
        channel = data['event']['item']['channel']
        ts = data['event']['item']['ts']
        chats = (await client.conversations_history(
            channel=channel,
            latest=ts,
            limit=1,
            inclusive='true'
        ))['messages']
        if chats:
            chat = chats[0]
            if 'thread_ts' in chat:
                ts = chat['thread_ts']

        await client.chat_postMessage(
            channel=channel,
            thread_ts=ts,
            text='<@{}> 손으로 얼굴 만지지 마세요'.format(user)
        )


async def start_discord_bot(server_app):
    discord_joonbot = DiscordBot.clone(joonbot, token=os.getenv('DISCORD_BOT_TOKEN'))

    @discord_joonbot.client.event
    async def on_member_join(member):
        if member.bot:
            return

        guild = member.guild
        general = guild.system_channel

        if general is not None:
            introduce_channel = guild.get_channel(699213780340703264)
            destroyed_channel = guild.get_channel(698538436684021800)
            comb_optim_channel = guild.get_channel(698541739799085077)
            minecraft_channel = guild.get_channel(698104026876608572)

            message = '{} 님, Joon\'s Dreamyard에 오신 것을 환영합니다! '.format(member.mention)
            message += '이 서버는 Joon의 네트워크를 중심으로 만들어진 네트워킹 서버에요. '
            if introduce_channel is not None:
                message += '우선 {} 채널에서 간단하게 소개 부탁드릴게요...!\n'.format(introduce_channel.mention)
            message += '이곳이 어떤 곳인지 궁금하시다면 아래 채널을 방문해 보세요!\n'
            message += '{} - 잡담 채널\n'.format(general.mention)
            if destroyed_channel is not None:
                message += '{} - 조금은 시끄러워도 되는 잡담 채널\n'.format(destroyed_channel.mention)
            if comb_optim_channel is not None:
                message += '{} - Joon과 함께하는 조합최적화 스터디 채널\n'.format(comb_optim_channel.mention)
            if minecraft_channel is not None:
                message += '{} - 마인크래프트를 즐기는 채널'.format(minecraft_channel.mention)

            await general.send(message)

    server_app['discord_bot'] = asyncio.ensure_future(discord_joonbot.start())


async def cleanup_discord_bot(server_app):
    server_app['discord_bot'].cancel()
    await server_app['discord_bot']


app = web.Application()
app.on_startup.append(start_discord_bot)
app.on_cleanup.append(cleanup_discord_bot)
app.add_routes([
    web.post('/slack/events', slack_event_handler.handle_event)
])
