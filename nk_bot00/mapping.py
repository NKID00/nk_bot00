from argparse import ArgumentParser, ArgumentError
from os import remove as os_remove, walk as os_walk
from pathlib import Path
from sqlite3 import Connection, Cursor, connect, Row
from sys import argv
from re import match as re_match
from gzip import decompress
from traceback import print_exc
from typing import Dict, List, Optional, Tuple
from threading import Lock

from mirai import Mirai, MessageEvent
from httpx import get as httpx_get

from nk_bot00.exception import ArgumentException
from nk_bot00.util import generate_forward_message

MOJANG_METADATA_URL = 'https://piston-meta.mojang.com/mc/game/version_manifest_v2.json'
YARN_METADATA_URL = 'https://meta.fabricmc.net/v2/versions/yarn'
YARN_MAPPING_URL = 'https://maven.fabricmc.net/net/fabricmc/yarn/%s/yarn-%s-tiny.gz'


class Mapping:
    yarn_version: str
    c: Connection
    lock: Lock

    def __init__(self, version: str) -> None:
        for f in next(os_walk('mapping'))[2]:
            if f.startswith(version):
                break
        else:
            raise ValueError('Incorrect game version.')
        self.c = connect(
            Path('mapping') / f,
            check_same_thread=False,
            isolation_level=None
        )
        self.yarn_version = f.rsplit('.', 1)[0]
        self.c.row_factory = Row
        self.lock = Lock()

    def execute(self, sql: str, args: Tuple[str]) -> Cursor:
        with self.lock:
            return self.c.execute(sql, args)

    def find(self, name: str, type_: str, namespace: str) -> Optional[List[str]]:
        if type_ == 'any':
            for t in ('class', 'field', 'method'):
                result = self.find(name, t, namespace)
                if result is not None:
                    return result
            return None
        if namespace == 'any':
            for ns in ('official', 'intermediary', 'mojang', 'yarn'):
                result = self.find(name, type_, ns)
                if result is not None:
                    return result
            return None

        if type_ == 'class':
            if namespace == 'official':
                row = self.execute(
                    'SELECT * FROM class WHERE official = ? LIMIT 1;',
                    (name,)
                ).fetchone()
            else:
                row = self.execute(
                    f'SELECT * FROM class WHERE {namespace} LIKE ? LIMIT 1;',
                    (f'%{name}',)
                ).fetchone()
            if row is None:
                return None

            return [
                f'yarn {self.yarn_version}',
                f'official: {row["official"]}',
                f'intermediary: {row["intermediary"]}',
                f'mojang: {row["mojang"]}',
                f'yarn: {row["yarn"]}',
            ]

        elif type_ == 'field':
            row = self.execute(
                f'SELECT * FROM field WHERE {namespace} = ? LIMIT 1;',
                (name,)
            ).fetchone()
            if row is None:
                return None

            row_class = self.execute(
                'SELECT * FROM class WHERE official = ? LIMIT 1;',
                (row['official_class'],)
            ).fetchone()
            if row_class is None:
                return None

            return [
                f'yarn {self.yarn_version}',
                f'official: {row["official_class"]}.{row["official"]}',
                f'field descriptor: {row["field_descriptor"]}',
                f'intermediary: {row["intermediary"]}',
                f'mojang: {row_class["mojang"]}.{row["mojang"]}',
                f'yarn: {row_class["yarn"]}.{row["yarn"]}'
            ]

        elif type_ == 'method':
            row = self.execute(
                f'SELECT * FROM method WHERE {namespace} = ? LIMIT 1;',
                (name,)
            ).fetchone()
            if row is None:
                return None

            row_class = self.execute(
                'SELECT * FROM class WHERE official = ? LIMIT 1;',
                (row['official_class'],)
            ).fetchone()
            if row_class is None:
                return None

            return [
                f'yarn {self.yarn_version}',
                f'official: {row["official_class"]}.{row["official"]}',
                f'method descriptor: {row["method_descriptor"]}',
                f'intermediary: {row["intermediary"]}',
                f'mojang: {row_class["mojang"]}.{row["mojang"]}'
                f'{map_method_mojang(row["method_descriptor"], self.c)}',
                f'mojang mixin: "{row["mojang"]}'
                f'{map_mixin_mojang(row["method_descriptor"], self.c)}"',
                f'yarn: {row_class["yarn"]}.{row["yarn"]}'
                f'{map_method_yarn(row["method_descriptor"], self.c)}',
                f'yarn mixin: "{row["yarn"]}{map_mixin_yarn(row["method_descriptor"], self.c)}"'
            ]
        return None


PARSER = ArgumentParser(add_help=False, exit_on_error=False)
PARSER.add_argument('name')
PARSER.add_argument('type', choices=(
    'class', 'field', 'method', 'any'
), nargs='?', default='any')
PARSER.add_argument('namespace', choices=(
    'official', 'intermediary', 'mojang', 'yarn', 'any'
), nargs='?', default='any')
PARSER.add_argument('mcVersion', choices=(
    '1.15.2', '1.16.5', '1.17.1', '1.18.2', '1.19'
), nargs='?', default='1.19')


def redirect_exit(_status=0, message=None):
    raise ArgumentException(message)


def redirect_error(message):
    raise ArgumentException(message)


PARSER.exit = redirect_exit  # type: ignore
PARSER.error = redirect_error  # type: ignore
del redirect_exit
del redirect_error
MAPPINGS: Dict[str, Mapping] = {}


async def on_command_mapping(bot: Mirai, event: MessageEvent, args_raw: List[str], _config: dict):
    '''!m <名称> [<类型>] [<命名空间>] [<mc版本>]
    查找并显示匹配的第一个映射
    <类型> := class | field | method | [any]
    <命名空间> := official | intermediary | mojang | yarn | [any]
    <mc版本> := 1.15.2 | 1.16.5 | 1.17.1 | 1.18.2 | [1.19]'''
    try:
        args = PARSER.parse_args(args_raw)
    except ArgumentError as e:
        raise ArgumentException from e
    version = args.mcVersion
    if version not in MAPPINGS:
        MAPPINGS[version] = Mapping(version)
    try:
        result = MAPPINGS[version].find(args.name, args.type, args.namespace)
    except Exception:  # pylint: disable=broad-except
        print_exc()
        await bot.send(event, '内部错误')
    else:
        if result is None:
            await bot.send(event, '未知映射')
        else:
            await bot.send(event, generate_forward_message(bot.qq, 'Yet Another Fabric Bot', result))


def fetch_mapping() -> None:
    version = argv[1]
    print(f'Target version {version}')
    print('Initializing database ...')
    mapping_path = Path('mapping')
    if not mapping_path.exists():
        mapping_path.mkdir()
    connection = init_database()
    print('Mojang mapping')
    fetch_mojang_mapping(version, connection)
    print('Yarn mapping')
    yarn_version = fetch_yarn_mapping(version, connection)
    print('Writing database ...')
    write_database(yarn_version, connection)
    connection.commit()
    connection.close()
    print('Done')


def init_database() -> Connection:
    c = connect(':memory:', isolation_level=None)
    c.execute('''CREATE TABLE class (
        official TEXT PRIMARY KEY NOT NULL,
        intermediary TEXT,
        mojang TEXT,
        yarn TEXT
    );''')
    c.execute('''CREATE TABLE field (
        official_class TEXT NOT NULL,
        official TEXT NOT NULL,
        field_descriptor TEXT,
        intermediary TEXT,
        mojang TEXT,
        yarn TEXT,
        PRIMARY KEY (official_class, official)
    );''')
    c.execute('''CREATE TABLE method (
        official_class TEXT NOT NULL,
        official TEXT NOT NULL,
        method_descriptor TEXT NOT NULL,
        intermediary TEXT,
        mojang TEXT,
        yarn TEXT,
        PRIMARY KEY (official_class, official, method_descriptor)
    );''')
    return c


def insert_or_update(
    table: str,
    primary_key: Dict[str, str],
    other: Dict[str, str],
    c: Connection
) -> None:
    c.execute(
        f'INSERT OR IGNORE INTO {table} ({", ".join(primary_key.keys())}) '
        f'VALUES ({", ".join("?" * len(primary_key))});',
        list(primary_key.values())
    )
    if len(other) > 0:
        c.execute(
            f'UPDATE {table} SET {", ".join(s + " = ?" for s in other.keys())} '
            f'WHERE ({", ".join(primary_key.keys())}) = ({", ".join("?" * len(primary_key))});',
            (*other.values(), *primary_key.values())
        )


FIELD_DESCRIPTORS = {
    'byte': 'B',
    'char': 'C',
    'double': 'D',
    'float': 'F',
    'int': 'I',
    'long': 'J',
    'short': 'S',
    'boolean': 'Z',
    'void': 'V'
}


def remap_field_mojang(field: str, c: Connection) -> str:
    array_dimension_count = 0
    while field.endswith('[]'):
        field = field[:-2]
        array_dimension_count += 1
    if field in FIELD_DESCRIPTORS:
        return '[' * array_dimension_count + FIELD_DESCRIPTORS[field]
    for row in c.execute('SELECT official FROM class WHERE mojang = ?;', (field,)):
        field = row[0]
        break
    field = field.replace('.', '/')
    return f'{"[" * array_dimension_count}L{field};'


def remap_method_mojang(method: str, c: Connection) -> Optional[str]:
    m = re_match(r'\(([\w$.[\],]*)\)([\w$.[\]]+)', method)
    if m is None:
        return None
    args, retval = m.groups()
    args = args.split(',')
    args = ''.join(remap_field_mojang(arg, c)
                   for arg in args if len(arg) > 0)
    retval = remap_field_mojang(retval, c)
    return f'({args}){retval}'


FIELD_TYPES = {
    'B': 'byte',
    'C': 'char',
    'D': 'double',
    'F': 'float',
    'I': 'int',
    'J': 'long',
    'S': 'short',
    'Z': 'boolean',
    'V': 'void'
}


def map_field_mojang(field: str, c: Connection) -> str:
    array_dimension_count = 0
    while field.startswith('['):
        field = field[1:]
        array_dimension_count += 1
    if field in FIELD_TYPES:
        return FIELD_TYPES[field] + '[]' * array_dimension_count
    if field.startswith('L') and field.endswith(';'):
        field = field[1:-1]
    field = field.replace('/', '.')
    for row in c.execute('SELECT mojang FROM class WHERE official = ?;', (field,)):
        field = row[0]
        break
    return field + '[]' * array_dimension_count


def map_field_yarn(field: str, c: Connection) -> str:
    array_dimension_count = 0
    while field.startswith('['):
        field = field[1:]
        array_dimension_count += 1
    if field in FIELD_TYPES:
        return FIELD_TYPES[field] + '[]' * array_dimension_count
    if field.startswith('L') and field.endswith(';'):
        field = field[1:-1]
    field = field.replace('/', '.')
    for row in c.execute('SELECT yarn FROM class WHERE official = ?;', (field,)):
        field = row[0]
        break
    return field + '[]' * array_dimension_count


def map_method_mojang(method: str, c: Connection) -> Optional[str]:
    m = re_match(r'\(([\w$/[;]*)\)([\w$./[;]+)', method)
    if m is None:
        return None
    args, retval = m.groups()
    buffer = ''
    object_flag = False
    args_list = []
    while len(args) > 0:
        buffer += args[0]
        if object_flag:
            if args[0] == ';':
                args_list.append(map_field_mojang(buffer, c))
                buffer = ''
                object_flag = False
        else:
            if args[0] in FIELD_TYPES:
                args_list.append(map_field_mojang(buffer, c))
                buffer = ''
            elif args[0] == 'L':
                object_flag = True
        args = args[1:]
    retval = map_field_mojang(retval, c)
    return f'({", ".join(args_list)}) -> {retval}'


def map_method_yarn(method: str, c: Connection) -> Optional[str]:
    m = re_match(r'\(([\w$/[;]*)\)([\w$./[;]+)', method)
    if m is None:
        return None
    args, retval = m.groups()
    buffer = ''
    object_flag = False
    args_list = []
    while len(args) > 0:
        buffer += args[0]
        if object_flag:
            if args[0] == ';':
                args_list.append(map_field_yarn(buffer, c))
                buffer = ''
                object_flag = False
        else:
            if args[0] in FIELD_TYPES:
                args_list.append(map_field_yarn(buffer, c))
                buffer = ''
            elif args[0] == 'L':
                object_flag = True
        args = args[1:]
    retval = map_field_yarn(retval, c)
    return f'({", ".join(args_list)}) -> {retval}'


def map_mixin_mojang(descriptor: str, c: Connection) -> str:
    buffer = ''
    object_flag = False
    map_mixin = ''
    while len(descriptor) > 0:
        buffer += descriptor[0]
        if object_flag:
            if descriptor[0] == ';':
                s = buffer[:-1]
                for row in c.execute('SELECT mojang FROM class WHERE official = ?;', (s,)):
                    s = row[0]
                    break
                s = s.replace('.', '/')
                map_mixin += s + ';'
                buffer = ''
                object_flag = False
        else:
            if descriptor[0] == 'L':
                map_mixin += buffer
                buffer = ''
                object_flag = True
        descriptor = descriptor[1:]
    map_mixin += buffer
    return map_mixin


def map_mixin_yarn(descriptor: str, c: Connection) -> str:
    buffer = ''
    object_flag = False
    map_mixin = ''
    while len(descriptor) > 0:
        buffer += descriptor[0]
        if object_flag:
            if descriptor[0] == ';':
                s = buffer[:-1]
                for row in c.execute('SELECT yarn FROM class WHERE official = ?;', (s,)):
                    s = row[0]
                    break
                s = s.replace('.', '/')
                map_mixin += s + ';'
                buffer = ''
                object_flag = False
        else:
            if descriptor[0] == 'L':
                map_mixin += buffer
                buffer = ''
                object_flag = True
        descriptor = descriptor[1:]
    map_mixin += buffer
    return map_mixin


def fetch_mojang_mapping(version: str, c: Connection) -> None:
    print('  Fetching metadata ...')
    r = httpx_get(MOJANG_METADATA_URL)

    print('  Parsing metadata ...')
    for item in r.json()['versions']:
        if item['id'] == version:
            url = item['url']
            break

    print('  Fetching version metadata ...')
    r = httpx_get(url)

    print('  Parsing version metadata ...')
    downloads = r.json()['downloads']
    if 'client_mappings' not in downloads:
        print('  Mapping not found')
        return

    print('  Fetching mapping ...')
    url = downloads['client_mappings']['url']
    r = httpx_get(url)

    print('  Parsing mapping ...')
    for l in r.text.splitlines(False):
        if l.startswith('#'):
            continue
        m = re_match(r'([\w$.-]+)\s+->\s+([\w$.]+):', l)
        if m is not None:  # matches a class
            mapping_class = m[2]
            insert_or_update('class', {
                'official': m[2]
            }, {
                'mojang': m[1]
            }, c)
            continue
        m = re_match(r'\s+[\w$.[\]]+\s+([\w$]+)\s+->\s+([\w$]+)', l)
        if m is not None:  # matches a field
            insert_or_update('field', {
                'official': m[2],
                'official_class': mapping_class
            }, {
                'mojang': m[1]
            }, c)
            continue
        m = re_match(
            r'\s+(?:\d+:\d+:)?([\w$.[\]]+)\s+([\w$<>]+)(\([\w$.[\],]*\))\s+->\s+([\w<>$]+)', l
        )
        if m is not None:  # matches a method
            insert_or_update('method', {
                'method_descriptor': m[3] + m[1],
                'official': m[4],
                'official_class': mapping_class
            }, {
                'mojang': m[2]
            }, c)
            continue
        print(f'Parsing "{l}" failed!')

    print('  Remapping method descriptor ...')
    for row in c.execute(
        'SELECT official_class, official, method_descriptor FROM method;'
    ).fetchall():
        method_descriptor = remap_method_mojang(row[2], c)
        if method_descriptor is None:
            print(f'Remapping "{row[2]}" failed!')
            continue
        c.execute(
            'UPDATE method SET method_descriptor = ? WHERE '
            '(official_class, official, method_descriptor) = (?, ?, ?);',
            (method_descriptor, row[0], row[1], row[2])
        )


def fetch_yarn_mapping(version: str, c: Connection) -> str:
    print('  Fetching metadata ...')
    r = httpx_get(YARN_METADATA_URL)

    print('  Parsing metadata ...')
    latest_build = 0
    latest_version = ''
    for item in r.json():
        if item['gameVersion'] == version:
            if latest_build < item['build']:
                latest_version = item['version']
            break

    print(f'  Target version {latest_version} ...')
    print('  Fetching mapping ...')
    url = YARN_MAPPING_URL % ((latest_version,) * 2)
    r = httpx_get(url)

    print('  Parsing mapping ...')
    for l in decompress(r.content).decode('utf8').splitlines(False)[1:]:
        type_, *items = l.split()
        if type_ == 'CLASS':
            insert_or_update('class', {
                'official': items[0].replace('/', '.')
            }, {
                'intermediary': items[1].replace('/', '.'),
                'yarn': items[2].replace('/', '.')
            }, c)
            continue
        elif type_ == 'FIELD':
            insert_or_update('field', {
                'official_class': items[0].replace('/', '.'),
                'official': items[2].replace('/', '.')
            }, {
                'field_descriptor': items[1],
                'intermediary': items[3].replace('/', '.'),
                'yarn': items[4].replace('/', '.')
            }, c)
            continue
        elif type_ == 'METHOD':
            insert_or_update('method', {
                'official_class': items[0].replace('/', '.'),
                'method_descriptor': items[1],
                'official': items[2].replace('/', '.')
            }, {
                'intermediary': items[3].replace('/', '.'),
                'yarn': items[4].replace('/', '.')
            }, c)
            continue
        print(f'Parsing "{l}" failed!')

    return latest_version


def write_database(version: str, c: Connection):
    path = Path('mapping') / f'{version}.db'
    if path.exists():
        os_remove(path)
    c.execute('ATTACH DATABASE ? AS disk;', (str(path),))
    c.execute('CREATE TABLE disk.class AS SELECT * FROM class;')
    c.execute('CREATE TABLE disk.field AS SELECT * FROM field;')
    c.execute('CREATE TABLE disk.method AS SELECT * FROM method;')


if __name__ == '__main__':
    fetch_mapping()
