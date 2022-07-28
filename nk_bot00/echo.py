from typing import List

from mirai import Mirai, MessageEvent


async def on_command_echo(bot: Mirai, event: MessageEvent, args: List[str], _config: dict):
    '''!echo <文本>...
    回显 <文本>'''
    content = ' '.join(args)
    if len(content) > 50:
        await bot.send(event, '文本过长')
    else:
        await bot.send(event, content)
