import os

import aiohttp

from .core import SlackBot
from .exceptions import MessageHandleAborted


joonbot = SlackBot(
    token=os.getenv('SLACK_API_TOKEN'),
    name='joonbot',
    triggers=[
        'joonbot ',
        '<@U010K3P2ZPW> ',
        '준봇 ',
    ],
    group='__all__',
    channels='__all__',
    report_channels=['GQWM0LXEV']
)


@joonbot.pre_command_hook
async def ignore_bot(*args, **kwargs):
    bot = kwargs['bot']
    data = kwargs['event']
    user_id = data['user']
    user_info = (await bot.client.users_info(user=user_id))['user']
    is_bot = user_info['is_bot']

    if is_bot:
        raise MessageHandleAborted('bot')


@joonbot.command(aliases=['help', '?'])
async def help_message(*args, **kwargs):
    """ 이 메세지(도움말)을 보여줍니다."""
    bot = kwargs['bot']
    data = kwargs['event']
    user_id = data['user']
    channel_id = data['channel']

    message = ''
    sorted_commands = sorted(bot.get_commands(), key=lambda func: func.aliases[0])

    help_list = args[1:]

    for f in sorted_commands:
        if f.group == '__all__' or user_id in f.group:
            if not help_list or set(help_list).intersection(set(f.aliases)):
                message += '*{}* : {}\n'.format('/'.join(f.aliases), f.__doc__)

    await bot.client.chat_postMessage(channel=channel_id, text=message, as_user=True)


@joonbot.command(aliases=['echo', '에코'])
async def echo(*args, **kwargs):
    """ 흔한 echo """
    bot = kwargs['bot']
    data = kwargs['event']
    channel_id = data['channel']

    revised_text = ' '.join(args[1:])
    await bot.client.chat_postMessage(channel=channel_id, text=revised_text, as_user=True)


@joonbot.command(aliases=['dust', '미세먼지'])
async def air_pollution(*args, **kwargs):
    """ 실시간 미세먼지 정보 / Usage: _미세먼지 측정소_"""
    bot = kwargs['bot']
    data = kwargs['event']
    channel_id = data['channel']

    if len(args) == 1:
        await bot.client.chat_postMessage(channel=channel_id, text='측정소를 입력해 주세요.', as_user=True)
        return

    station = args[1]

    api_url = 'http://openapi.airkorea.or.kr/openapi/services/rest/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty'
    service_key = os.getenv('OPENAPI_SERVICE_KEY')

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params={
                'serviceKey': service_key,
                'numOfRows': 10,
                'pageNo': 1,
                'stationName': station,
                'dataTerm': 'DAILY',
                'ver': '1.3',
                '_returnType': 'json',
            }) as resp:
                resp_json = await resp.json(content_type=None)
    except aiohttp.ClientError:
        await bot.client.chat_postMessage(channel=channel_id, text='현재 사용할 수 없는 기능입니다.', as_user=True)
        return

    air_level = [
        '매우좋음 :blobaww:',
        '좋음 :smile:',
        '보통 :slightly_smiling_face:',
        '나쁨 :fearful:',
        '매우나쁨 :rage:',
    ]

    message = '알 수 없는 오류가 발생했습니다. 일시적인 현상일 수 있으니, 잠시 후에 다시 시도해 주세요.'
    if 'list' in resp_json:
        info_list = resp_json['list']
        if info_list:
            for dust_info in info_list:
                try:
                    data_time = dust_info['dataTime']
                    pm10value = int(dust_info['pm10Value'])
                    pm10grade = int(dust_info['pm10Grade1h'])
                    pm25value = int(dust_info['pm25Value'])
                    pm25grade = int(dust_info['pm25Grade1h'])

                    message = '{} {} 미세먼지 정보\n'.format(station, data_time)
                    message += '미세먼지: {} ({})\n'.format(air_level[pm10grade], pm10value)
                    message += '초미세먼지: {} ({})'.format(air_level[pm25grade], pm25value)
                    break
                except (ValueError, IndexError, KeyError):
                    continue
            else:
                message = '현재 표시 가능한 미세먼지 정보가 없습니다. 잠시 후에 다시 시도해 주세요.'
        else:
            message = '해당 측정소가 존재하지 않습니다'

    await bot.client.chat_postMessage(channel=channel_id, text=message, as_user=True)


@joonbot.command(aliases=['mask', '마스크', '마스크정보'])
async def mask(*args, **kwargs):
    """ 실시간 마스크 판매 현황 """
    bot = kwargs['bot']
    data = kwargs['event']
    channel_id = data['channel']

    if len(args) <= 2:
        await bot.client.chat_postMessage(
            channel=channel_id,
            text='주소를 구체적으로 입력해 주세요.',
            as_user=True
        )
        return

    try:
        page = int(args[-1])
        address = ' '.join(args[1:-1])
    except ValueError:
        page = 1
        address = ' '.join(args[1:])

    api_url = 'https://8oi9s0nnth.apigw.ntruss.com/corona19-masks/v1/storesByAddr/json'

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params={
                'address': address,
            }) as resp:
                resp_json = await resp.json(content_type=None)
    except aiohttp.ClientError:
        await bot.client.chat_postMessage(channel=channel_id, text='현재 사용할 수 없는 기능입니다.', as_user=True)
        return

    store_count = resp_json['count']
    if store_count == 0:
        await bot.client.chat_postMessage(channel=channel_id, text='검색 결과가 없습니다.', as_user=True)
        return

    stores = resp_json['stores']
    num_pages = (store_count - 1) // 5 + 1
    page = max(min(num_pages, page), 1)
    start = 5 * (page - 1)
    end = min(store_count, 5 * page)

    amount_dict = {
        'plenty': (4, '100개 이상 :smile:'),
        'some': (3, '30개 이상 100개 미만 :slightly_smiling_face:'),
        'few': (2, '2개 이상 30개 미만 :confused:'),
        'empty': (1, '1개 이하 :cry:'),
        'break': (0, '판매 중지 :x:'),
        'unknown': (-1, '(알 수 없음)')
    }

    store_type = {
        '00': '(알 수 없음)',
        '01': '약국',
        '02': '우체국',
        '03': '농협',
    }

    message = '`{}`로 검색한 마스크 판매 현황입니다. (페이지: {} / {})\n\n'.format(address, page, num_pages)

    stores = sorted(stores, key=lambda s: amount_dict.get(s.get('remain_stat', 'unknown'), (-1, '')), reverse=True)
    store_info_list = []
    for i in range(start, end):
        store = stores[i]
        store_info = '*이름*: {}\n'.format(store.get('name') or '(이름 없음)')
        store_info += '*종류*: {}\n'.format(store_type.get(store.get('type'), '(알 수 없음)'))
        store_info += '*주소*: {}\n'.format(store.get('addr') or '(주소 없음)')
        store_info += '*재고*: {}\n'.format(amount_dict.get(store.get('remain_stat'), (-1, '(알 수 없음)'))[1])
        store_info += '*입고*: {}\n'.format(store.get('stock_at') or '(알 수 없음)')
        store_info_list.append(store_info)

    message += '\n\n'
    message += '\n\n'.join(store_info_list)
    await bot.client.chat_postMessage(channel=channel_id, text=message, as_user=True)
