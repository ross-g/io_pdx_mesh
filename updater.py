"""
    IO PDX Mesh Python module.
    This is designed to allow tools to check if they are out of date or not and supply a download link to the latest.

    author : ross-g
"""

import json
import logging
import time
from datetime import date, datetime

# Py2, Py3 compatibility
try:
    from urllib.request import Request, URLError, urlopen
except ImportError:
    from urllib2 import Request, URLError, urlopen

from . import IO_PDX_SETTINGS, bl_info

UPDATER_LOG = logging.getLogger("io_pdx.updater")


""" ====================================================================================================================
    Helper functions.
========================================================================================================================
"""


class Github_API(object):
    """
    Handles connection to Githubs API to get some data on releases for this repository.
    """

    API_URL = "https://api.github.com"

    def __init__(self, owner, repo):
        self.api = self.API_URL
        self.owner = owner
        self.repo = repo
        self.args = {"owner": self.owner, "repo": self.repo, "api": self.api}

        self.AT_LATEST = False
        self.LATEST_VERSION = 0.0
        self.LATEST_URL = "https://github.com/{owner}/{repo}/releases/latest".format(**self.args)
        self.LATEST_NOTES = ""
        self.CURRENT_VERSION = float(".".join(map(str, bl_info["version"])))
        self.refresh()

    @staticmethod
    def get_data(url, time=1.0):
        req = Request(url)
        result = urlopen(req, timeout=time)
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
                release_list = self.get_data(releases_url)
                self.LATEST_RELEASE = release_list[0]
            except URLError as err:
                UPDATER_LOG.warning("Unable to check for update. ({})".format(err.reason))
                return
            except IndexError as err:
                UPDATER_LOG.warning("Found no releases during update check. ({})".format(err))
            except Exception as err:
                UPDATER_LOG.error("Failed during update check. ({})".format(err))
                return

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
            UPDATER_LOG.info("Checked for update. ({0:.4f} sec)".format(time.time() - start))

        else:
            # used cached release data in settings
            self.LATEST_VERSION = IO_PDX_SETTINGS.github_latest_version
            self.LATEST_URL = IO_PDX_SETTINGS.github_latest_url
            self.LATEST_NOTES = IO_PDX_SETTINGS.github_latest_notes

            UPDATER_LOG.info("Skipped update check. (already ran today)")

        self.AT_LATEST = self.CURRENT_VERSION == self.LATEST_VERSION


github = Github_API(owner=bl_info["author"], repo=bl_info["project_name"])
