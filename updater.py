"""
    IO PDX Mesh Python module.
    .

    author : ross-g
"""

import os
import urllib.request
import json

from . import bl_info


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

API_URL = 'https://api.github.com'
RELEASE_DATA = {}


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


def get_repo_url():
    return '{api}/repos/{author}/{repo_name}'.format(api=API_URL, **bl_info)


def get_releases_url():
    return '{api}/repos/{author}/{repo_name}/releases'.format(api=API_URL, **bl_info)


def get_releases_data():
    global RELEASE_DATA

    request = urllib.request.Request(get_releases_url())
    result = urllib.request.urlopen(request)
    result_str = result.read()
    result.close()

    RELEASE_DATA = json.JSONDecoder().decode(result_str.decode())


get_releases_data()
