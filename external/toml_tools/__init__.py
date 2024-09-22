# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2021 Taneli Hukkinen
# Licensed to PSF under a Contributor Agreement.

__all__ = ("loads", "load", "TOMLDecodeError", "dumps", "dump")
__version__ = "2.0.0"  

from ._parser import TOMLDecodeError, load, loads
from ._writer import dump, dumps
from ._helpers import stem

# Pretend this exception was created here.
TOMLDecodeError.__module__ = __name__

