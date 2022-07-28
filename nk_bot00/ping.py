from typing import List

from mirai import Mirai, MessageEvent, GroupMessage
from mcstatus import JavaServer

from nk_bot00.util import generate_forward_message


async def on_command_ping(bot: Mirai, event: MessageEvent, _args_raw: List[str], config: dict):
    '''!ping
    查询服务器状态'''
    if not isinstance(event, GroupMessage) or str(event.group.id) not in config:
        return
    try:
        server: JavaServer = await JavaServer.async_lookup(config[str(event.group.id)])
        status = await server.async_status()
        content = []
        content.append(f'Version: {status.version.name}')
        content.append(f'Description: "{status.description}"')
        content.append(f'Ping: {status.latency}ms')
        players = f'Players: {status.players.online}/{status.players.max}'
        if status.players.sample is not None:
            players += ''.join(f'\n  {player.name}' for player in status.players.sample)
        content.append(players)
    except Exception:  # pylint: disable=broad-except
        await bot.send(event, '连接失败')
    else:
        await bot.send(event, generate_forward_message(bot.qq, 'Pong', content))
