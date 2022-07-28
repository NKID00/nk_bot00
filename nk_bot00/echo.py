from typing import List

from mirai import Mirai, MessageEvent


async def on_command_echo(bot: Mirai, event: MessageEvent, args: List[str]):
    '''!echo <文本>...
    回显 <文本>'''
    await bot.send(event, ' '.join(args))
