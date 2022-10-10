from mirai import Mirai, MessageEvent

from nk_bot00.exception import ArgumentException


async def on_command_echo(bot: Mirai, event: MessageEvent, args: list[str], _config: dict):
    '''!echo [文本...]
    回显文本'''
    if len(args) == 0:
        raise ArgumentException('参数不足')
    content = ' '.join(args)
    if len(content) > 50:
        raise ArgumentException('文本过长')
    await bot.send(event, content)
