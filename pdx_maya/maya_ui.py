"""
    Paradox asset files, Maya import/export interface.

    author : ross-g
"""

from __future__ import print_function

import os
import sys
import webbrowser
from imp import reload
from textwrap import wrap
from functools import partial

import pymel.core as pmc
import maya.OpenMayaUI as omUI

try:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance
except ImportError:
    from PySide import QtCore, QtGui
    from PySide import QtGui as QtWidgets
    from shiboken import wrapInstance

from .. import bl_info, IO_PDX_LOG, IO_PDX_SETTINGS, ENGINE_SETTINGS
from ..pdx_data import PDXData
from ..updater import github

try:
    from . import maya_import_export

    reload(maya_import_export)
    from .maya_import_export import (
        create_shader,
        export_animfile,
        export_meshfile,
        get_animation_clips,
        get_mesh_index,
        import_animfile,
        import_meshfile,
        list_scene_materials,
        list_scene_pdx_meshes,
        list_scene_rootbones,
        PDX_ANIMATION,
        PDX_SHADER,
        remove_animation_clip,
        set_ignore_joints,
        set_local_axis_display,
        set_mesh_index,
    )
except Exception as err:
    IO_PDX_LOG.error(err)
    raise

# Py2, Py3 compatibility (Maya doesn't yet use Py3, this is purely to stop flake8 complaining)
if sys.version_info >= (3, 0):
    xrange = range
    long = int


""" ====================================================================================================================
    Variables and Helper functions.
========================================================================================================================
"""


def get_maya_mainWindow():
    pointer = omUI.MQtUtil.mainWindow()
    return wrapInstance(long(pointer), QtWidgets.QMainWindow)


def set_widget_icon(widget, icon_name):
    """ to visually browse for Mayas internal icon set
            import maya.app.general.resourceBrowser as resourceBrowser
            resBrowser = resourceBrowser.resourceBrowser()
            path = resBrowser.run()
        generate the full list with
            cmds.resourceManager()
    """
    try:
        widget.setIcon(QtGui.QIcon(":/{}".format(icon_name)))
    except Exception as err:
        IO_PDX_LOG.error(err)


class HLine(QtWidgets.QFrame):
    def __init__(self):
        super(HLine, self).__init__()
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setFrameShadow(QtWidgets.QFrame.Sunken)


class CollapsingGroupBox(QtWidgets.QGroupBox):
    def __init__(self, title, parent=None, layout=None, **kwargs):
        super(CollapsingGroupBox, self).__init__(title, parent, **kwargs)
        self.parent = parent
        self.line = HLine()

        layout = layout or QtWidgets.QGridLayout
        self.inner = QtWidgets.QWidget(self.parent)
        self.inner.setLayout(layout())

        self.setStyleSheet(
            "QGroupBox {"
            "border: 1px solid;"
            "border-color: rgba(0, 0, 0, 64);"
            "border-radius: 6px;"
            "background-color: rgb(78, 80, 82);"
            "font-weight: bold;"
            "}"
            "QGroupBox::title {"
            "subcontrol-origin: margin;"
            "left: 6px;"
            "top: 4px;"
            "}"
        )

        self.setCheckable(True)
        self.setChecked(True)
        self.setFlat(True)

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(4, 18, 4, 4)
        self.layout().setSpacing(0)
        self.layout().addWidget(self.line)
        self.layout().addWidget(self.inner)

        # configure checkable groupbox as show/hide panel
        self.toggled.connect(self.on_toggle)

    def on_toggle(self, state):
        self.inner.setVisible(state)
        self.line.setVisible(state)
        if state:
            self.layout().setContentsMargins(4, 18, 4, 4)
        else:
            self.layout().setContentsMargins(4, 0, 4, 4)

        QtCore.QCoreApplication.processEvents()
        self.parent.resize(self.parent.layout().sizeHint())

    def sizeHint(self):
        if self.isChecked():
            return super(CollapsingGroupBox, self).sizeHint()
        else:
            return QtCore.QSize(self.width(), 22)


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDXUI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        # parent to the Maya main window.
        parent = parent or get_maya_mainWindow()

        super(PDXUI, self).__init__(parent)
        self.popup = None  # type: QtWidgets.QWidget
        self.settings = None  # type: QtCore.QSettings
        self.create_ui()
        self.read_ui_settings()

    def create_ui(self):
        # window properties
        self.setWindowTitle("PDX Maya Tools")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)

        # populate and connect controls
        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # File panel
        grp_File = CollapsingGroupBox("File", self)
        grp_File.setObjectName("grpFile")

        lbl_Import = QtWidgets.QLabel("Import:", self)
        self.import_mesh = btn_ImportMesh = QtWidgets.QPushButton("Load mesh ...", self)
        set_widget_icon(btn_ImportMesh, "out_polyCube.png")
        self.import_anim = btn_ImportAnim = QtWidgets.QPushButton("Load anim ...", self)
        set_widget_icon(btn_ImportAnim, "out_renderLayer.png")
        lbl_Export = QtWidgets.QLabel("Export:", self)
        self.export_mesh = btn_ExportMesh = QtWidgets.QPushButton("Save mesh ...", self)
        set_widget_icon(btn_ExportMesh, "out_polyCube.png")
        self.export_anim = btn_ExportAnim = QtWidgets.QPushButton("Save anim ...", self)
        set_widget_icon(btn_ExportAnim, "out_renderLayer.png")

        grp_File.inner.layout().addWidget(lbl_Import, 0, 0, 1, 2)
        grp_File.inner.layout().addWidget(btn_ImportMesh, 1, 0)
        grp_File.inner.layout().addWidget(btn_ImportAnim, 1, 1)
        grp_File.inner.layout().addWidget(lbl_Export, 2, 0, 1, 2)
        grp_File.inner.layout().addWidget(btn_ExportMesh, 3, 0)
        grp_File.inner.layout().addWidget(btn_ExportAnim, 3, 1)

        # Tools panel
        grp_Tools = CollapsingGroupBox("Tools", self)
        grp_Tools.setObjectName("grpTools")

        lbl_Materials = QtWidgets.QLabel("PDX materials:", self)
        self.material_create_popup = btn_MaterialCreate = QtWidgets.QPushButton("Create", self)
        set_widget_icon(btn_MaterialCreate, "blinn.svg")
        self.material_edit_popup = btn_MaterialEdit = QtWidgets.QPushButton("Edit", self)
        set_widget_icon(btn_MaterialEdit, "hypershadeIcon.png")
        lbl_Bones = QtWidgets.QLabel("PDX bones:", self)
        self.ignore_bone = btn_BoneIgnore = QtWidgets.QPushButton("Ignore bones", self)
        set_widget_icon(btn_BoneIgnore, "joint.svg")
        self.unignore_bone = btn_BoneUnignore = QtWidgets.QPushButton("Unignore bones", self)
        set_widget_icon(btn_BoneUnignore, "joint.svg")
        lbl_Meshes = QtWidgets.QLabel("PDX meshes:", self)
        self.mesh_index_popup = btn_MeshOrder = QtWidgets.QPushButton("Set mesh order ...", self)
        set_widget_icon(btn_MeshOrder, "sortName.png")

        grp_Tools.inner.layout().addWidget(lbl_Materials, 0, 0, 1, 2)
        grp_Tools.inner.layout().addWidget(btn_MaterialCreate, 1, 0)
        grp_Tools.inner.layout().addWidget(btn_MaterialEdit, 1, 1)
        grp_Tools.inner.layout().addWidget(lbl_Bones, 2, 0, 1, 2)
        grp_Tools.inner.layout().addWidget(btn_BoneIgnore, 3, 0)
        grp_Tools.inner.layout().addWidget(btn_BoneUnignore, 3, 1)
        grp_Tools.inner.layout().addWidget(lbl_Meshes, 4, 0, 1, 2)
        grp_Tools.inner.layout().addWidget(btn_MeshOrder, 5, 0, 1, 2)

        # Display panel
        grp_Display = CollapsingGroupBox("Display", self)
        grp_Display.setObjectName("grpDisplay")

        lbl_Display = QtWidgets.QLabel("Display local axes:", self)
        self.show_axis_bones = btn_ShowBones = QtWidgets.QPushButton("Show on bones", self)
        set_widget_icon(btn_ShowBones, "out_joint.png")
        self.hide_axis_bones = btn_HideBones = QtWidgets.QPushButton("Hide on bones", self)
        set_widget_icon(btn_HideBones, "out_joint.png")
        self.show_axis_locators = btn_ShowLocators = QtWidgets.QPushButton("Show on locators", self)
        set_widget_icon(btn_ShowLocators, "out_holder.png")
        self.hide_axis_locators = btn_HideLocators = QtWidgets.QPushButton("Hide on locators", self)
        set_widget_icon(btn_HideLocators, "out_holder.png")

        grp_Display.inner.layout().addWidget(lbl_Display, 0, 0, 1, 2)
        grp_Display.inner.layout().addWidget(btn_ShowBones, 1, 0)
        grp_Display.inner.layout().addWidget(btn_HideBones, 1, 1)
        grp_Display.inner.layout().addWidget(btn_ShowLocators, 2, 0)
        grp_Display.inner.layout().addWidget(btn_HideLocators, 2, 1)

        # Setup panel
        grp_Setup = CollapsingGroupBox("Setup", self)
        grp_Setup.setObjectName("grpSetup")

        lbl_SetupEngine = QtWidgets.QLabel("Engine:", self)
        ddl_EngineSelect = QtWidgets.QComboBox(self)
        lbl_SetupAnimation = QtWidgets.QLabel("Animation:", self)
        spn_AnimationFps = QtWidgets.QDoubleSpinBox(self)

        grp_Setup.inner.layout().addWidget(lbl_SetupEngine, 0, 0)
        grp_Setup.inner.layout().addWidget(ddl_EngineSelect, 0, 1)
        grp_Setup.inner.layout().addWidget(lbl_SetupAnimation, 1, 0)
        grp_Setup.inner.layout().addWidget(spn_AnimationFps, 1, 1)
        grp_Setup.inner.layout().setColumnStretch(1, 1)

        # Info panel
        grp_Info = CollapsingGroupBox("Info", self)
        grp_Info.setObjectName("grpInfo")

        lbl_Current = QtWidgets.QLabel("current version: {}".format(github.CURRENT_VERSION), self)
        self.update_version, self.about_popup = None, None
        if github.AT_LATEST is False:  # update info appears if we aren't at the latest tag version
            self.update_version = btn_UpdateVersion = QtWidgets.QPushButton(
                "NEW UPDATE {}".format(github.LATEST_VERSION), self
            )
            set_widget_icon(btn_UpdateVersion, "SE_FavoriteStar.png")
            self.about_popup = btn_AboutVersion = QtWidgets.QPushButton("About", self)
            set_widget_icon(btn_AboutVersion, "info.png")

        # Help sub panel
        grp_Help = CollapsingGroupBox("Help", self)
        grp_Help.setObjectName("grpHelp")

        self.help_wiki = btn_HelpWiki = QtWidgets.QPushButton("Tool Wiki", self)
        set_widget_icon(btn_HelpWiki, "help.png")
        self.help_forum = btn_HelpForum = QtWidgets.QPushButton("Paradox forums", self)
        set_widget_icon(btn_HelpForum, "help.png")
        self.help_source = btn_HelpSource = QtWidgets.QPushButton("Source code", self)
        set_widget_icon(btn_HelpSource, "help.png")

        grp_Help.inner.layout().addWidget(btn_HelpWiki, 0, 0)
        grp_Help.inner.layout().addWidget(btn_HelpForum, 1, 0)
        grp_Help.inner.layout().addWidget(btn_HelpSource, 2, 0)
        grp_Help.inner.layout().setContentsMargins(0, 0, 0, 0)
        grp_Help.inner.layout().setSpacing(4)

        grp_Info.inner.layout().addWidget(lbl_Current, 0, 0, 1, 2)
        if github.AT_LATEST is False:
            grp_Info.inner.layout().addWidget(btn_UpdateVersion, 1, 0)
            grp_Info.inner.layout().addWidget(btn_AboutVersion, 1, 1)
            grp_Info.inner.layout().setColumnStretch(0, 1)
        grp_Info.inner.layout().addWidget(grp_Help, 3, 0, 1, 2)
        grp_Info.inner.layout().setRowMinimumHeight(2, 4)

        # main layout
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        self.layout().setContentsMargins(4, 4, 4, 4)
        self.layout().setSpacing(6)
        for group_widget in [grp_File, grp_Tools, grp_Display, grp_Setup, grp_Info]:
            group_widget.inner.layout().setContentsMargins(0, 0, 0, 0)
            group_widget.inner.layout().setSpacing(4)
            self.layout().addWidget(group_widget)

        self.layout().addStretch()

        for btn in self.findChildren(QtWidgets.QPushButton):
            btn.setMaximumHeight(22)

    def connect_signals(self):
        self.import_mesh.clicked.connect(partial(print, "import_mesh"))
        self.import_anim.clicked.connect(partial(print, "import_anim"))
        self.export_mesh.clicked.connect(partial(print, "export_mesh"))
        self.export_anim.clicked.connect(partial(print, "export_anim"))

        self.material_create_popup.clicked.connect(self.create_material)
        self.material_edit_popup.clicked.connect(partial(print, "material_edit_popup"))
        self.ignore_bone.clicked.connect(partial(set_ignore_joints, True))
        self.unignore_bone.clicked.connect(partial(set_ignore_joints, False))
        self.mesh_index_popup.clicked.connect(self.edit_mesh_order)

        self.show_axis_bones.clicked.connect(partial(set_local_axis_display, True, object_type="joint"))
        self.hide_axis_bones.clicked.connect(partial(set_local_axis_display, False, object_type="joint"))
        self.show_axis_locators.clicked.connect(partial(set_local_axis_display, True, object_type="locator"))
        self.hide_axis_locators.clicked.connect(partial(set_local_axis_display, False, object_type="locator"))

        if self.update_version:
            self.update_version.clicked.connect(partial(webbrowser.open, str(github.LATEST_URL)))
        if self.about_popup:
            self.about_popup.clicked.connect(self.show_update_notes)
        self.help_wiki.clicked.connect(partial(webbrowser.open, bl_info["wiki_url"]))
        self.help_forum.clicked.connect(partial(webbrowser.open, bl_info["forum_url"]))
        self.help_source.clicked.connect(partial(webbrowser.open, bl_info["project_url"]))

    def closeEvent(self, event):
        self.write_ui_settings()
        event.accept()

    def read_ui_settings(self):
        self.settings = QtCore.QSettings(
            QtCore.QSettings.NativeFormat, QtCore.QSettings.UserScope, "IO_PDX_MESH", "MAYA"
        )
        # restore groupbox panels expand state
        for grp in self.findChildren(QtWidgets.QGroupBox):
            state = True
            if self.settings.contains("ui/isChecked_{0}".format(grp.objectName())):
                state = self.settings.value("ui/isChecked_{0}".format(grp.objectName())) == "true"
            grp.setChecked(state)
        # restore dialog size, position
        self.restoreGeometry(self.settings.value("ui/geometry", ""))

    def write_ui_settings(self):
        # store groupbox panels expand state
        for grp in self.findChildren(QtWidgets.QGroupBox):
            self.settings.setValue("ui/isChecked_{0}".format(grp.objectName()), grp.isChecked())
        # store dialog size, position
        self.settings.setValue("ui/geometry", self.saveGeometry())

    @QtCore.Slot()
    def create_material(self):
        if self.popup:
            self.popup.close()
        self.popup = material_popup(parent=self)
        self.popup.show()

    @QtCore.Slot()
    def edit_mesh_order(self):
        if self.popup:
            self.popup.close()
        self.popup = meshindex_popup(parent=self)
        self.popup.show()

    @QtCore.Slot()
    def show_update_notes(self):
        msg_text = github.LATEST_NOTES

        # split text into multiple label rows if it's wider than the panel
        txt_lines = []
        for line in msg_text.splitlines():
            txt_lines.extend(wrap(line, 450 / 6))
            txt_lines.append("")

        QtWidgets.QMessageBox.information(self, bl_info["name"], "\n".join(txt_lines))


class PDXmaya_ui(QtWidgets.QDialog):
    """
        Main tool window.
    """

    def __init__(self, parent=None):
        # parent to the Maya main window.
        if not parent:
            parent = get_maya_mainWindow()

        super(PDXmaya_ui, self).__init__(parent)
        self.popup = None  # reference for popup widget
        self.create_ui()
        self.setStyleSheet(
            "QGroupBox {"
            "border: 1px solid;"
            "border-color: rgba(0, 0, 0, 64);"
            "border-radius: 4px;"
            "margin-top: 8px;"
            "padding: 5px 2px 2px 2px;"
            "background-color: rgb(78, 80, 82);"
            "}"
            "QGroupBox::title {"
            "subcontrol-origin: margin;"
            "subcontrol-position: top left;"
            "left: 10px;"
            "}"
        )

    def create_ui(self):
        # window properties
        self.setWindowTitle("PDX Maya Tools")
        self.setWindowFlags(QtCore.Qt.Window)
        if self.parent():
            parent_x = self.parent().x()
            parent_y = self.parent().y()
            self.setGeometry(parent_x + 60, parent_y + 220, self.width(), self.height())

        # populate window
        self.create_menu()
        self.create_controls()
        self.create_signals()
        self.refresh_gui()

    def create_menu(self):
        self.menubar = QtWidgets.QMenuBar()
        file_menu = self.menubar.addMenu("&File")
        tools_menu = self.menubar.addMenu("&Tools")
        tools_menu.setTearOffEnabled(True)
        help_menu = self.menubar.addMenu("&Help")

        # file menu
        file_import = QtWidgets.QAction("Import", self)
        file_import.setDisabled(True)

        file_import_mesh = QtWidgets.QAction("Load mesh ...", self)
        file_import_mesh.triggered.connect(self.do_import_mesh)
        set_widget_icon(file_import_mesh, "out_polyCube.png")

        file_import_anim = QtWidgets.QAction("Load animation ...", self)
        file_import_anim.triggered.connect(self.do_import_anim)
        set_widget_icon(file_import_anim, "out_renderLayer.png")

        file_export = QtWidgets.QAction("Export", self)
        file_export.setDisabled(True)

        file_export_mesh = QtWidgets.QAction("Save mesh ...", self)
        file_export_mesh.triggered.connect(lambda: self.do_export_mesh(select_path=True))
        set_widget_icon(file_export_mesh, "out_polyCube.png")

        file_export_anim = QtWidgets.QAction("Save animation ...", self)
        file_export_anim.triggered.connect(lambda: self.do_export_anim(select_path=True))
        set_widget_icon(file_export_anim, "out_renderLayer.png")

        # tools menu
        tool_ignore_joints = QtWidgets.QAction("Ignore selected joints", self)
        tool_ignore_joints.triggered.connect(lambda: set_ignore_joints(True))

        tool_unignore_joints = QtWidgets.QAction("Un-ignore selected joints", self)
        tool_unignore_joints.triggered.connect(lambda: set_ignore_joints(False))

        tool_show_jnt_localaxes = QtWidgets.QAction("Show all joint axes", self)
        tool_show_jnt_localaxes.triggered.connect(lambda: set_local_axis_display(True, object_type="joint"))
        set_widget_icon(tool_show_jnt_localaxes, "out_joint.png")

        tool_hide_jnt_localaxes = QtWidgets.QAction("Hide all joint axes", self)
        tool_hide_jnt_localaxes.triggered.connect(lambda: set_local_axis_display(False, object_type="joint"))

        tool_show_loc_localaxes = QtWidgets.QAction("Show all locator axes", self)
        tool_show_loc_localaxes.triggered.connect(lambda: set_local_axis_display(True, object_type="locator"))
        set_widget_icon(tool_show_loc_localaxes, "out_holder.png")

        tool_hide_loc_localaxes = QtWidgets.QAction("Hide all locator axes", self)
        tool_hide_loc_localaxes.triggered.connect(lambda: set_local_axis_display(False, object_type="locator"))

        tool_edit_mesh_order = QtWidgets.QAction("Set mesh order", self)
        tool_edit_mesh_order.triggered.connect(self.edit_mesh_order)
        set_widget_icon(tool_edit_mesh_order, "sortName.png")

        # help menu
        help_version = QtWidgets.QAction("current version {}".format(github.CURRENT_VERSION), self)
        help_version.setDisabled(True)

        help_wiki = QtWidgets.QAction("Tool Wiki", self)
        help_wiki.triggered.connect(lambda: webbrowser.open(bl_info["wiki_url"]))
        set_widget_icon(help_wiki, "help.png")

        help_forum = QtWidgets.QAction("Paradox forums", self)
        help_forum.triggered.connect(lambda: webbrowser.open(bl_info["wiki_url"]))
        set_widget_icon(help_forum, "help.png")

        help_code = QtWidgets.QAction("Source code", self)
        help_code.triggered.connect(lambda: webbrowser.open(bl_info["project_url"]))
        set_widget_icon(help_code, "help.png")

        # new version sub-menu
        help_update = QtWidgets.QMenu("NEW UPDATE {}".format(github.LATEST_VERSION), self)
        set_widget_icon(help_update, "SE_FavoriteStar.png")

        help_download = QtWidgets.QAction("Download", self)
        help_download.triggered.connect(lambda: webbrowser.open(str(github.LATEST_URL)))
        set_widget_icon(help_download, "advancedSettings.png")

        help_about = QtWidgets.QAction("About", self)
        help_about.triggered.connect(self.show_update_notes)
        set_widget_icon(help_about, "info.png")

        # add all actions and separators to menus
        file_menu.addActions([file_import, file_import_mesh, file_import_anim])
        file_menu.addSeparator()
        file_menu.addActions([file_export, file_export_mesh, file_export_anim])

        tools_menu.addActions([tool_ignore_joints, tool_unignore_joints])
        tools_menu.addSeparator()
        tools_menu.addActions([tool_show_jnt_localaxes, tool_hide_jnt_localaxes])
        tools_menu.addActions([tool_show_loc_localaxes, tool_hide_loc_localaxes])
        tools_menu.addSeparator()
        tools_menu.addActions([tool_edit_mesh_order])

        help_menu.addActions([help_version])
        if github.AT_LATEST is False:  # update info appears if we aren't at the latest tag version
            help_menu.addMenu(help_update)
            help_update.addActions([help_download, help_about])
            bold_fnt = help_update.menuAction().font()
            bold_fnt.setBold(True)
            help_update.menuAction().setFont(bold_fnt)
        help_menu.addSeparator()
        help_menu.addActions([help_wiki, help_forum, help_code])

    def create_controls(self):
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        # create all of the main controls
        self.export_ctrls = export_controls(parent=self)

        # create menubar and add widgets to main layout
        main_layout.setMenuBar(self.menubar)
        main_layout.addWidget(self.export_ctrls)

    def create_signals(self):
        # connect up controls
        pass

    def refresh_gui(self):
        # call any gui refresh functions here
        self.export_ctrls.refresh_mat_list()
        self.export_ctrls.refresh_anim_list()

    @QtCore.Slot()
    def show_update_notes(self):
        msg_text = github.LATEST_NOTES

        # split text into multiple label rows if it's wider than the panel
        txt_lines = []
        for line in msg_text.splitlines():
            txt_lines.extend(wrap(line, 450 / 6))
            txt_lines.append("")

        QtWidgets.QMessageBox.information(self, bl_info["name"], "\n".join(txt_lines))

    @QtCore.Slot()
    def do_import_mesh(self):
        last_dir = IO_PDX_SETTINGS.last_import_mesh or ""
        filepath, filefilter = QtWidgets.QFileDialog.getOpenFileName(
            self, caption="Select .mesh file", dir=last_dir, filter="PDX Mesh files (*.mesh)"
        )

        if filepath != "":
            filepath = os.path.abspath(filepath)
            if os.path.splitext(filepath)[1] == ".mesh":
                if self.popup:
                    self.popup.close()
                self.popup = import_popup(filepath, parent=self)
                self.popup.show()
                IO_PDX_SETTINGS.last_import_mesh = filepath
            else:
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "READ ERROR",
                    "Unable to read selected file. The filepath ... "
                    "\n\n\t{0}"
                    "\n ... is not a .mesh file!".format(filepath),
                    QtWidgets.QMessageBox.Ok,
                    defaultButton=QtWidgets.QMessageBox.Ok,
                )
                if reply == QtWidgets.QMessageBox.Ok:
                    IO_PDX_LOG.info("Nothing to import.")

    @QtCore.Slot()
    def do_import_anim(self):
        last_dir = IO_PDX_SETTINGS.last_import_anim or ""
        filepath, filefilter = QtWidgets.QFileDialog.getOpenFileName(
            self, caption="Select .anim file", dir=last_dir, filter="PDX Animation files (*.anim)"
        )

        if filepath != "":
            filepath = os.path.abspath(filepath)
            if os.path.splitext(filepath)[1] == ".anim":
                if self.popup:
                    self.popup.close()
                self.popup = import_popup(filepath, parent=self)
                self.popup.show()
                IO_PDX_SETTINGS.last_import_anim = filepath
            else:
                reply = QtWidgets.QMessageBox.warning(
                    self,
                    "READ ERROR",
                    "Unable to read selected file. The filepath ... "
                    "\n\n\t{0}"
                    "\n ... is not a .anim file!".format(filepath),
                    QtWidgets.QMessageBox.Ok,
                    defaultButton=QtWidgets.QMessageBox.Ok,
                )
                if reply == QtWidgets.QMessageBox.Ok:
                    IO_PDX_LOG.info("Nothing to import.")

    @QtCore.Slot()
    def do_export_mesh(self, select_path=False):
        export_opts = self.export_ctrls
        filepath, filename = export_opts.get_export_path()

        # validate directory
        if filepath == "" or select_path:
            last_dir = IO_PDX_SETTINGS.last_export_mesh or ""
            export_opts.select_export_path(filter_dir=last_dir, filter_text="PDX Mesh files (*.mesh)")
            filepath, filename = export_opts.get_export_path()
        if not os.path.isdir(filepath):
            reply = QtWidgets.QMessageBox.warning(
                self,
                "WRITE ERROR",
                "Unable to export content. The filepath ... "
                "\n\n\t{0}"
                "\n ... is not a valid location!".format(filepath),
                QtWidgets.QMessageBox.Ok,
                defaultButton=QtWidgets.QMessageBox.Ok,
            )
            if reply == QtWidgets.QMessageBox.Ok:
                IO_PDX_LOG.info("Nothing to export.")
            return

        # determine the output mesh path
        name, ext = os.path.splitext(filename)
        if not ext == ".mesh":
            filename = name + ".mesh"
        meshpath = os.path.join(os.path.abspath(filepath), filename)

        try:
            export_meshfile(
                meshpath,
                exp_mesh=export_opts.chk_mesh.isChecked(),
                exp_skel=export_opts.chk_skel.isChecked(),
                exp_locs=export_opts.chk_locs.isChecked(),
                merge_verts=export_opts.chk_merge_vtx.isChecked(),
                exp_selected=export_opts.chk_selected.isChecked(),
                progress_fn=MayaProgress,
            )
            QtWidgets.QMessageBox.information(self, "SUCCESS", "Mesh export finished!\n\n{0}".format(meshpath))
            IO_PDX_SETTINGS.last_export_mesh = meshpath
        except Exception as err:
            IO_PDX_LOG.warning("FAILED to export {0}".format(meshpath))
            IO_PDX_LOG.error(err)
            QtWidgets.QMessageBox.critical(self, "FAILURE", "Mesh export failed!\n\n{0}".format(err))
            MayaProgress.finished()
            raise

    @QtCore.Slot()
    def do_export_anim(self, select_path=False):
        export_opts = self.export_ctrls
        filepath, filename = export_opts.get_export_path()

        # validate directory
        if filepath == "" or select_path:
            last_dir = IO_PDX_SETTINGS.last_export_anim or ""
            export_opts.select_export_path(filter_dir=last_dir, filter_text="PDX Animation files (*.anim)")
            filepath, filename = export_opts.get_export_path()
        if not os.path.isdir(filepath):
            reply = QtWidgets.QMessageBox.warning(
                self,
                "WRITE ERROR",
                "Unable to export content. The filepath ... "
                "\n\n\t{0}"
                "\n ... is not a valid location!".format(filepath),
                QtWidgets.QMessageBox.Ok,
                defaultButton=QtWidgets.QMessageBox.Ok,
            )
            if reply == QtWidgets.QMessageBox.Ok:
                IO_PDX_LOG.info("Nothing to export.")
            return

        # determine the output anim path
        name, ext = os.path.splitext(filename)
        if not ext == ".anim":
            filename = name + ".anim"
        animpath = os.path.join(os.path.abspath(filepath), filename)

        try:
            export_animfile(
                animpath,
                timestart=pmc.playbackOptions(query=True, minTime=True),
                timeend=pmc.playbackOptions(query=True, maxTime=True),
                progress_fn=MayaProgress,
            )
            QtWidgets.QMessageBox.information(self, "SUCCESS", "Animation export finished!\n\n{0}".format(animpath))
            IO_PDX_SETTINGS.last_export_anim = animpath
        except Exception as err:
            IO_PDX_LOG.warning("FAILED to export {0}".format(animpath))
            IO_PDX_LOG.error(err)
            QtWidgets.QMessageBox.critical(self, "FAILURE", "Animation export failed!\n\n{0}".format(err))
            MayaProgress.finished()
            raise

    def edit_mesh_order(self):
        if self.popup:
            self.popup.close()
        self.popup = meshindex_popup(parent=self)
        self.popup.show()


class export_controls(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(export_controls, self).__init__(parent)

        self.parent = parent
        self.popup = None  # reference for popup widget

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        # materials
        self.list_materials = QtWidgets.QListWidget()
        self.btn_mat_create = QtWidgets.QPushButton("Create ...", self)
        self.btn_mat_edit = QtWidgets.QPushButton("Edit", self)
        self.btn_mat_delete = QtWidgets.QPushButton("Delete", self)
        self.btn_mat_refresh = QtWidgets.QPushButton("Refresh", self)
        # animations
        self.list_animations = QtWidgets.QListWidget()
        self.list_animations.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.btn_anim_create = QtWidgets.QPushButton("Create ...", self)
        self.btn_anim_edit = QtWidgets.QPushButton("Edit", self)
        self.btn_anim_delete = QtWidgets.QPushButton("Delete", self)
        self.btn_anim_refresh = QtWidgets.QPushButton("Refresh", self)

        # settings
        lbl_engine = QtWidgets.QLabel("Game engine:")
        self.setup_engine = QtWidgets.QComboBox()
        self.setup_engine.addItems(ENGINE_SETTINGS.keys())
        lbl_fps = QtWidgets.QLabel("Animation fps:")
        self.setup_fps = QtWidgets.QDoubleSpinBox()  # TODO: this should set Maya prefs and read/load from presets
        self.setup_fps.setMinimum(0.0)
        self.setup_fps.setValue(15.0)

        # export options
        self.chk_mesh = QtWidgets.QCheckBox("Export mesh")
        self.chk_skel = QtWidgets.QCheckBox("Export skeleton")
        self.chk_locs = QtWidgets.QCheckBox("Export locators")
        self.chk_merge_vtx = QtWidgets.QCheckBox("Merge vertices")
        self.chk_merge_obj = QtWidgets.QCheckBox("Merge objects")
        self.chk_selected = QtWidgets.QCheckBox("Selected Only")
        self.chk_timeline = QtWidgets.QCheckBox("Export current timeline")
        self.chk_animation = QtWidgets.QCheckBox("Export all selected animations")
        self.chk_create_extra = QtWidgets.QCheckBox("Create .gfx and .asset")
        for ctrl in [self.chk_mesh, self.chk_skel, self.chk_locs, self.chk_merge_vtx]:
            ctrl.setChecked(True)

        # output settings
        lbl_path = QtWidgets.QLabel("Output path:")
        self.txt_path = QtWidgets.QLineEdit()
        self.btn_path = QtWidgets.QPushButton("...", self)
        self.btn_path.setMaximumWidth(20)
        self.btn_path.setMaximumHeight(18)
        lbl_file = QtWidgets.QLabel("Filename:")
        self.txt_file = QtWidgets.QLineEdit()
        self.txt_file.setPlaceholderText("placeholder_name.mesh")
        self.btn_export = QtWidgets.QPushButton("Export ...", self)

        # TODO: re-enable these once supported
        self.btn_anim_create.setDisabled(True)
        self.btn_anim_edit.setDisabled(True)
        self.btn_anim_delete.setDisabled(True)
        self.btn_anim_refresh.setDisabled(True)
        self.chk_create_extra.setDisabled(True)
        self.chk_merge_obj.setDisabled(True)
        self.chk_timeline.setDisabled(True)
        self.chk_animation.setDisabled(True)

        # create layouts
        main_layout = QtWidgets.QHBoxLayout()
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(5, 5, 5, 5)

        left_layout = QtWidgets.QVBoxLayout()
        left_layout.setSpacing(5)
        grp_mats = QtWidgets.QGroupBox("Materials")
        grp_mats_layout = QtWidgets.QVBoxLayout()
        grp_mats_layout.setContentsMargins(4, 4, 4, 4)
        grp_mats_button_layout = QtWidgets.QHBoxLayout()
        grp_anims = QtWidgets.QGroupBox("Animations")
        grp_anims_layout = QtWidgets.QVBoxLayout()
        grp_anims_layout.setContentsMargins(4, 4, 4, 4)
        grp_anims_button_layout = QtWidgets.QHBoxLayout()

        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setSpacing(5)
        grp_scene = QtWidgets.QGroupBox("Scene setup")
        grp_scene_layout = QtWidgets.QGridLayout()
        grp_scene_layout.setColumnStretch(1, 1)
        grp_scene_layout.setColumnStretch(2, 2)
        grp_scene_layout.setContentsMargins(4, 4, 4, 4)
        grp_scene_layout.setVerticalSpacing(5)
        grp_export = QtWidgets.QGroupBox("Export settings")
        grp_export_layout = QtWidgets.QGridLayout()
        grp_export_layout.setVerticalSpacing(5)
        grp_export_layout.setHorizontalSpacing(4)
        grp_export_layout.setContentsMargins(4, 4, 4, 4)
        grp_export_fields_layout = QtWidgets.QGridLayout()
        grp_export_fields_layout.setVerticalSpacing(5)
        grp_export_fields_layout.setHorizontalSpacing(4)

        for grp in [grp_mats, grp_anims, grp_scene, grp_export]:
            grp.setMinimumWidth(250)

        # add controls
        self.setLayout(main_layout)
        main_layout.addLayout(left_layout)
        main_layout.addLayout(right_layout)

        left_layout.addWidget(grp_mats)
        grp_mats.setLayout(grp_mats_layout)
        grp_mats_layout.addWidget(self.list_materials)
        grp_mats_layout.addLayout(grp_mats_button_layout)
        grp_mats_button_layout.addWidget(self.btn_mat_create)
        grp_mats_button_layout.addWidget(self.btn_mat_edit)
        grp_mats_button_layout.addWidget(self.btn_mat_delete)
        grp_mats_button_layout.addWidget(self.btn_mat_refresh)
        grp_mats_button_layout.setSpacing(3)

        left_layout.addWidget(grp_anims)
        grp_anims.setLayout(grp_anims_layout)
        grp_anims_layout.addWidget(self.list_animations)
        grp_anims_layout.addLayout(grp_anims_button_layout)
        grp_anims_button_layout.addWidget(self.btn_anim_create)
        grp_anims_button_layout.addWidget(self.btn_anim_edit)
        grp_anims_button_layout.addWidget(self.btn_anim_delete)
        grp_anims_button_layout.addWidget(self.btn_anim_refresh)
        grp_anims_button_layout.setSpacing(3)

        right_layout.addWidget(grp_scene)
        grp_scene.setLayout(grp_scene_layout)
        grp_scene_layout.addWidget(lbl_engine, 1, 1)
        grp_scene_layout.addWidget(self.setup_engine, 1, 2)
        grp_scene_layout.addWidget(lbl_fps, 2, 1)
        grp_scene_layout.addWidget(self.setup_fps, 2, 2)

        right_layout.addWidget(grp_export)
        grp_export.setLayout(grp_export_layout)
        grp_export_layout.addWidget(self.chk_mesh, 1, 1)
        grp_export_layout.addWidget(self.chk_skel, 2, 1)
        grp_export_layout.addWidget(self.chk_locs, 3, 1)
        grp_export_layout.addWidget(self.chk_merge_vtx, 1, 2)
        grp_export_layout.addWidget(self.chk_merge_obj, 2, 2)
        grp_export_layout.addWidget(self.chk_selected, 3, 2)
        grp_export_layout.addWidget(HLine(), 4, 1, 1, 2)
        grp_export_layout.addWidget(self.chk_timeline, 5, 1, 1, 2)
        grp_export_layout.addWidget(self.chk_animation, 6, 1, 1, 2)
        grp_export_layout.addWidget(HLine(), 7, 1, 1, 2)
        grp_export_layout.addWidget(self.chk_create_extra, 8, 1, 1, 2)
        grp_export_layout.addWidget(HLine(), 9, 1, 1, 2)
        grp_export_layout.addLayout(grp_export_fields_layout, 10, 1, 1, 2)
        grp_export_fields_layout.addWidget(lbl_path, 1, 1)
        grp_export_fields_layout.addWidget(self.txt_path, 1, 2)
        grp_export_fields_layout.addWidget(self.btn_path, 1, 3)
        grp_export_fields_layout.addWidget(lbl_file, 2, 1)
        grp_export_fields_layout.addWidget(self.txt_file, 2, 2, 1, 2)
        grp_export_layout.addWidget(self.btn_export, 11, 1, 1, 2)

    def connect_signals(self):
        self.list_materials.itemClicked.connect(self.select_mat)
        self.list_materials.itemDoubleClicked.connect(self.edit_selected_mat)
        self.btn_mat_create.clicked.connect(self.create_new_mat)
        self.btn_mat_edit.clicked.connect(self.edit_selected_mat)
        self.btn_mat_delete.clicked.connect(self.delete_selected_mat)
        self.btn_mat_refresh.clicked.connect(self.refresh_mat_list)

        self.list_animations.itemDoubleClicked.connect(self.select_anim)
        self.btn_anim_create.clicked.connect(self.create_new_anim)
        self.btn_anim_edit.clicked.connect(self.edit_selected_anim)
        self.btn_anim_delete.clicked.connect(self.delete_selected_anim)
        self.btn_anim_refresh.clicked.connect(self.refresh_anim_list)

        self.btn_path.clicked.connect(self.select_export_path)
        self.btn_export.clicked.connect(self.do_export)

    def create_new_mat(self):
        if self.popup:
            self.popup.close()
        self.popup = material_popup(parent=self.parent)
        self.popup.show()

    def edit_selected_mat(self):
        if self.list_materials.selectedItems():
            selected_mat = self.list_materials.selectedItems()[0]
            if self.popup:
                self.popup.close()
            self.popup = material_popup(material=selected_mat, parent=self.parent)
            self.popup.show()

    def delete_selected_mat(self):
        if self.list_materials.selectedItems():
            selected_mat = self.list_materials.selectedItems()[0]
            material_node = pmc.PyNode(selected_mat.text())
            pmc.delete(material_node)
            self.refresh_mat_list()

    def refresh_mat_list(self):
        self.list_materials.clearSelection()
        self.list_materials.clear()
        pdx_scenemats = [mat.name() for mat in list_scene_materials() if hasattr(mat, PDX_SHADER)]

        for mat in pdx_scenemats:
            list_item = QtWidgets.QListWidgetItem()
            list_item.setText(mat)
            self.list_materials.insertItem(self.list_materials.count(), list_item)

        self.list_materials.sortItems()

    def select_mat(self, curr_sel):
        try:
            pmc.select(curr_sel.text())
        except pmc.MayaNodeError:
            self.refresh_mat_list()

        self.list_animations.sortItems()

    def create_new_anim(self):
        self.refresh_anim_list()

    def edit_selected_anim(self):
        self.refresh_anim_list()

    def delete_selected_anim(self):
        pdx_scene_rootbones = [bone for bone in list_scene_rootbones() if hasattr(bone, PDX_ANIMATION)]

        if pdx_scene_rootbones:
            for selected_clip in self.list_animations.selectedItems():
                name, start, end = selected_clip.data(QtCore.Qt.UserRole)
                remove_animation_clip([pdx_scene_rootbones[0]], name)

        self.refresh_anim_list()

    def refresh_anim_list(self):
        self.list_animations.clearSelection()
        self.list_animations.clear()
        pdx_scene_rootbones = [bone for bone in list_scene_rootbones() if hasattr(bone, PDX_ANIMATION)]

        pdx_sceneanims = []
        if pdx_scene_rootbones:
            # allow only one root bone with the animation property
            pdx_sceneanims = get_animation_clips([pdx_scene_rootbones[0]])

        for clip in pdx_sceneanims:
            list_item = QtWidgets.QListWidgetItem()
            list_item.setText("{name}  -  {start},{end}".format(**clip._asdict()))
            list_item.setData(QtCore.Qt.UserRole, clip)
            self.list_animations.insertItem(self.list_animations.count(), list_item)

    def select_anim(self, curr_sel):
        if self.list_animations.selectedItems():
            selected_clip = self.list_animations.selectedItems()[0]
            name, start, end = selected_clip.data(QtCore.Qt.UserRole)

            pmc.playbackOptions(edit=True, minTime=start)
            pmc.playbackOptions(edit=True, maxTime=end)

    def select_export_path(self, filter_dir="", filter_text="All files (*.*)"):
        filepath, filefilter = QtWidgets.QFileDialog.getSaveFileName(
            self, caption="Select export folder", dir=filter_dir, filter=filter_text
        )
        path, name = os.path.split(filepath)

        if filepath != "" and os.path.isdir(path):
            self.txt_path.setText(path)
            self.txt_file.setText(name)
            self.txt_file.setToolTip(filepath)

    def get_export_path(self):
        filepath = self.txt_path.text()
        filename = self.txt_file.text() or self.txt_file.placeholderText()
        return filepath, filename

    def do_export(self):
        if self.chk_mesh.isChecked() or self.chk_skel.isChecked() or self.chk_locs.isChecked():
            self.parent.do_export_mesh()

        if self.chk_timeline.isChecked() or self.chk_animation.isChecked():
            pass


class import_popup(QtWidgets.QWidget):
    def __init__(self, filepath, parent=None):
        super(import_popup, self).__init__(parent)

        self.pdx_file = filepath
        self.pdx_type = os.path.splitext(filepath)[1]
        self.parent = parent

        self.setWindowTitle("Import options")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.MSWindowsFixedSizeDialogHint)
        self.setFixedSize(275, 100)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_filepath = QtWidgets.QLabel("Filename:  {0}".format(os.path.split(self.pdx_file)[-1]))
        self.btn_import = QtWidgets.QPushButton("Import ...", self)
        self.btn_import.setToolTip("Select a {0} file to import.".format(self.pdx_type))
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)
        # mesh specific controls
        self.chk_mesh = QtWidgets.QCheckBox("Mesh")
        self.chk_skel = QtWidgets.QCheckBox("Skeleton")
        self.chk_locs = QtWidgets.QCheckBox("Locators")
        # anim specific controls
        lbl_starttime = QtWidgets.QLabel("Start frame:")
        lbl_starttime.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.spn_start = QtWidgets.QSpinBox()
        self.spn_start.setMaximum(9999)
        self.spn_start.setMinimum(-9999)
        self.spn_start.setMaximumWidth(50)
        self.spn_start.setValue(1)
        self.chk_wipekeys = QtWidgets.QCheckBox("Wipe existing animation")

        # create layouts
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        opts_layout = QtWidgets.QHBoxLayout()
        btn_layout = QtWidgets.QHBoxLayout()

        # add controls
        self.setLayout(main_layout)
        main_layout.addWidget(lbl_filepath)
        main_layout.addSpacing(5)
        # add mode specific import option controls
        if self.pdx_type == ".mesh":
            for chk_box in [self.chk_mesh, self.chk_skel, self.chk_locs]:
                opts_layout.addWidget(chk_box)
                chk_box.setChecked(True)
        elif self.pdx_type == ".anim":
            for qt_control in [self.chk_wipekeys, lbl_starttime, self.spn_start]:
                opts_layout.addWidget(qt_control)
        main_layout.addLayout(opts_layout)
        main_layout.addSpacing(10)
        main_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.btn_import)
        btn_layout.addWidget(self.btn_cancel)

    def connect_signals(self):
        if self.pdx_type == ".mesh":
            self.btn_import.clicked.connect(self.import_mesh)
        elif self.pdx_type == ".anim":
            self.btn_import.clicked.connect(self.import_anim)
        self.btn_cancel.clicked.connect(self.close)

    def import_mesh(self):
        try:
            self.close()
            import_meshfile(
                self.pdx_file,
                imp_mesh=self.chk_mesh.isChecked(),
                imp_skel=self.chk_skel.isChecked(),
                imp_locs=self.chk_locs.isChecked(),
                progress_fn=MayaProgress,
            )
            self.parent.refresh_gui()
        except Exception as err:
            IO_PDX_LOG.warning("FAILED to import {0}".format(self.pdx_file))
            IO_PDX_LOG.error(err)
            QtWidgets.QMessageBox.critical(self, "FAILURE", "Mesh import failed!\n\n{0}".format(err))
            MayaProgress.finished()
            self.close()
            raise

        self.close()

    def import_anim(self):
        try:
            self.close()
            import_animfile(
                self.pdx_file, timestart=self.spn_start.value(), progress_fn=MayaProgress,
            )
            self.parent.refresh_gui()
        except Exception as err:
            IO_PDX_LOG.warning("FAILED to import {0}".format(self.pdx_file))
            IO_PDX_LOG.error(err)
            QtWidgets.QMessageBox.critical(self, "FAILURE", "Animation import failed!\n\n{0}".format(err))
            MayaProgress.finished()
            self.close()
            raise

        self.close()


class material_popup(QtWidgets.QWidget):
    def __init__(self, material=None, parent=None):
        super(material_popup, self).__init__(parent)

        self.parent = parent
        self.material = material

        self.setWindowTitle("PDX material")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.MSWindowsFixedSizeDialogHint)
        self.setFixedSize(300, 100)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        self.mat_name = QtWidgets.QLineEdit()
        self.mat_name.setObjectName("Name")
        self.mat_type = QtWidgets.QComboBox()
        self.mat_type.setObjectName("Shader")
        self.mat_type.setEditable(True)
        self.mat_type.addItems(self.get_shader_presets())
        self.mat_type.setCurrentIndex(-1)
        self.btn_okay = QtWidgets.QPushButton("Okay", self)
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)

        # create layouts
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        form_layout = QtWidgets.QFormLayout()
        btn_layout = QtWidgets.QHBoxLayout()

        # add controls
        self.setLayout(main_layout)
        main_layout.addLayout(form_layout)
        for ctrl in [self.mat_name, self.mat_type]:
            form_layout.addRow(ctrl.objectName(), ctrl)
        main_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.btn_okay)
        btn_layout.addWidget(self.btn_cancel)

        # editing a selected material
        if self.material:
            mat_name = self.material.text()
            mat_node = pmc.PyNode(mat_name)
            mat_shader = getattr(mat_node, PDX_SHADER).get()

            self.mat_name.setText(mat_name)
            if self.mat_type.findText(mat_shader) != -1:
                self.mat_type.setCurrentIndex(self.mat_type.findText(mat_shader))
            else:
                self.mat_type.setEditText(mat_shader)

            self.btn_okay.setText("Okay")
        # creating a new material
        else:
            self.btn_okay.setText("Save")

    def connect_signals(self):
        self.btn_okay.clicked.connect(self.save_mat)
        self.btn_cancel.clicked.connect(self.close)

    def get_shader_presets(self):
        sel_engine = self.parent.export_ctrls.setup_engine.currentText()
        return ENGINE_SETTINGS[sel_engine]["material"]

    def save_mat(self):
        # editing a selected material
        if self.material:
            mat_name = self.material.text()
            mat_node = pmc.PyNode(mat_name)

            pmc.rename(mat_node, self.mat_name.text())
            getattr(mat_node, PDX_SHADER).set(self.mat_type.currentText())
        # creating a new material
        else:
            mat_name = self.mat_name.text()
            mat_type = self.mat_type.currentText()
            # create a mock PDXData object for convenience here to pass to the create_shader function
            mat_pdx = type("Material", (PDXData, object), {"shader": [mat_type]})

            create_shader(mat_pdx, mat_name, None)

        self.parent.export_ctrls.refresh_mat_list()
        self.close()


class meshindex_popup(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(meshindex_popup, self).__init__(parent)

        self.parent = parent

        self.setWindowTitle("PDX mesh index")
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.MSWindowsFixedSizeDialogHint)
        self.setFixedSize(200, 200)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_help = QtWidgets.QLabel("Drag/drop meshes to reorder")
        self.list_meshes = QtWidgets.QListWidget()
        self.list_meshes.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_meshes.defaultDropAction = QtCore.Qt.MoveAction

        self.btn_okay = QtWidgets.QPushButton("Save", self)
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)

        # create layouts
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(5, 5, 5, 5)
        btn_layout = QtWidgets.QHBoxLayout()

        # add controls
        self.setLayout(main_layout)
        main_layout.addWidget(lbl_help)
        main_layout.addWidget(self.list_meshes)
        main_layout.addLayout(btn_layout)
        btn_layout.addWidget(self.btn_okay)
        btn_layout.addWidget(self.btn_cancel)

        # populate list
        self.list_meshes.clearSelection()
        self.list_meshes.clear()
        pdx_scenemeshes = [mesh for mesh in list_scene_pdx_meshes()]
        pdx_scenemeshes.sort(key=lambda mesh: get_mesh_index(mesh))

        for mesh in pdx_scenemeshes:
            list_item = QtWidgets.QListWidgetItem()
            list_item.setText(mesh.name())
            list_item.setData(QtCore.Qt.UserRole, mesh.longName())
            self.list_meshes.insertItem(self.list_meshes.count(), list_item)

    def connect_signals(self):
        self.btn_okay.clicked.connect(self.set_meshindex)
        self.btn_cancel.clicked.connect(self.close)

    def set_meshindex(self):
        IO_PDX_LOG.info("Setting mesh index order...")
        for i in xrange(self.list_meshes.count()):
            item = self.list_meshes.item(i)
            maya_mesh = pmc.PyNode(item.data(QtCore.Qt.UserRole))  # type: pmc.nt.Mesh
            set_mesh_index(maya_mesh, i)
            IO_PDX_LOG.info("\t{} - {}".format(maya_mesh.name(), i))

        self.close()


class MayaProgress(object):
    """
        Wrapping the Maya progress window for convenience.
    """

    def __init__(self, title, max_value):
        super(MayaProgress, self).__init__()
        pmc.progressWindow(title=title, progress=0, min=0, max=max_value, status="", isInterruptable=False)

    def __del__(self):
        self.finished()

    @staticmethod
    def update(step, status):
        progress = pmc.progressWindow(query=True, progress=True)
        max_value = pmc.progressWindow(query=True, max=True)
        if progress >= max_value:
            pmc.progressWindow(edit=True, progress=0)
        pmc.progressWindow(edit=True, step=step, status=status)

    @staticmethod
    def finished():
        pmc.progressWindow(endProgress=True)


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def main():
    IO_PDX_LOG.info("Launching Maya UI.")
    global pdx_tools

    try:
        pdx_tools.close()
        pdx_tools.deleteLater()
    except Exception:
        pass

    pdx_tools = PDXUI()

    try:
        pdx_tools.show()
    except Exception:
        pdx_tools.deleteLater()
        pdx_tools = None
        raise


if __name__ == "__main__":
    main()
