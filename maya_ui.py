"""
    Paradox asset files, Maya import/export interface.
    
    author : ross-g
"""

import os
import sys
import webbrowser
import inspect
import json
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


def h_line():        
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    return line


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
        self.popup = None                       # reference for popup widget
        self.settings = self.load_settings()    # settings from json
        self.create_ui()
        self.setStyleSheet(#'QWidget {font: 8pt "Sans Serif"}'
                           'QGroupBox {'
                           'border: 1px solid;'
                           'border-color: rgba(0, 0, 0, 64);'
                           'border-radius: 4px;'
                           'margin-top: 8px;'
                           'padding: 5px 2px 2px 2px;'
                           'background-color: rgb(78, 80, 82);'
                           '}'
                           'QGroupBox::title {'
                           'subcontrol-origin: margin;'
                           'subcontrol-position: top left;'
                           'left: 10px;'
                           '}'
                           )
        
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
        self.menubar = QtWidgets.QMenuBar()
        file_menu = self.menubar.addMenu('&File')
        tools_menu = self.menubar.addMenu('&Tools')
        help_menu = self.menubar.addMenu('&Help')

        # file menu
        file_import_mesh = QtWidgets.QAction('Import mesh ...', self)
        file_import_mesh.triggered.connect(self.do_import)
        # file_import_mesh.setStatusTip('')
        file_import_anim = QtWidgets.QAction('Import animation ...', self)
        # file_import_anim.triggered.connect(self.do_import_anim)
        file_import_anim.setDisabled(True)
        file_export = QtWidgets.QAction('Export mesh ...', self)
        file_export.setDisabled(True)

        # tools menu
        tool_edit_settings = QtWidgets.QAction('Edit Clausewitz settings', self)
        tool_edit_settings.setDisabled(True)
        tool_ignore_joints = QtWidgets.QAction('Ignore selected joints', self)
        tool_ignore_joints.setDisabled(True)
        tool_unignore_joints = QtWidgets.QAction('Un-ignore selected joints', self)
        tool_unignore_joints.setDisabled(True)

        # help menu
        help_forum = QtWidgets.QAction('Paradox forums', self)
        help_forum.triggered.connect(lambda: webbrowser.open(
            'https://forum.paradoxplaza.com/forum/index.php?forums/clausewitz-maya-exporter-modding-tool.935/')
        )
        help_code = QtWidgets.QAction('Source code', self)
        help_code.triggered.connect(lambda: webbrowser.open(
            'https://github.com/ross-g/io_pdx_mesh')
        )

        file_menu.addActions([file_import_mesh, file_import_anim])
        file_menu.addSeparator()
        file_menu.addActions([file_export])
        tools_menu.addActions([tool_edit_settings])
        tools_menu.addSeparator()
        tools_menu.addActions([tool_ignore_joints, tool_unignore_joints])
        help_menu.addActions([help_forum, help_code])

    def create_controls(self):
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        export_ctrls = export_controls(parent=self)

        # create menubar and add widgets to main layout
        main_layout.setMenuBar(self.menubar)
        main_layout.addWidget(export_ctrls)
        print self.settings

    def create_signals(self):
        # connect up controls
        pass

    @QtCore.Slot()
    def do_import(self):
        filename, filefilter = QtWidgets.QFileDialog.getOpenFileName(self, caption='Select .mesh',
                                                                     filter='PDX Mesh files (*.mesh)')
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

    def import_mesh(self, filepath):
        self.popup = import_popup(filepath, parent=self)
        self.popup.show()

    def load_settings(self):
        script_dir = os.path.dirname(inspect.getfile(inspect.currentframe()))

        settings_file = os.path.join(script_dir, 'clausewitz.json')
        with open(settings_file, 'rt') as f:
            settings = json.load(f)
            return settings


class import_popup(QtWidgets.QWidget):

    def __init__(self, filepath, parent=None):
        super(import_popup, self).__init__(parent)

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
        for chk_box in [self.chk_mesh, self.chk_skeleton, self.chk_locators]:
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

        try:
            import_file(self.mesh_file, imp_mesh=self.chk_mesh, imp_skel=self.chk_skeleton, imp_locs=self.chk_locators)
        except Exception, err:
            print "[io_pdx_mesh] Failed to import {}.".format(self.mesh_file)
            print err
            raise

        self.close()


class export_controls(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(export_controls, self).__init__(parent)

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        # materials
        self.list_materials = QtWidgets.QListWidget()
        self.btn_mat_refresh = QtWidgets.QPushButton('Refresh', self)
        self.btn_mat_edit = QtWidgets.QPushButton('Edit', self)
        self.btn_mat_create = QtWidgets.QPushButton('Create ...', self)
        # animations
        self.list_animations = QtWidgets.QListWidget()
        self.btn_anim_refresh = QtWidgets.QPushButton('Refresh', self)
        self.btn_anim_edit = QtWidgets.QPushButton('Edit', self)
        self.btn_anim_create = QtWidgets.QPushButton('Create ...', self)

        # settings
        lbl_engine = QtWidgets.QLabel('Game engine:')
        self.setup_engine = QtWidgets.QComboBox()
        self.setup_engine.addItems(self.parent().settings.keys())
        lbl_fps = QtWidgets.QLabel('Animation fps:')
        self.setup_fps = QtWidgets.QDoubleSpinBox()
        self.setup_fps.setMinimum(0.0)
        self.setup_fps.setValue(15.0)
        
        # export options
        self.chk_mesh = QtWidgets.QCheckBox('Export mesh')
        self.chk_skel = QtWidgets.QCheckBox('Export skeleton')
        self.chk_anim = QtWidgets.QCheckBox('Export animations')
        self.chk_merge_vtx = QtWidgets.QCheckBox('Merge vertices')
        self.chk_merge_obj = QtWidgets.QCheckBox('Merge objects')
        self.chk_create = QtWidgets.QCheckBox('Create .gfx and .asset')
        self.chk_preview = QtWidgets.QCheckBox('Preview on export')

        # output settings
        lbl_path = QtWidgets.QLabel('Output path:')
        self.txt_path = QtWidgets.QLineEdit()
        self.txt_path.setDisabled(True)
        self.btn_path = QtWidgets.QPushButton('...', self)
        self.btn_path.setMaximumWidth(20)
        self.btn_path.setMaximumHeight(18)
        lbl_file = QtWidgets.QLabel('Filename:')
        self.txt_file = QtWidgets.QLineEdit()
        self.txt_file.setPlaceholderText('placeholder_name.mesh')
        self.btn_export = QtWidgets.QPushButton('Export ...', self)

        # create layouts
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setSpacing(5)
        grp_mats = QtWidgets.QGroupBox('Materials')
        grp_mats_layout = QtWidgets.QVBoxLayout()
        grp_mats_layout.setContentsMargins(4, 4, 4, 4)
        grp_mats_button_layout = QtWidgets.QHBoxLayout()
        grp_anims = QtWidgets.QGroupBox('Animations')
        grp_anims_layout = QtWidgets.QVBoxLayout()
        grp_anims_layout.setContentsMargins(4, 4, 4, 4)
        grp_anims_button_layout = QtWidgets.QHBoxLayout()

        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setSpacing(5)
        grp_scene = QtWidgets.QGroupBox('Scene setup')
        grp_scene_layout = QtWidgets.QGridLayout()
        grp_scene_layout.setColumnStretch(1, 1)
        grp_scene_layout.setColumnStretch(2, 2)
        grp_scene_layout.setContentsMargins(4, 4, 4, 4)
        grp_scene_layout.setVerticalSpacing(5)
        grp_export = QtWidgets.QGroupBox('Export settings')
        grp_export_layout = QtWidgets.QVBoxLayout()
        grp_export_layout.setContentsMargins(4, 4, 4, 4)
        grp_export_fields_layout = QtWidgets.QGridLayout()
        grp_export_fields_layout.setVerticalSpacing(5)
        grp_export_fields_layout.setHorizontalSpacing(4)

        for grp in [grp_scene, grp_mats, grp_anims, grp_export]:
            grp.setMinimumWidth(250)
            # grp.setFont(QtGui.QFont('SansSerif', 8, QtGui.QFont.Bold))

        # add controls
        self.setLayout(main_layout)
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)

        left_layout.addWidget(grp_mats)
        grp_mats.setLayout(grp_mats_layout)
        grp_mats_layout.addWidget(self.list_materials)
        grp_mats_layout.addLayout(grp_mats_button_layout)
        grp_mats_button_layout.addWidget(self.btn_mat_refresh)
        grp_mats_button_layout.addWidget(self.btn_mat_edit)
        grp_mats_button_layout.addWidget(self.btn_mat_create)

        left_layout.addWidget(grp_anims)
        grp_anims.setLayout(grp_anims_layout)
        grp_anims_layout.addWidget(self.list_animations)
        grp_anims_layout.addLayout(grp_anims_button_layout)
        grp_anims_button_layout.addWidget(self.btn_anim_refresh)
        grp_anims_button_layout.addWidget(self.btn_anim_edit)
        grp_anims_button_layout.addWidget(self.btn_anim_create)

        right_layout.addWidget(grp_scene)
        grp_scene.setLayout(grp_scene_layout)
        grp_scene_layout.addWidget(lbl_engine, 1, 1)
        grp_scene_layout.addWidget(self.setup_engine, 1, 2)
        grp_scene_layout.addWidget(lbl_fps, 2, 1)
        grp_scene_layout.addWidget(self.setup_fps, 2, 2)

        right_layout.addWidget(grp_export)
        grp_export.setLayout(grp_export_layout)
        grp_export_layout.addWidget(self.chk_mesh)
        grp_export_layout.addWidget(self.chk_skel)
        grp_export_layout.addWidget(self.chk_anim)
        grp_export_layout.addWidget(h_line())
        grp_export_layout.addWidget(self.chk_merge_vtx)
        grp_export_layout.addWidget(self.chk_merge_obj)
        grp_export_layout.addWidget(h_line())
        grp_export_layout.addWidget(self.chk_create)
        grp_export_layout.addWidget(self.chk_preview)
        grp_export_layout.addWidget(h_line())
        grp_export_layout.addLayout(grp_export_fields_layout)
        grp_export_fields_layout.addWidget(lbl_path, 1, 1)
        grp_export_fields_layout.addWidget(self.txt_path, 1, 2)
        grp_export_fields_layout.addWidget(self.btn_path, 1, 3)
        grp_export_fields_layout.addWidget(lbl_file, 2, 1)
        grp_export_fields_layout.addWidget(self.txt_file, 2, 2, 1, 2)
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
