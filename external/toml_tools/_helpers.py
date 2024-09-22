# -*- coding: utf-8 -*-
import os
import sys
import collections

# Iron Python 3 is on 3.4 (May 2023), but for future proofing's sake:
if sys.version_info < (3,7) or sys.implementation.name.lower() == 'ironpython':
    Dict = collections.OrderedDict
else:
    Dict = dict


class ReadOnlyDict(object):
    def __init__(self, *args, **kwargs):
        self._dict = Dict(*args, **kwargs)

    def __getitem__(self, key):
        return self._dict[key]
    
    def __contains__(self, key):
        return key in self._dict
    
    def keys(self):
        return self._dict.keys()
    
    def values(self):
        return self._dict.values()
    
    def items(self):
        return self._dict.items()
    
def stem(file_path):
    #type(str) -> str
    return os.path.splitext(os.path.basename(file_path))[0]


if sys.version_info < (3,6):
    def parse_int(s):
        #type(str) -> int
        return int(s.replace('_',''), base = 0)
    def parse_float(s):
        #type(str) -> float
        return float(s.replace('_',''))
else:
    # "Base 0 means to interpret the string exactly as an integer 
    # literal, so that the actual base is 2, 8, 10, or 16."
    # https://docs.python.org/2.7/library/functions.html#int
    parse_int = lambda s: int(s, base = 0)

    parse_float = float

try:
    # put long in name space as itself so we can import it
    # from elsewhere
    long = long #type: ignore
except NameError:
    long = int