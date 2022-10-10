from mirai import Mirai, MessageEvent

from nk_bot00.exception import ArgumentException


async def on_command_hello(bot: Mirai, event: MessageEvent, args: list[str], _config: dict):
    '''!hello
    显示友好问候'''
    if len(args) > 0:
        raise ArgumentException('参数过多')
    await bot.send(event, 'Hello, world!')
