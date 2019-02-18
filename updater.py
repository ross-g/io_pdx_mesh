"""
    IO PDX Mesh Python module.
    This is designed to allow tools to check if they are out of date or not and supply a download link to the latest.

    author : ross-g
"""

import json
import time
# Py2, Py3 compatibility
try:
    from urllib.request import urlopen, Request, URLError
except ImportError:
    from urllib2 import urlopen, Request, URLError

from . import bl_info, IO_PDX_LOG


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

TIMEOUT = 1.0   # seconds
API_URL = 'https://api.github.com'
CURRENT_VERSION = float('.'.join(map(str, bl_info['version'])))
LATEST_RELEASE = {}
LATEST_VERSION = None
LATEST_URL = None

AT_LATEST = True


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


class Github_API(object):
    """
        Handles connection to Githubs API to get some data on releases for this repository.
    """

    def __init__(self):
        self.api = API_URL
        self.owner = bl_info['author']
        self.repo = bl_info['repo_name']
        self.args = {'owner': self.owner, 'repo': self.repo, 'api': self.api}

        self.refresh()

    @staticmethod
    def get_data(url, t):
        req = Request(url)
        result = urlopen(req, timeout=t)
        result_str = result.read()
        result.close()

        return json.JSONDecoder().decode(result_str.decode())

    def refresh(self):
        start = time.time()

        # get latest release data
        releases_url = '{api}/repos/{owner}/{repo}/releases'.format(**self.args)
        try:
            release_list = self.get_data(releases_url, TIMEOUT)
        except URLError as err:
            IO_PDX_LOG.error("Unable to check for update. ({})".format(err.reason))
            return

        global LATEST_RELEASE, LATEST_VERSION, LATEST_URL
        LATEST_RELEASE = release_list[0]
        LATEST_VERSION = float(release_list[0]['tag_name'])
        LATEST_URL = release_list[0]['assets'][0]['browser_download_url']

        global AT_LATEST
        AT_LATEST = CURRENT_VERSION == LATEST_VERSION

        IO_PDX_LOG.info("Checked for update. ({0:.4f} sec)".format(time.time() - start))


github_repo = Github_API()
