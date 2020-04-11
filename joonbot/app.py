import asyncio
import hashlib
import hmac
import os

import slack
from aiohttp import web

from .bot import joonbot


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


app = web.Application()
app.add_routes([
    web.post('/slack/events', slack_event_handler.handle_event)
])
