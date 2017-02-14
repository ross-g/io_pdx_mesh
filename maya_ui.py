"""
    Paradox asset files, Maya import/export interface.
    
    author : ross-g
"""

import os, sys
import webbrowser
import pymel.core as pmc
import maya.cmds as cmds
import maya.OpenMayaUI as omUI

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
except ImportError:
    from PySide import QtCore, QtGui
    from PySide import QtGui as QtWidgets
    from shiboken import wrapInstance

from maya_import_export import *


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
        self.popup = None  # reference for popup widget

    def create_ui(self):
        # window properties
        self.setWindowTitle('PDX Maya Tools')
        self.setWindowFlags(QtCore.Qt.Window)
        self.setFixedSize(550, 400)
        if self.parent():
            parent_x = self.parent().x()
            parent_y = self.parent().y()
            self.setGeometry(parent_x+60, parent_y+220, self.width(), self.height())

        # populate window
        self.create_menu()
        self.create_controls()
        self.create_signals()

    def create_menu(self):
        self.menubar = QtGui.QMenuBar()
        file_menu = self.menubar.addMenu('&File')
        help_menu = self.menubar.addMenu('&Help')

        file_import = QtGui.QAction('Import mesh ...', self)
        # file_import.setStatusTip('')
        file_import.triggered.connect(self.do_import)
        file_export = QtGui.QAction('Export mesh ...', self)
        file_export.setDisabled(True)
        # file_export.setStatusTip('')
        # file_export.triggered.connect(self.do_export)

        help_forum = QtGui.QAction('Paradox forums', self)
        help_forum.triggered.connect(
            lambda: webbrowser.open(
                'https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/')
        )
        help_code = QtGui.QAction('Source code', self)
        help_code.triggered.connect(
            lambda: webbrowser.open(
                'https://github.com/ross-g/io_pdx_mesh')
        )

        file_menu.addActions([file_import, file_export])
        help_menu.addActions([help_forum, help_code])

    def create_controls(self):
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        # Import tab
        # self.tab1 = tab_Import(parent=self)

        # Export tab
        # self.tab2 = tab_Export(parent=self)
        export_ctrls = tab_Export(parent=self)

        # construct tabs widget
        # self.tabWidget = QtWidgets.QTabWidget()
        # self.tabWidget.addTab(self.tab1, self.tr("Import"))
        # self.tabWidget.addTab(self.tab2, self.tr("Export"))

        # create menubar and add widgets to main layout
        main_layout.setMenuBar(self.menubar)
        main_layout.addWidget(export_ctrls)

    def create_signals(self):
        # connect up controls
        pass
        # self.tab1.btn_import.clicked.connect(self.on_openfile)
        # self.tabWidget.currentChanged.connect(self.on_tabchange)

    @QtCore.Slot()
    def do_import(self):
        filename, filefilter = QtWidgets.QFileDialog.getOpenFileName(caption='Select .mesh', filter='PDX Mesh files (*.mesh)')
        if filename and os.path.splitext(filename)[1] == '.mesh':
            self.import_mesh(filename)
        else:
            reply = QtWidgets.QMessageBox.warning(self, 'READ Error',
                                                  'Unable to read the file. The selected filepath ... '
                                                  '\n\n\t{}'
                                                  '\n\n ... is not a .mesh file!'.format(filename),
                                                  QtWidgets.QMessageBox.Ok,
                                                  defaultButton=QtWidgets.QMessageBox.Ok)
            if reply == QtWidgets.QMessageBox.Ok:
                print "[io_pdx_mesh] Nothing to import."

    @QtCore.Slot()
    def import_mesh(self, filepath):
        self.popup = tab_Import(filepath, parent=self)
        self.popup.show()

    @QtCore.Slot()
    def launch_webpage(self, address):
        pass


class tab_Import(QtWidgets.QWidget):

    def __init__(self, filepath, parent=None):
        super(tab_Import, self).__init__(parent)

        topleft = pdx_tools.window().frameGeometry().topLeft()
        self.move(topleft + QtCore.QPoint(5, 50))
        self.mesh_file = filepath

        self.create_controls()
        self.connect_signals()
        self.setWindowTitle('Import options')
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.MSWindowsFixedSizeDialogHint)

    def create_controls(self):
        # create controls
        lbl_filepath = QtWidgets.QLabel('Filename:  {}'.format(os.path.split(self.mesh_file)[-1]))
        self.chk_mesh = QtWidgets.QCheckBox('Mesh')
        self.chk_material = QtWidgets.QCheckBox('Material')
        self.chk_skeleton = QtWidgets.QCheckBox('Skeleton')
        self.chk_locators = QtWidgets.QCheckBox('Locators')
        self.btn_import = QtWidgets.QPushButton('Import ...', self)
        self.btn_import.setToolTip('Select a .mesh file to import.')
        self.btn_cancel = QtWidgets.QPushButton('Cancel', self)

        # create layouts
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        opts_layout = QtWidgets.QHBoxLayout()
        btn_layout = QtWidgets.QHBoxLayout()

        # add controls
        self.setLayout(main_layout)
        main_layout.addWidget(lbl_filepath)
        main_layout.addSpacing(10)
        for chk_box in [self.chk_mesh, self.chk_material, self.chk_skeleton, self.chk_locators]:
            opts_layout.addWidget(chk_box)
            chk_box.setChecked(True)
        main_layout.addLayout(opts_layout)
        main_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.btn_import)
        btn_layout.addWidget(self.btn_cancel)

    def connect_signals(self):
        self.btn_import.clicked.connect(self.import_mesh)
        self.btn_cancel.clicked.connect(self.close)

    def import_mesh(self):
        print "[io_pdx_mesh] Importing {}.".format(self.mesh_file)
        asset = pdx_data.read_meshfile(self.mesh_file)

        # create skeleton first
        for mesh in asset.meshes:
            if mesh.skeleton:
                create_Skeleton(mesh.skeleton)
        # create mesh
        for mesh in asset.meshes:
            create_Mesh(mesh, os.path.split(self.mesh_file)[0])

        # create locators
        if self.chk_locators.checkState():
            for loc in asset.locators:
                create_Locator(loc)

        self.close()


class tab_Export(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(tab_Export, self).__init__(parent)

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_engine = QtWidgets.QLabel('Game engine:')
        self.setup_engine = QtWidgets.QComboBox()
        self.setup_engine.addItems(['stellaris', 'hearts of iron 4', 'europa universalis 4', 'crusader kings 2'])
        lbl_fps = QtWidgets.QLabel('Animation fps:')
        self.setup_fps = QtWidgets.QDoubleSpinBox()
        self.setup_fps.setMinimum(0.0)
        self.setup_fps.setValue(15.0)

        self.list_materials = QtWidgets.QListWidget()
        self.btn_mat_refresh = QtWidgets.QPushButton('Refresh', self)
        self.btn_mat_create = QtWidgets.QPushButton('Create new ...', self)
        
        self.list_animations = QtWidgets.QListWidget()
        self.btn_anim_refresh = QtWidgets.QPushButton('Refresh', self)
        # self.btn_anim_refresh.setToolTip('Refresh the scene material list')
        
        lbl_exportwip = QtWidgets.QLabel('I\'m working on it...')
        lbl_exportwip.setToolTip('This isn\'t done yet')

        # create layouts
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setSpacing(5)
        grp_scene = QtWidgets.QGroupBox('Scene setup')
        grp_scene_layout = QtWidgets.QGridLayout()
        grp_scene_layout.setColumnStretch(1, 1)
        grp_scene_layout.setColumnStretch(2, 2)
        grp_scene_layout.setContentsMargins(5, 0, 5, 5)
        grp_scene_layout.setVerticalSpacing(5)
        grp_mats = QtWidgets.QGroupBox('Materials')
        grp_mats_layout = QtWidgets.QVBoxLayout()
        grp_mats_layout.setContentsMargins(4, 4, 4, 4)
        grp_mats_button_layout = QtWidgets.QHBoxLayout()
        grp_anims = QtWidgets.QGroupBox('Animations')
        grp_anims_layout = QtWidgets.QVBoxLayout()
        grp_anims_layout.setContentsMargins(4, 4, 4, 4)

        right_layout = QtWidgets.QVBoxLayout()
        grp_export = QtWidgets.QGroupBox('Export settings')
        grp_export_layout = QtWidgets.QVBoxLayout()

        for grp in [grp_scene, grp_mats, grp_anims, grp_export]:
            grp.setMinimumWidth(250)
            grp.setFont(QtGui.QFont('SansSerif', 8, QtGui.QFont.Bold))

        # add controls
        self.setLayout(main_layout)
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)

        left_layout.addWidget(grp_scene)
        grp_scene.setLayout(grp_scene_layout)
        grp_scene_layout.addWidget(lbl_engine, 1, 1)
        grp_scene_layout.addWidget(self.setup_engine, 1, 2)
        grp_scene_layout.addWidget(lbl_fps, 2, 1)
        grp_scene_layout.addWidget(self.setup_fps, 2, 2)

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

        right_layout.addWidget(grp_export)
        grp_export.setLayout(grp_export_layout)
        grp_export_layout.addWidget(lbl_exportwip)

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
