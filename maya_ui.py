"""
    Paradox asset files, Maya import/export interface.
    
    author : ross-g
"""

import pymel.core as pmc
import maya.cmds as cmds
import maya.OpenMayaUI as omUI

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
    from PySide2 import __version__
except ImportError:
    from PySide import QtCore, QtGui
    from PySide import QtGui as QtWidgets
    from shiboken import wrapInstance
    from PySide import __version__
import os, re
import xml.etree.ElementTree as xml

import site
# site.addsitedir(os.path.join(os.environ['PG_SCRIPTS_ROOT'], 'Maya2017', 'python', 'external', 'site-packages'))
# from pg.CharMats import *


def get_mayamainwindow():
    pointer = omUI.MQtUtil.mainWindow()
    return wrapInstance(long(pointer), QtWidgets.QMainWindow)


""" ================================================================================================
    UI class for the import/export tool.
====================================================================================================
"""

class PDXmaya_ui(QtWidgets.QDialog):
    """
        Main tool window.
    """
    def __init__(self, parent=None):
        # parent to the Maya main window.
        if not parent:
            parent = get_mayamainwindow()

        super(PDXmaya_ui, self).__init__(parent)
        self.create_ui()

    def create_ui(self):
        # window properties
        self.setWindowTitle('PDX Maya Tools')
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(640, 480)
        if self.parent():
            parent_x = self.parent().x()
            parent_y = self.parent().y()
            self.setGeometry(parent_x+60, parent_y+220, self.width(), self.height())

        # populate window
        self.create_controls()
        self.create_signals()

    def create_controls(self):
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        self.setLayout(main_layout)

        # Import tab
        self.tab1 = QtWidgets.QWidget()
        tab1_layout = QtWidgets.QVBoxLayout()
        tab1_layout.setContentsMargins(5, 5, 5, 5)
        self.tab1.setLayout(tab1_layout)
        self.btn_import = QtWidgets.QPushButton('Import .mesh ...', self)
        self.btn_import.setToolTip('Select a .mesh file to import.')
        tab1_layout.addWidget(self.btn_import)

        # Export tab
        self.tab2 = tab_Export(parent=self)

        # construct tabs widget
        self.tabWidget = QtWidgets.QTabWidget()
        self.tabWidget.addTab(self.tab1, self.tr("Import"))
        self.tabWidget.addTab(self.tab2, self.tr("Export"))
        # add tabs widget to main layout
        main_layout.addWidget(self.tabWidget)

    def create_signals(self):
        # connect up controls
        self.btn_import.clicked.connect(self.on_openfile)
        self.tabWidget.currentChanged.connect(self.on_tabchange)

    @QtCore.Slot()
    def on_openfile(self):
        filename, filefilter = QtWidgets.QFileDialog.getOpenFileName(self, caption='Select .mesh', filter='PDX Mesh files (*.mesh)')
        if filename:
            self.import_mesh(filename)

    @QtCore.Slot()
    def import_mesh(self, filepath):
        if os.path.splitext(filepath)[1] == '.mesh':
            pass
            print "Loading asset from - '{}'".format(filepath)
        else:
            reply = QtWidgets.QMessageBox.warning(self,
                                                  'READ Error',
                                                  'Unable to read the file. The selected filepath ... '
                                                  '\n\n\t{}'
                                                  '\n\n ... is not a .mesh file!'.format(filepath),
                                                  QtWidgets.QMessageBox.Ok,
                                                  defaultButton=QtWidgets.QMessageBox.Ok)
            if reply == QtWidgets.QMessageBox.Ok:
                print "Could not read asset."

    @QtCore.Slot()
    def on_tabchange(self):
        pass


class tab_Export(QtWidgets.QWidget):
    """
        Tab for managing crowd models
    """

    def __init__(self, parent=None):
        super(tab_Export, self).__init__(parent)

        self.create_controls()
        self.connect_signals()

        self.popup = None       # reference for popup widget
        self.copied_data = None # reference for copy/paste data

    def create_controls(self):        
        # create controls
        lbl_engine = QtWidgets.QLabel('Game engine:')
        self.setup_engine = QtWidgets.QComboBox()
        
        self.list_materials = QtWidgets.QListWidget()
        # self.list_materials.setToolTip('<p><b>BOLD</b> materials are being used</p><p>Other materials are unassigned</p>')
        self.btn_mat_refresh = QtWidgets.QPushButton('Refresh', self)
        # self.btn_mat_refresh.setToolTip('Refresh the scene material list')
        self.btn_mat_create = QtWidgets.QPushButton('Create new ...', self)
        
        self.list_animations = QtWidgets.QListWidget()
        # self.list_materials.setToolTip('<p><b>BOLD</b> materials are being used</p><p>Other materials are unassigned</p>')
        self.btn_anim_refresh = QtWidgets.QPushButton('Refresh', self)
        # self.btn_anim_refresh.setToolTip('Refresh the scene material list')
        
        self.btn_export = QtWidgets.QPushButton('I\'m working on it...', self)
        self.btn_export.setToolTip('This isn\'t done yet')
        self.btn_export.setDisabled(True)

        # create layouts
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)

        left_layout = QtWidgets.QVBoxLayout()
        # left_layout.setSizePolicy()
        grp_scene = QtWidgets.QGroupBox('Scene')
        grp_scene_layout = QtWidgets.QVBoxLayout()
        grp_mats = QtWidgets.QGroupBox('Materials')
        grp_mats_layout = QtWidgets.QVBoxLayout()
        grp_mats_button_layout = QtWidgets.QHBoxLayout()
        grp_anims = QtWidgets.QGroupBox('Animations')
        grp_anims_layout = QtWidgets.QVBoxLayout()
        grp_anims_button_layout = QtWidgets.QHBoxLayout()

        grp_export = QtWidgets.QGroupBox('Export')
        grp_export_layout = QtWidgets.QVBoxLayout()

        for grp in [grp_scene, grp_mats, grp_anims, grp_export]:
            grp.setMaximumWidth(300)
            grp.setFont(QtGui.QFont('SansSerif', 8, QtGui.QFont.Bold))

        # add controls
        self.setLayout(main_layout)
        main_layout.addLayout(left_layout)
        
        left_layout.addWidget(grp_scene)
        grp_scene.setLayout(grp_scene_layout)
        grp_scene_layout.addWidget(lbl_engine)
        grp_scene_layout.addWidget(self.setup_engine)

        left_layout.addWidget(grp_mats)
        grp_mats.setLayout(grp_mats_layout)
        grp_mats_layout.addWidget(self.list_materials)
        grp_mats_layout.addLayout(grp_mats_button_layout)
        grp_mats_button_layout.addWidget(self.btn_mat_refresh)
        grp_mats_button_layout.addWidget(self.btn_mat_create)

        left_layout.addWidget(grp_anims)
        grp_anims.setLayout(grp_anims_layout)
        grp_anims_layout.addWidget(self.list_animations)
        grp_anims_layout.addWidget(self.btn_anim_refresh)

        main_layout.addWidget(grp_export)
        grp_export.setLayout(grp_export_layout)
        grp_export_layout.addWidget(self.btn_export)

    def connect_signals(self):
        pass



""" ================================================================================================
    Main entry point.
====================================================================================================
"""

def main():
    global pdx_tools

    try:
        pdx_tools.close()
        pdx_tools.deleteLater()
    except:
        pass

    pdx_tools = PDXmaya_ui()

    try:
        pdx_tools.show()
    except:
        pdx_tools.deleteLater()
        pdx_tools = None
        raise


if __name__ == '__main__':
    main()
