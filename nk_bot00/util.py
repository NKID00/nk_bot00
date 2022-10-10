import datetime
import io
import logging
from typing import AnyStr, Callable, Optional, Union

from mirai.models.message import Forward, ForwardMessageNode, MessageChain, MessageComponent


def forward_message(
    sender_id: int,
    sender_name: str,
    content: list[Union[MessageChain, MessageComponent, str]]
):
    nodes: list[ForwardMessageNode] = []
    time = datetime.datetime.now()
    time -= datetime.timedelta(seconds=len(content))
    for s in content:
        if isinstance(s, (MessageComponent, str)):
            message = MessageChain([s])
        else:
            message = s
        nodes.append(ForwardMessageNode(
            sender_id=sender_id,
            sender_name=sender_name,
            message_chain=message,
            time=time
        ))
        time += datetime.timedelta(seconds=1)
    return Forward(node_list=nodes)


def logger(name: Optional[str] = None) -> logging.Logger:
    if name is None:
        logger_ = logging.getLogger('nk_bot00')
    else:
        logger_ = logging.getLogger('nk_bot00.' + name)
    logger_.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)-8s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    ch.setFormatter(formatter)
    logger_.addHandler(ch)
    return logger_


def endswith_line_break(s: str) -> bool:
    return s.endswith(('\r', '\n'))


class LoggerWrapper:
    def __init__(self, log_func: Callable) -> None:
        self.log_func = log_func
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        if s == '':
            return 0
        lines = s.splitlines(True)
        if len(lines) > 1 or endswith_line_break(lines[0]):
            lines[0] = self._buffer.getvalue() + lines[0]
            self._buffer = io.StringIO()
            for line in lines[:-1]:
                self.log_func(line[:-1])  # remove tailing line break
            if endswith_line_break(lines[-1]):
                self.log_func(lines[-1][:-1])
            else:
                self._buffer.write(lines[-1])
        else:
            self._buffer.write(s)
        return len(s)

    def flush(self) -> None:
        pass
