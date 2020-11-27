"""
    IO PDX Mesh Python module.
    This is designed to allow tools to check if they are out of date or not and supply a download link to the latest.

    author : ross-g
"""

import json
import time
from datetime import datetime, date

# Py2, Py3 compatibility
try:
    from urllib.request import urlopen, Request, URLError
except ImportError:
    from urllib2 import urlopen, Request, URLError

from . import bl_info, IO_PDX_LOG, IO_PDX_SETTINGS


""" ====================================================================================================================
    Variables.
========================================================================================================================
"""

TIMEOUT = 1.0  # seconds
API_URL = "https://api.github.com"


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


class Github_API(object):
    """
        Handles connection to Githubs API to get some data on releases for this repository.
    """

    def __init__(self):
        self.LATEST_VERSION = None
        self.LATEST_URL = None
        self.AT_LATEST = None
        self.CURRENT_VERSION = float(".".join(map(str, bl_info["version"])))

        self.api = API_URL
        self.owner = bl_info["author"]
        self.repo = bl_info["project_name"]
        self.args = {"owner": self.owner, "repo": self.repo, "api": self.api}
        self.refresh()

    @staticmethod
    def get_data(url, t):
        req = Request(url)
        result = urlopen(req, timeout=t)
        result_str = result.read()
        result.close()

        return json.JSONDecoder().decode(result_str.decode())

    def refresh(self, force=False):
        recheck = True

        # only check for updates once per day
        last_check_date = IO_PDX_SETTINGS.last_update_check
        if last_check_date is not None:
            recheck = date.today() > datetime.strptime(last_check_date, "%Y-%m-%d").date()

        if recheck or force:
            start = time.time()

            # get latest release data
            releases_url = "{api}/repos/{owner}/{repo}/releases".format(**self.args)
            try:
                release_list = self.get_data(releases_url, TIMEOUT)
            except URLError as err:
                IO_PDX_LOG.warning("Unable to check for update. ({})".format(err.reason))
                return
            except Exception as err:
                IO_PDX_LOG.error("Failed on check for update. ({})".format(err))
                return
            self.LATEST_RELEASE = release_list[0]

            latest = release_list[0]

            # store data
            self.LATEST_VERSION = float(latest["tag_name"])
            self.LATEST_URL = latest["assets"][0]["browser_download_url"]
            self.LATEST_NOTES = "{0}\r\nRelease version: {1}\r\n{2}".format(
                latest["published_at"].split("T")[0], latest["tag_name"], latest["body"]
            )

            # cache data to settings
            IO_PDX_SETTINGS.github_latest_version = self.LATEST_VERSION
            IO_PDX_SETTINGS.github_latest_url = self.LATEST_URL
            IO_PDX_SETTINGS.github_latest_notes = self.LATEST_NOTES

            IO_PDX_SETTINGS.last_update_check = str(date.today())
            IO_PDX_LOG.info("Checked for update. ({0:.4f} sec)".format(time.time() - start))

        else:
            # used cached release data in settings
            self.LATEST_VERSION = IO_PDX_SETTINGS.github_latest_version
            self.LATEST_URL = IO_PDX_SETTINGS.github_latest_url
            self.LATEST_NOTES = IO_PDX_SETTINGS.github_latest_notes

            IO_PDX_LOG.info("Skipped update check. (already ran today)")

        self.AT_LATEST = self.CURRENT_VERSION == self.LATEST_VERSION


github = Github_API()
