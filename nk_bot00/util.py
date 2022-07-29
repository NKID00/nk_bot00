from datetime import datetime, timedelta
from typing import List, Union

from mirai.models.message import Forward, ForwardMessageNode, MessageChain, MessageComponent


def forward_message(
    sender_id: int,
    sender_name: str,
    content: List[Union[MessageChain, MessageComponent, str]]
):
    nodes: List[ForwardMessageNode] = []
    time = datetime.now()
    time -= timedelta(seconds=len(content))
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
        time += timedelta(seconds=1)
    return Forward(node_list=nodes)
