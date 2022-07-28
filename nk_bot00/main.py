from shlex import split as shlex_split
from typing import Iterable, List, Optional, Tuple
from json import load as json_load

from mirai import Mirai, FriendMessage, GroupMessage, TempMessage, WebSocketAdapter, MessageChain

from .exception import ArgumentException
from .hello import on_command_hello
from .echo import on_command_echo
from .mapping import on_command_mapping


COMMAND_HANDLER = {
    'hello': on_command_hello,
    'echo': on_command_echo,
    'mapping': on_command_mapping
}
COMMAND_ALIAS = {
    'e': 'echo',
    'm': 'mapping',
    'map': 'mapping'
}


def parse_command(message_chain: MessageChain) -> Tuple[Optional[str], Optional[List[str]]]:
    if any(item.type not in ['Source', 'Plain'] for item in message_chain):
        # 只接受纯文本
        return None, None
    message = str(message_chain).strip()
    if not message.startswith('!'):
        # 只接受 '!' 开头
        return None, None
    message = message[1:]
    command, *args = shlex_split(message)
    command = COMMAND_ALIAS.get(command, command)
    return command, args


def get_help_message(args: List[str], available_commands: Iterable[str]) -> str:
    if len(args) > 0:
        command = args[0]
        if command in COMMAND_HANDLER:
            docstring = COMMAND_HANDLER[command].__doc__
            if docstring is not None:
                return '\n  '.join(s.strip() for s in docstring.splitlines(False))
    return (
        '!<命令> <参数>\n'
        '  执行命令\n'
        '!help <命令>\n'
        '  显示命令用法\n'
        '  <命令> := ' + ' | '.join(available_commands)
    )


def main():
    with open('config.json', 'r', encoding='utf8') as f:
        config = json_load(f)
    friend_permission = {int(k): v for k, v in config['friend_permission'].items()}
    group_permission = {int(k): v for k, v in config['group_permission'].items()}
    bot = Mirai(config['bot_qq'], adapter=WebSocketAdapter(
        verify_key=config['verify_key'], host=config['host'], port=config['port']
    ))

    @bot.on(FriendMessage)
    async def _(event: FriendMessage):
        if event.sender.id in friend_permission:
            command, args = parse_command(event.message_chain)
            if command is None or args is None:
                return
            available_commands = friend_permission[event.sender.id]
            if command == 'help':
                await bot.send(event, get_help_message(args, available_commands))
            elif command in available_commands:
                try:
                    await COMMAND_HANDLER[command](bot, event, args)
                except ArgumentException:
                    await bot.send(event, get_help_message([command], available_commands))

    @bot.on(GroupMessage)
    async def _(event: GroupMessage):
        if event.group.id in group_permission:
            command, args = parse_command(event.message_chain)
            if command is None or args is None:
                return
            available_commands = group_permission[event.group.id]
            if command == 'help':
                await bot.send(event, get_help_message(args, available_commands))
            elif command in available_commands:
                try:
                    await COMMAND_HANDLER[command](bot, event, args)
                except ArgumentException:
                    await bot.send(event, get_help_message([command], available_commands))

    # 据说临时聊天封号风险较大，暂时禁用
    #
    # @bot.on(TempMessage)
    # async def _(event: GroupMessage):
    #     if event.group.id in GROUP_PERMISSION:
    #         command, args = parse_command(event.message_chain)
    #         if command is None or args is None:
    #             return
    #         available_commands = GROUP_PERMISSION[event.group.id]
    #         if command == 'help':
    #             await bot.send(event, get_help_message(args, available_commands))
    #             if len(args) == 0:
    #                 await bot.send(event, '从不同群聊发起的临时会话拥有不同的命令执行权限')
    #         elif command in available_commands:
    #             await COMMAND_HANDLER[command](bot, event, args)

    bot.run(host='localhost', port=32181)


if __name__ == '__main__':
    main()
