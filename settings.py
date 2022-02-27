"""
    IO PDX Mesh Python module.
    Simple settings object which writes to a JSON file on any value being set.

    author : ross-g
"""

import os
import sys
import json
import logging
import os.path as path

SETTINGS_LOG = logging.getLogger("io_pdx_settings")


""" ====================================================================================================================
    Module settings class.
========================================================================================================================
"""


class PDXsettings(object):
    def __init__(self, filepath):
        if path.exists(filepath):
            # read settings file
            self.load_settings_file(filepath)
        else:
            # new settings file
            try:
                os.makedirs(path.dirname(filepath))
                with open(filepath, "w") as _:
                    pass
            except OSError as err:
                SETTINGS_LOG.error("Failed creating new settings file", exc_info=True)

        # default settings
        self.config_path = filepath
        self.config_dir = path.dirname(filepath)
        self.app = sys.executable

    def __setattr__(self, name, value):
        result = super(PDXsettings, self).__setattr__(name, value)
        self.save_settings_file()
        return result

    def __getattr__(self, attr):
        try:
            return super(PDXsettings, self).__getattr__(attr)
        except AttributeError:
            return None

    def __delattr__(self, name):
        result = super(PDXsettings, self).__delattr__(name)
        self.save_settings_file()
        return result

    def load_settings_file(self, filepath):
        # default to empty settings dictionary
        settings_dict = {}
        with open(filepath) as f:
            try:
                settings_dict = json.load(f)
            except Exception:
                SETTINGS_LOG.error("Failed loading settings file", exc_info=True)

        self.config_path = filepath
        for k, v in settings_dict.items():
            setattr(self, k, v)

    def save_settings_file(self):
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.__dict__, f, sort_keys=True, indent=4)
        except Exception:
            SETTINGS_LOG.error("Failed saving settings file", exc_info=True)
