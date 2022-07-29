from shlex import split as shlex_split
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Tuple
from json import load as json_load

from mirai import Mirai, FriendMessage, GroupMessage, MessageEvent, WebSocketAdapter, MessageChain

from nk_bot00.exception import ArgumentException
from nk_bot00.hello import on_command_hello
from nk_bot00.echo import on_command_echo
from nk_bot00.mapping import on_command_mapping
from nk_bot00.ping import on_command_ping


COMMAND_HANDLER: Dict[str, Callable[[Mirai, MessageEvent, List[str], Any], Awaitable[None]]] = {
    'hello': on_command_hello,
    'echo': on_command_echo,
    'mapping': on_command_mapping,
    'ping': on_command_ping
}
COMMAND_ALIAS: Dict[str, str] = {
    'h': 'help',
    'm': 'mapping',
    'map': 'mapping'
}


def parse_command(command_prefix: Tuple[str], message_chain: MessageChain) -> Optional[Tuple[str, List[str]]]:
    if any(item.type not in ['Source', 'Plain'] for item in message_chain):
        # 只接受纯文本
        return None
    message = str(message_chain).strip()
    if not message.startswith(command_prefix):
        # 只接受允许的前缀开头的命令
        return None
    message = message[1:].strip()
    command, *args = shlex_split(message)
    command = COMMAND_ALIAS.get(command, command)
    return command, args


def get_help_message(args: List[str], available_commands: Iterable[str]) -> str:
    if len(args) == 1:
        command = args[0]
        if command in COMMAND_HANDLER:
            docstring = COMMAND_HANDLER[command].__doc__
            if docstring is not None:
                return '\n  '.join(s.strip() for s in docstring.splitlines(False))
    if len(args) > 1:
        raise ArgumentException('参数过多')
    return (
        '![命令] [参数...]\n'
        '  执行命令\n'
        '!h [命令]\n'
        '  显示命令用法\n'
        '  [命令] := ' + ' | '.join(available_commands)
    )


async def execute_command(
    bot: Mirai,
    event: MessageEvent,
    command: str,
    args: List[str],
    available_commands: List[str],
    command_config: Mapping[str, Any]
) -> None:
    try:
        if command == 'help':
            await bot.send(event, get_help_message(args, available_commands))
        elif command in available_commands:
            await COMMAND_HANDLER[command](bot, event, args, command_config[command])
    except ArgumentException as e:
        await bot.send(
            event,
            f'{e}\n'
            f'!h [命令]\n'
            f'  显示命令用法\n'
        )


def main():
    with open('config.json', 'r', encoding='utf8') as f:
        config = json_load(f)
    command_prefix = tuple(config['command_prefix'])
    friend_permission = {
        int(k): v for k, v in config['friend_permission'].items()}
    group_permission = {
        int(k): v for k, v in config['group_permission'].items()}
    bot = Mirai(config['bot_qq'], adapter=WebSocketAdapter(
        verify_key=config['verify_key'], host=config['host'], port=config['port']
    ))
    command_config = config['command_config']
    for c in COMMAND_HANDLER:
        if c not in command_config:
            command_config[c] = {}

    @bot.on(MessageEvent)
    async def _(event: MessageEvent):
        if isinstance(event, FriendMessage):
            if event.sender.id not in friend_permission:
                return
            available_commands = friend_permission[event.sender.id]
        elif isinstance(event, GroupMessage):
            if event.group.id not in group_permission:
                return
            available_commands = group_permission[event.group.id]
        else:
            return

        optional = parse_command(command_prefix, event.message_chain)
        if optional is None:
            return
        command, args = optional
        await execute_command(
            bot, event, command, args,
            available_commands, command_config[command]
        )

    bot.run(host='localhost', port=32181)


if __name__ == '__main__':
    main()
