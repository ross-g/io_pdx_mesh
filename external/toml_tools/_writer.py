# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Taneli Hukkinen
# Licensed to PSF under a Contributor Agreement.


from collections import namedtuple
from datetime import date, datetime, time
from decimal import Decimal
import string

from ._helpers import ReadOnlyDict, long

try:
    basestring #type: ignore
except NameError:
    basestring = str


ASCII_CTRL = frozenset(chr(i) for i in range(32)) | frozenset(chr(127))
ILLEGAL_BASIC_STR_CHARS = frozenset('"\\') | ASCII_CTRL - frozenset("\t")
BARE_KEY_CHARS = frozenset(string.ascii_letters + string.digits + "-_")
ARRAY_TYPES = (list, tuple)
ARRAY_INDENT = " " * 4
MAX_LINE_LENGTH = 100

COMPACT_ESCAPES = ReadOnlyDict([(u"\u0008", r"\b"),  # backspace
                                (u"\u000A", r"\n"),  # linefeed
                                (u"\u000C", r"\f"),  # form feed
                                (u"\u000D", r"\r"),  # carriage return
                                (u"\u0022", r'\"'),  # quote
                                (u"\u005C", r"\\")  # backslash
                               ]
                              )


def dump(__obj, __fp, multiline_strings = False):
    #type(dict, BinaryIO, bool) -> None
    ctx = Context(multiline_strings, {})
    for chunk in gen_table_chunks(__obj, ctx, name=""):
        __fp.write(chunk.encode(encoding = 'utf8'))


def dumps(__obj,  multiline_strings = False):
    #type(dict, bool) -> str
    ctx = Context(multiline_strings, {})
    return "".join(gen_table_chunks(__obj, ctx, name=""))




Context = namedtuple('Context', ('allow_multiline', 'inline_table_cache'))


def gen_table_chunks(table, ctx, name, inside_aot = False):
    #type(Mapping, Context, str bool) -> Iterator[str]
    yielded = False
    literals = []
    tables = []  
    for k, v in table.items():
        if isinstance(v, dict):
            tables.append((k, v, False))
        elif is_aot(v) and not all(is_suitable_inline_table(t, ctx) for t in v):
            tables.extend((k, t, True) for t in v)
        else:
            literals.append((k, v))

    if inside_aot or name and (literals or not tables):
        yielded = True
        yield ("[[%s]]\n" if inside_aot else "[%s]\n") % name

    if literals:
        yielded = True
        for k, v in literals:
            yield "%s = %s\n" % (format_key_part(k), format_literal(v, ctx))

    for k, v, in_aot in tables:
        if yielded:
            yield "\n"
        else:
            yielded = True
        key_part = format_key_part(k)
        display_name = ("%s.%s" % (name, key_part)) if name else key_part
        for chunk in gen_table_chunks(v, ctx, name=display_name, inside_aot=in_aot):
            yield chunk


def format_literal(obj, ctx, nest_level= 0):
    #type(type[any], Context, int) -> str
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, (int, long, date, datetime)):
        return str(obj)
    
    # repr of floats Makes Python 2 behaviour consistent
    # https://stackoverflow.com/questions/25898733/why-does-strfloat-return-more-digits-in-python-3-than-python-2
    if isinstance(obj, float):
        return repr(obj)
    if isinstance(obj, Decimal):
        return format_decimal(obj)
    if isinstance(obj, time):
        if obj.tzinfo:
            raise ValueError("TOML does not support offset times")
        return str(obj)
    if isinstance(obj, basestring):
        return format_string(obj, allow_multiline=ctx.allow_multiline)
    if isinstance(obj, ARRAY_TYPES):
        return format_inline_array(obj, ctx, nest_level)
    if isinstance(obj, dict):
        return format_inline_table(obj, ctx)
    raise TypeError("Object: %s of type %s is not TOML serializable" % (obj, type(obj)))


def format_decimal(obj):
    #type(Decimal) -> str
    if obj.is_nan():
        return "nan"
    if obj == Decimal("inf"):
        return "inf"
    if obj == Decimal("-inf"):
        return "-inf"
    return str(obj)


def format_inline_table(obj, ctx):
    #type(type[any], Context) -> str

    # check cache first
    obj_id = id(obj)
    if obj_id in ctx.inline_table_cache:
        return ctx.inline_table_cache[obj_id]

    if not obj:
        rendered = "{}"
    else:
        rendered = (
            "{ "
            + ", ".join(
                ("%s = %s" % (format_key_part(k), format_literal(v, ctx)))
                for k, v in obj.items()
            )
            + " }"
        )
    ctx.inline_table_cache[obj_id] = rendered
    return rendered


def format_inline_array(obj, ctx, nest_level):
    #type(tuple | list, Context, int) -> str
    if not obj:
        return "[]"
    item_indent = ARRAY_INDENT * (1 + nest_level)
    closing_bracket_indent = ARRAY_INDENT * nest_level
    return (
        "[\n"
        + ",\n".join(
            item_indent + format_literal(item, ctx, nest_level=nest_level + 1)
            for item in obj
        )
        + ",\n%s]" % closing_bracket_indent
    )


def format_key_part(part):
    #type(str) -> str
    if part and BARE_KEY_CHARS.issuperset(part):
        return part
    return format_string(part, allow_multiline=False)


def format_string(s, allow_multiline):
    #type(str, bool) -> str
    do_multiline = allow_multiline and "\n" in s
    if do_multiline:
        result = '"""\n'
        s = s.replace("\r\n", "\n")
    else:
        result = '"'

    for char in s:
        if char in ILLEGAL_BASIC_STR_CHARS:
            if char in COMPACT_ESCAPES:
                if do_multiline and char == "\n":
                    result += "\n"
                else:
                    result += COMPACT_ESCAPES[char]
            else:
                result += "\\u" + hex(ord(char))[2:].rjust(4, "0")
        else:
            result += char

    if do_multiline:
        result += '"""'
    else:
        result += '"'

    return result

def is_aot(obj):
    #type(type[Any]) -> bool
    """Decides if an object behaves as an array of tables (i.e. a nonempty list
    of dicts)."""
    return bool(
        isinstance(obj, ARRAY_TYPES) and obj and all(isinstance(v, dict) for v in obj)
    )


def is_suitable_inline_table(obj, ctx):
    #type(dict, Context) -> bool
    """Use heuristics to decide if the inline-style representation is a good
    choice for a given table."""
    rendered_inline = "%s%s," % (ARRAY_INDENT, format_inline_table(obj, ctx))
    return len(rendered_inline) <= MAX_LINE_LENGTH and "\n" not in rendered_inline
