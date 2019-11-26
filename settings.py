"""
    IO PDX Mesh Python module.
    This is designed to allow tools to check if they are out of date or not and supply a download link to the latest.

    author : ross-g
"""

import os
import sys
import json
import errno
import os.path as path


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
                with open(filepath, 'w') as f:
                    pass
            except OSError as e:
                if e.errno != errno.EEXIST:
                    print(e)
        # default settings
        self.config_path = filepath
        self.app = sys.executable

    def __setattr__(self, name, value):
        super(PDXsettings, self).__setattr__(name, value)
        self.save_settings_file()

    def __getattribute__(self, attr):
        try:
            return super(PDXsettings, self).__getattribute__(attr)
        except AttributeError:
            return None

    def load_settings_file(self, filepath):
        settings_dict = json.load(open(filepath))
        self.config_path = filepath
        for k, v in settings_dict.items():
            setattr(self, k, v)

    def save_settings_file(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.__dict__, f, sort_keys=True, indent=4)
        except Exception as e:
            print(e)
