from typing import List

from mirai import Mirai, MessageEvent


async def on_command_hello(bot: Mirai, event: MessageEvent, _args: List[str]):
    '''!hello
    显示友好问候'''
    await bot.send(event, 'Hello, world!')
