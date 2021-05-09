"""
    Paradox asset files, Maya import/export interface.

    author : ross-g
"""

from __future__ import print_function, unicode_literals

import os
import sys
import webbrowser
from imp import reload
from textwrap import wrap
from functools import partial

import maya.cmds as cmds
import pymel.core as pmc
import maya.OpenMayaUI as OpenMayaUI
import maya.api.OpenMaya as OpenMayaAPI

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
        PDX_ANIMATION,
        PDX_SHADER,
        create_shader,
        export_animfile,
        export_meshfile,
        get_animation_clips,
        get_animation_fps,
        get_mesh_index,
        import_animfile,
        import_meshfile,
        list_scene_pdx_materials,
        list_scene_pdx_meshes,
        list_scene_rootbones,
        remove_animation_clip,
        set_animation_fps,
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
    Helper functions/classes.
========================================================================================================================
"""


def get_maya_mainWindow():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
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
        widget.setIcon(QtGui.QIcon(":/{0}".format(icon_name)))
    except Exception as err:
        IO_PDX_LOG.error(err)


def move_dialog_onscreen(dialog):
    QtCore.QCoreApplication.processEvents()
    screen = QtWidgets.QDesktopWidget().availableGeometry(dialog)
    frame = dialog.frameGeometry()
    if not screen.contains(frame, proper=True):
        x_pos, y_pos = frame.x(), frame.y()

        if not screen.intersects(frame):
            # entirely offscreen, reset
            dialog.move(screen.x(), screen.y())
        else:
            # partially offscreen, move
            if frame.left() < screen.left():
                x_pos += (screen.left() - frame.left())
            if frame.right() > screen.right():
                x_pos += (screen.right() - frame.right())
            if frame.top() < screen.top():
                y_pos += (screen.top() - frame.top())
            if frame.bottom() > screen.bottom():
                y_pos += (screen.bottom() - frame.bottom())

            dialog.move(x_pos, y_pos)


def HLine():
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.HLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    return line


def VLine():
    line = QtWidgets.QFrame()
    line.setFrameShape(QtWidgets.QFrame.VLine)
    line.setFrameShadow(QtWidgets.QFrame.Sunken)
    return line


class CollapsingGroupBox(QtWidgets.QGroupBox):
    def __init__(self, title, parent=None, layout=None, **kwargs):
        super(CollapsingGroupBox, self).__init__(title, parent, **kwargs)
        self.parent = parent
        self.line = HLine()

        self.setCheckable(True)
        self.setChecked(True)
        self.setFlat(True)
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
            "QGroupBox::indicator:checked {"
            "image: url(:/arrowDown.png);"
            "}"
            "QGroupBox::indicator:unchecked {"
            "image: url(:/arrowRight.png);"
            "}"
        )

        # setup inner widget, defaulting to grid layout
        self.inner = QtWidgets.QWidget(self.parent)
        layout = layout or QtWidgets.QGridLayout()
        self.inner.setLayout(layout)

        # setup layout to contain inner widget
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
        if not self.isChecked():
            return QtCore.QSize(self.width(), 22)
        else:
            return self.layout().sizeHint()


class CustomFileDialog(QtWidgets.QFileDialog):
    def __init__(self, *args, **kwargs):
        super(CustomFileDialog, self).__init__(*args, **kwargs)
        self.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)
        self.setViewMode(QtWidgets.QFileDialog.Detail)

    def addCustomOptions(self, widget):
        self.optionsWidget = widget
        # adjust QFileDialog layout to append custom options
        box = QtWidgets.QVBoxLayout()
        box.addWidget(self.optionsWidget)
        box.addStretch(1)

        self.layout().addWidget(VLine(), 0, 3, 4, 1)
        self.layout().addLayout(box, 0, 4, 4, 1)

    def selectedOptions(self):
        def widget_values(widget):
            ctrl_values = {}
            for ctrl in widget.children():
                name = ctrl.objectName()
                value = None
                if isinstance(ctrl, QtWidgets.QLineEdit):
                    value = ctrl.text()
                elif isinstance(ctrl, QtWidgets.QComboBox):
                    value = ctrl.currentText()
                elif isinstance(ctrl, QtWidgets.QCheckBox):
                    value = ctrl.isChecked()
                elif isinstance(ctrl, QtWidgets.QSpinBox):
                    value = ctrl.value()

                # store this controls value against its identifier
                if name is not None and value is not None:
                    ctrl_values[name] = value
                # check all children of this control
                ctrl_values.update(widget_values(ctrl))

            return ctrl_values

        options = widget_values(self.optionsWidget)

        return options

    @classmethod
    def runPopup(cls, parent):
        file_dialog = cls(parent)
        file_dialog.show()
        result = file_dialog.exec_()

        return result == QtWidgets.QFileDialog.Accepted, file_dialog.selectedFiles(), file_dialog.selectedOptions()


class CustomFileOptions(QtWidgets.QGroupBox):
    def __init__(self, title, parent=None, **kwargs):
        super(CustomFileOptions, self).__init__(title, parent, **kwargs)
        self.setFixedWidth(175)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(8, 22, 8, 8)
        self.layout().setSpacing(8)
        self.setStyleSheet(
            "QGroupBox {"
            "border: 1px solid;"
            "border-color: rgba(0, 0, 0, 64);"
            "border-radius: 6px;"
            "background-color: rgb(78, 80, 82);"
            "}"
            "QGroupBox::title {"
            "subcontrol-origin: margin;"
            "left: 6px;"
            "top: 4px;"
            "}"
        )


""" ====================================================================================================================
    UI classes for the import/export tool.
========================================================================================================================
"""


class PDX_UI(QtWidgets.QDialog):
    def __init__(self, parent=None):
        # parent to the Maya main window.
        parent = parent or get_maya_mainWindow()

        super(PDX_UI, self).__init__(parent)
        self.popup = None  # type: QtWidgets.QWidget
        self.settings = None  # type: QtCore.QSettings
        self.create_ui()

    def create_ui(self):
        # window properties
        self.setObjectName("PDX_Maya_Tools")
        self.setWindowTitle("PDX Maya Tools")
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # populate and connect controls
        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # File panel
        grp_File = CollapsingGroupBox("File", self)
        grp_File.setObjectName("grpFile")

        lbl_Import = QtWidgets.QLabel("Import:", self)
        self.mesh_import = btn_ImportMesh = QtWidgets.QPushButton("Load mesh ...", self)
        set_widget_icon(btn_ImportMesh, "out_polyCube.png")
        self.anim_import = btn_ImportAnim = QtWidgets.QPushButton("Load anim ...", self)
        set_widget_icon(btn_ImportAnim, "out_renderLayer.png")
        lbl_Export = QtWidgets.QLabel("Export:", self)
        self.mesh_export = btn_ExportMesh = QtWidgets.QPushButton("Save mesh ...", self)
        set_widget_icon(btn_ExportMesh, "out_polyCube.png")
        self.anim_export = btn_ExportAnim = QtWidgets.QPushButton("Save anim ...", self)
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
        self.ddl_EngineSelect = QtWidgets.QComboBox(self)
        self.ddl_EngineSelect.addItems(ENGINE_SETTINGS.keys())
        lbl_SetupAnimation = QtWidgets.QLabel("Animation:", self)
        self.spn_AnimationFps = QtWidgets.QSpinBox(self)
        self.spn_AnimationFps.setPrefix("FPS ")
        self.spn_AnimationFps.setKeyboardTracking(False)

        grp_Setup.inner.layout().addWidget(lbl_SetupEngine, 0, 0)
        grp_Setup.inner.layout().addWidget(self.ddl_EngineSelect, 0, 1)
        grp_Setup.inner.layout().addWidget(lbl_SetupAnimation, 1, 0)
        grp_Setup.inner.layout().addWidget(self.spn_AnimationFps, 1, 1)
        grp_Setup.inner.layout().setColumnStretch(1, 1)

        # Info panel
        grp_Info = CollapsingGroupBox("Info", self)
        grp_Info.setObjectName("grpInfo")

        lbl_Current = QtWidgets.QLabel("current version: {0}".format(github.CURRENT_VERSION), self)
        self.update_version, self.about_popup = None, None
        if github.AT_LATEST is False:  # update info appears if we aren't at the latest tag version
            self.update_version = btn_UpdateVersion = QtWidgets.QPushButton(
                "NEW UPDATE {0}".format(github.LATEST_VERSION), self
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
        self.mesh_import.clicked.connect(self.import_mesh)
        self.anim_import.clicked.connect(self.import_anim)
        self.mesh_export.clicked.connect(self.export_mesh)
        self.anim_export.clicked.connect(self.export_anim)

        self.material_create_popup.clicked.connect(partial(self.show_popup, MaterialCreatePopup_UI))
        self.material_edit_popup.clicked.connect(partial(self.show_popup, MaterialEditPopup_UI))
        self.ignore_bone.clicked.connect(partial(set_ignore_joints, True))
        self.unignore_bone.clicked.connect(partial(set_ignore_joints, False))
        self.mesh_index_popup.clicked.connect(partial(self.show_popup, MeshIndexPopup_UI))

        self.show_axis_bones.clicked.connect(partial(set_local_axis_display, True, object_type="joint"))
        self.hide_axis_bones.clicked.connect(partial(set_local_axis_display, False, object_type="joint"))
        self.show_axis_locators.clicked.connect(partial(set_local_axis_display, True, object_type="locator"))
        self.hide_axis_locators.clicked.connect(partial(set_local_axis_display, False, object_type="locator"))

        self.ddl_EngineSelect.currentIndexChanged.connect(self.set_engine)
        self.spn_AnimationFps.valueChanged.connect(self.set_fps)

        if self.update_version:
            self.update_version.clicked.connect(partial(webbrowser.open, str(github.LATEST_URL)))
        if self.about_popup:
            self.about_popup.clicked.connect(self.show_update_notes)
        self.help_wiki.clicked.connect(partial(webbrowser.open, bl_info["wiki_url"]))
        self.help_forum.clicked.connect(partial(webbrowser.open, bl_info["forum_url"]))
        self.help_source.clicked.connect(partial(webbrowser.open, bl_info["project_url"]))

    def showEvent(self, event):
        self.read_ui_settings()
        self.id = OpenMayaAPI.MEventMessage.addEventCallback("timeUnitChanged", partial(self.on_timeUnitChanged, self))
        event.accept()

    def closeEvent(self, event):
        self.write_ui_settings()
        OpenMayaAPI.MEventMessage.removeCallback(self.id)
        if self.popup:
            self.popup.close()
        event.accept()

    def read_ui_settings(self):
        self.settings = QtCore.QSettings(
            QtCore.QSettings.NativeFormat, QtCore.QSettings.UserScope, "IO_PDX_MESH", "MAYA"
        )

        # restore dialog size, position
        geom = self.settings.value("ui/geometry", None)
        if geom is None:
            parent_x, parent_y = self.parent().x(), self.parent().y()
            self.setGeometry(parent_x + 60, parent_y + 220, self.width(), self.height())
        else:
            self.restoreGeometry(geom)

        # restore groupbox panels expand state
        for grp in self.findChildren(QtWidgets.QGroupBox):
            state = bool(self.settings.value("ui/isChecked_{0}".format(grp.objectName()), defaultValue=True))
            grp.setChecked(state)

        # restore engine selection
        self.ddl_EngineSelect.setCurrentText(IO_PDX_SETTINGS.last_set_engine or ENGINE_SETTINGS.keys()[0])
        # restore scene animation fps
        self.spn_AnimationFps.setValue(int(get_animation_fps()))

        # ensure dialog was not restored offscreen after groupbox state is restored
        move_dialog_onscreen(self)

    def write_ui_settings(self):
        # store dialog size, position
        self.settings.setValue("ui/geometry", self.saveGeometry())

        # store groupbox panels expand state
        for grp in self.findChildren(QtWidgets.QGroupBox):
            self.settings.setValue("ui/isChecked_{0}".format(grp.objectName()), int(grp.isChecked()))

    @QtCore.Slot()
    def import_mesh(self):
        result, files, options = MeshImport_UI.runPopup(self)
        if result and files:
            mesh_filepath = files[0]
            options["progress_fn"] = MayaProgress
            try:
                import_meshfile(mesh_filepath, **options)
                IO_PDX_SETTINGS.last_import_mesh = mesh_filepath
            except Exception as err:
                IO_PDX_LOG.warning("FAILED to import {0}".format(mesh_filepath))
                IO_PDX_LOG.error(err)
                QtWidgets.QMessageBox.critical(self, "FAILURE", "Mesh import failed!\n\n{0}".format(err))
                MayaProgress.finished()
                raise
        else:
            IO_PDX_LOG.info("Nothing to import.")

    @QtCore.Slot()
    def export_mesh(self):
        result, files, options = MeshExport_UI.runPopup(self)
        if result and files:
            mesh_filepath = files[0]
            options["progress_fn"] = MayaProgress
            try:
                export_meshfile(mesh_filepath, **options)
                QtWidgets.QMessageBox.information(self, "SUCCESS", "Mesh export finished!\n\n{0}".format(mesh_filepath))
                IO_PDX_SETTINGS.last_export_mesh = mesh_filepath
            except Exception as err:
                IO_PDX_LOG.warning("FAILED to export {0}".format(mesh_filepath))
                IO_PDX_LOG.error(err)
                QtWidgets.QMessageBox.critical(self, "FAILURE", "Mesh export failed!\n\n{0}".format(err))
                MayaProgress.finished()
                raise
        else:
            IO_PDX_LOG.info("Nothing to export.")

    @QtCore.Slot()
    def import_anim(self):
        result, files, options = AnimImport_UI.runPopup(self)
        if result and files:
            anim_filepath = files[0]
            options["progress_fn"] = MayaProgress
            try:
                import_animfile(anim_filepath, **options)
                IO_PDX_SETTINGS.last_import_anim = anim_filepath
            except Exception as err:
                IO_PDX_LOG.warning("FAILED to import {0}".format(anim_filepath))
                IO_PDX_LOG.error(err)
                QtWidgets.QMessageBox.critical(self, "FAILURE", "Animation import failed!\n\n{0}".format(err))
                MayaProgress.finished()
                raise
        else:
            IO_PDX_LOG.info("Nothing to import.")

    @QtCore.Slot()
    def export_anim(self):
        result, files, options = AnimExport_UI.runPopup(self)
        if result and files:
            anim_filepath = files[0]
            try:
                options["progress_fn"] = MayaProgress
                if options["custom_range"]:
                    export_animfile(anim_filepath, **options)
                else:
                    options["frame_start"] = pmc.playbackOptions(query=True, minTime=True)
                    options["frame_end"] = pmc.playbackOptions(query=True, maxTime=True)
                    export_animfile(anim_filepath, **options)
                QtWidgets.QMessageBox.information(self, "SUCCESS", "Animation export finished!\n\n{0}".format(anim_filepath))
                IO_PDX_SETTINGS.last_export_anim = anim_filepath
            except Exception as err:
                IO_PDX_LOG.warning("FAILED to export {0}".format(anim_filepath))
                IO_PDX_LOG.error(err)
                QtWidgets.QMessageBox.critical(self, "FAILURE", "Animation export failed!\n\n{0}".format(err))
                MayaProgress.finished()
                raise
        else:
            IO_PDX_LOG.info("Nothing to export.")

    @QtCore.Slot()
    def show_popup(self, popup_widget):
        if self.popup:
            self.popup.close()
        self.popup = popup_widget(parent=self)
        self.popup.show()

    @QtCore.Slot()
    def set_engine(self):
        sel_engine = self.ddl_EngineSelect.currentText()
        IO_PDX_SETTINGS.last_set_engine = sel_engine
        IO_PDX_LOG.info("Set game engine to: '{0}'".format(sel_engine))

    @QtCore.Slot()
    def set_fps(self, fps):
        prev_fps = int(get_animation_fps())
        try:
            set_animation_fps(fps)
        except RuntimeError:
            QtWidgets.QMessageBox.warning(self, "ERROR", "Unsupported animation speed. ({0} fps)".format(fps))
            self.spn_AnimationFps.setValue(int(prev_fps))

    @QtCore.Slot()
    def on_timeUnitChanged(self, *args):
        curr_fps = int(get_animation_fps())
        self.spn_AnimationFps.setValue(curr_fps)

    @QtCore.Slot()
    def show_update_notes(self):
        msg_text = github.LATEST_NOTES

        # split text into multiple label rows if it's wider than the panel
        txt_lines = []
        for line in msg_text.splitlines():
            txt_lines.extend(wrap(line, 450 / 6))
            txt_lines.append("")

        QtWidgets.QMessageBox.information(self, bl_info["name"], "\n".join(txt_lines))


class MaterialCreatePopup_UI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(MaterialCreatePopup_UI, self).__init__(parent)
        self.parent = parent
        self.setWindowTitle("Create a PDX material")
        self.setWindowFlags(QtCore.Qt.Popup)
        self.setFixedWidth(350)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        move_dialog_onscreen(self)

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_help = QtWidgets.QLabel("Create a PDX material")
        grp_create = QtWidgets.QGroupBox(self)
        grp_create.setLayout(QtWidgets.QFormLayout())
        self.mat_name = QtWidgets.QLineEdit(self)
        self.mat_type = QtWidgets.QComboBox(self)
        self.use_custom = QtWidgets.QCheckBox("Custom type:", self)
        self.custom_type = QtWidgets.QLineEdit(self)
        self.custom_type.setEnabled(False)
        self.btn_okay = QtWidgets.QPushButton("Save", self)
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)

        # create layouts & add controls
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        main_layout.addWidget(lbl_help)
        form_layout = grp_create.layout()
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(4)
        form_layout.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        form_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Material name:", self.mat_name)
        form_layout.addRow("Material type:", self.mat_type)
        form_layout.addRow(self.use_custom, self.custom_type)
        main_layout.addWidget(grp_create)
        main_layout.addSpacing(1)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn_okay)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        # populate data
        sel_engine = IO_PDX_SETTINGS.last_set_engine or ENGINE_SETTINGS.keys()[0]
        self.mat_type.addItems(ENGINE_SETTINGS[sel_engine]["material"])
        self.mat_type.setCurrentIndex(-1)

    def connect_signals(self):
        self.use_custom.toggled.connect(self.mat_type.setDisabled)
        self.use_custom.toggled.connect(self.custom_type.setEnabled)
        self.btn_okay.clicked.connect(self.execute)
        self.btn_cancel.clicked.connect(self.close)

    @QtCore.Slot()
    def execute(self):
        mat_name = self.mat_name.text()
        mat_type = self.mat_type.currentText()
        if self.use_custom.isChecked() or mat_type == "":
            mat_type = self.custom_type.text()
        # create a mock PDXData object for convenience here to pass to the create_shader function
        mat_pdx = type(str("Material"), (PDXData, object), {"shader": [mat_type]})
        create_shader(mat_pdx, mat_name, None)
        IO_PDX_LOG.info("Created material: {0} ({1})".format(mat_name, mat_type))
        self.close()

    def showEvent(self, event):
        self.activateWindow()
        event.accept()


class MaterialEditPopup_UI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(MaterialEditPopup_UI, self).__init__(parent)
        self.parent = parent
        self.setWindowTitle("Edit a PDX material")
        self.setWindowFlags(QtCore.Qt.Popup)
        self.setFixedWidth(350)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        move_dialog_onscreen(self)

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_help = QtWidgets.QLabel("Edit a PDX material")
        lbl_selected = QtWidgets.QLabel("Selected material:")
        self.scene_mats = QtWidgets.QComboBox(self)
        self.scene_mats.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        grp_create = QtWidgets.QGroupBox(self)
        grp_create.setLayout(QtWidgets.QFormLayout())
        self.mat_name = QtWidgets.QLineEdit(self)
        self.mat_type = QtWidgets.QLineEdit(self)
        self.btn_okay = QtWidgets.QPushButton("Save", self)
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)

        # create layouts & add controls
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        main_layout.addWidget(lbl_help)
        selection_layout = QtWidgets.QHBoxLayout()
        selection_layout.addWidget(lbl_selected)
        selection_layout.addWidget(self.scene_mats)
        main_layout.addLayout(selection_layout)
        form_layout = grp_create.layout()
        form_layout.setContentsMargins(4, 4, 4, 4)
        form_layout.setSpacing(4)
        form_layout.setLabelAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        form_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignBottom)
        form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow("Material name:", self.mat_name)
        form_layout.addRow("Material type:", self.mat_type)
        main_layout.addWidget(grp_create)
        main_layout.addSpacing(1)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn_okay)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

        # populate data
        self.scene_mats.addItems([mat.name() for mat in list_scene_pdx_materials()])
        self.scene_mats.setCurrentIndex(-1)

    def connect_signals(self):
        self.scene_mats.currentTextChanged.connect(self.mat_select)
        self.btn_okay.clicked.connect(self.execute)
        self.btn_cancel.clicked.connect(self.close)

    @QtCore.Slot(str)
    def mat_select(self, mat_name):
        curr_mat = pmc.PyNode(mat_name)
        mat_shader = getattr(curr_mat, PDX_SHADER).get()
        self.mat_name.setText(mat_name)
        self.mat_type.setText(mat_shader)

    @QtCore.Slot()
    def execute(self):
        mat = pmc.PyNode(self.scene_mats.currentText())
        mat_name = self.mat_name.text()
        mat_type = self.mat_type.text()

        pmc.rename(mat, mat_name)
        getattr(mat, PDX_SHADER).set(mat_type)
        IO_PDX_LOG.info("Edited material: {0} ({1})".format(mat_name, mat_type))
        self.close()

    def showEvent(self, event):
        self.activateWindow()
        event.accept()


class MeshIndexPopup_UI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(MeshIndexPopup_UI, self).__init__(parent)
        self.parent = parent

        self.setWindowTitle("Set mesh index on PDX meshes")
        self.setWindowFlags(QtCore.Qt.Popup)
        self.setFixedSize(200, 300)
        if self.parent:
            center_x = self.parent.frameGeometry().center().x() - (self.width() / 2)
            center_y = self.parent.frameGeometry().center().y() - (self.height() / 2)
            self.setGeometry(center_x, center_y, self.width(), self.height())

        move_dialog_onscreen(self)

        self.create_controls()
        self.connect_signals()

    def create_controls(self):
        # create controls
        lbl_help = QtWidgets.QLabel("Set mesh index on PDX meshes")
        self.list_meshes = QtWidgets.QListWidget()
        self.list_meshes.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_meshes.defaultDropAction = QtCore.Qt.MoveAction
        lbl_tip = QtWidgets.QLabel("Drag/drop meshes to reorder")
        self.btn_okay = QtWidgets.QPushButton("Save", self)
        self.btn_cancel = QtWidgets.QPushButton("Cancel", self)

        # create layouts & add controls
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)
        main_layout.addWidget(lbl_help)
        main_layout.addWidget(self.list_meshes)
        main_layout.addWidget(lbl_tip)
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addWidget(self.btn_okay)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)
        self.setLayout(main_layout)

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
        self.btn_okay.clicked.connect(self.execute)
        self.btn_cancel.clicked.connect(self.close)

    @QtCore.Slot()
    def execute(self):
        IO_PDX_LOG.info("Setting mesh index order...")
        for i in xrange(self.list_meshes.count()):
            item = self.list_meshes.item(i)
            maya_mesh = pmc.PyNode(item.data(QtCore.Qt.UserRole))  # type: pmc.nt.Mesh
            set_mesh_index(maya_mesh, i)
            IO_PDX_LOG.info("\t{0} - {0}".format(maya_mesh.name(), i))

        self.close()

    def showEvent(self, event):
        self.activateWindow()
        event.accept()


class MeshImport_UI(CustomFileDialog):
    def __init__(self, parent=None):
        super(MeshImport_UI, self).__init__(
            parent=parent, caption="Import a mesh file", filter="PDX Mesh files (*.mesh)"
        )
        options_group = CustomFileOptions("Import Settings", self)
        self.addCustomOptions(options_group)

        self.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        self.setLabelText(QtWidgets.QFileDialog.Accept, "Import")
        last_directory = os.path.dirname(IO_PDX_SETTINGS.last_import_mesh or "")
        self.setDirectory(last_directory)
        self.setSidebarUrls([QtCore.QUrl.fromLocalFile(last_directory)])

        self.chk_mesh = QtWidgets.QCheckBox("Mesh")
        self.chk_mesh.setObjectName("imp_mesh")

        self.mesh_settings = QtWidgets.QGroupBox()
        self.mesh_settings.setLayout(QtWidgets.QVBoxLayout())

        self.chk_joinmats = QtWidgets.QCheckBox("Join materials")
        self.chk_joinmats.setObjectName("join_materials")

        self.chk_skel = QtWidgets.QCheckBox("Skeleton")
        self.chk_skel.setObjectName("imp_skel")

        self.chk_locs = QtWidgets.QCheckBox("Locators")
        self.chk_locs.setObjectName("imp_locs")

        self.mesh_settings.layout().addWidget(self.chk_joinmats)
        self.mesh_settings.layout().setContentsMargins(16, 4, 4, 4)
        self.mesh_settings.layout().setAlignment(QtCore.Qt.AlignRight)
        self.mesh_settings.setStyleSheet("background-color: rgb(63, 65, 67);")

        for ctrl in [self.chk_mesh, self.mesh_settings, self.chk_skel, self.chk_locs]:
            options_group.layout().addWidget(ctrl)

        for chk in [self.chk_mesh, self.chk_joinmats, self.chk_skel, self.chk_locs]:
            chk.setChecked(True)

        self.chk_mesh.toggled.connect(self.mesh_settings.setVisible)


class AnimImport_UI(CustomFileDialog):
    def __init__(self, parent=None):
        super(AnimImport_UI, self).__init__(
            parent=parent, caption="Import a anim file", filter="PDX Animation files (*.anim)"
        )
        options_group = CustomFileOptions("Import Settings", self)
        self.addCustomOptions(options_group)

        self.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        self.setAcceptMode(QtWidgets.QFileDialog.AcceptOpen)
        self.setLabelText(QtWidgets.QFileDialog.Accept, "Import")
        last_directory = os.path.dirname(IO_PDX_SETTINGS.last_import_anim or "")
        self.setDirectory(last_directory)
        self.setSidebarUrls([QtCore.QUrl.fromLocalFile(last_directory)])

        self.lbl_start = QtWidgets.QLabel("Start frame:")
        self.spn_frame = QtWidgets.QSpinBox()
        self.spn_frame.setMaximumWidth(100)
        self.spn_frame.setObjectName("frame_start")
        self.spn_frame.setValue(1)

        frame_group = QtWidgets.QHBoxLayout()
        for ctrl in [self.lbl_start, self.spn_frame]:
            frame_group.addWidget(ctrl)
        options_group.layout().addLayout(frame_group)


class MeshExport_UI(CustomFileDialog):
    def __init__(self, parent=None):
        super(MeshExport_UI, self).__init__(
            parent=parent, caption="Export a mesh file", filter="PDX Mesh files (*.mesh)"
        )
        options_group = CustomFileOptions("Export Settings")
        self.addCustomOptions(options_group)

        self.setFileMode(QtWidgets.QFileDialog.AnyFile)
        self.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        self.setLabelText(QtWidgets.QFileDialog.Accept, "Export")
        last_directory = os.path.dirname(IO_PDX_SETTINGS.last_export_mesh or "")
        self.setDirectory(last_directory)
        self.setSidebarUrls([QtCore.QUrl.fromLocalFile(last_directory)])
        self.setDefaultSuffix(".mesh")

        self.chk_mesh = QtWidgets.QCheckBox("Mesh")
        self.chk_mesh.setObjectName("exp_mesh")

        self.mesh_settings = QtWidgets.QGroupBox()
        self.mesh_settings.setLayout(QtWidgets.QVBoxLayout())

        self.chk_skel = QtWidgets.QCheckBox("Skeleton")
        self.chk_skel.setObjectName("exp_skel")

        self.chk_locs = QtWidgets.QCheckBox("Locators")
        self.chk_locs.setObjectName("exp_locs")

        self.chk_sel_only = QtWidgets.QCheckBox("Selection only")
        self.chk_sel_only.setObjectName("exp_selected")

        self.chk_split_vtx = QtWidgets.QCheckBox("Split all vertices")
        self.chk_split_vtx.setObjectName("split_verts")

        self.mesh_settings.layout().addWidget(self.chk_split_vtx)
        self.mesh_settings.layout().setContentsMargins(16, 4, 4, 4)
        self.mesh_settings.layout().setAlignment(QtCore.Qt.AlignRight)
        self.mesh_settings.setStyleSheet("background-color: rgb(63, 65, 67);")

        for ctrl in [self.chk_mesh, self.mesh_settings, self.chk_skel, self.chk_locs, self.chk_sel_only]:
            options_group.layout().addWidget(ctrl)

        for ctrl in [self.chk_mesh, self.chk_skel, self.chk_locs]:
            ctrl.setChecked(True)

        self.chk_mesh.toggled.connect(self.mesh_settings.setVisible)


class AnimExport_UI(CustomFileDialog):
    def __init__(self, parent=None):
        super(AnimExport_UI, self).__init__(
            parent=parent, caption="Export a anim file", filter="PDX Animation files (*.anim)"
        )
        options_group = CustomFileOptions("Export Settings")
        self.addCustomOptions(options_group)

        self.setFileMode(QtWidgets.QFileDialog.AnyFile)
        self.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        self.setLabelText(QtWidgets.QFileDialog.Accept, "Export")
        last_directory = os.path.dirname(IO_PDX_SETTINGS.last_export_anim or "")
        self.setDirectory(last_directory)
        self.setSidebarUrls([QtCore.QUrl.fromLocalFile(last_directory)])
        self.setDefaultSuffix(".anim")

        self.chk_custom = QtWidgets.QCheckBox("Custom range")
        self.chk_custom.setObjectName("custom_range")

        self.range_settings = QtWidgets.QGroupBox()
        self.range_settings.setLayout(QtWidgets.QVBoxLayout())

        self.lbl_start = QtWidgets.QLabel("Start frame:")
        self.spn_start = QtWidgets.QSpinBox()
        self.spn_start.setFixedWidth(65)
        self.spn_start.setObjectName("frame_start")

        self.lbl_end = QtWidgets.QLabel("End frame:")
        self.spn_end = QtWidgets.QSpinBox()
        self.spn_end.setFixedWidth(65)
        self.spn_end.setObjectName("frame_end")

        self.start_group = QtWidgets.QHBoxLayout()
        self.start_group.setContentsMargins(0, 0, 0, 0)
        for ctrl in [self.lbl_start, self.spn_start]:
            self.start_group.addWidget(ctrl)
        self.end_group = QtWidgets.QHBoxLayout()
        self.end_group.setContentsMargins(0, 0, 0, 0)
        for ctrl in [self.lbl_end, self.spn_end]:
            self.end_group.addWidget(ctrl)

        self.range_settings.layout().addLayout(self.start_group)
        self.range_settings.layout().addLayout(self.end_group)
        self.range_settings.layout().setContentsMargins(16, 4, 4, 4)
        self.range_settings.layout().setAlignment(QtCore.Qt.AlignRight)
        self.range_settings.setStyleSheet("background-color: rgb(63, 65, 67);")

        options_group.layout().addWidget(self.chk_custom)
        options_group.layout().addWidget(self.range_settings)

        self.chk_custom.setChecked(False)
        self.range_settings.setVisible(False)
        self.chk_custom.toggled.connect(self.range_settings.setVisible)


class MayaProgress(object):
    """ Wrapping the Maya progress window for convenience. """

    def __del__(self):
        self.finished()

    def __call__(self, *args):
        args = list(args)
        name = args.pop(0)
        try:
            fn = getattr(self, name)
            fn(*args)
        except AttributeError:
            IO_PDX_LOG.warning("Maya progress window called with unknown method '{0}'".format(name))

    @staticmethod
    def show(max_value, title):
        cmds.progressWindow(title=title, progress=0, min=0, max=max_value, status="", isInterruptable=False)

    @staticmethod
    def update(step, status):
        progress = cmds.progressWindow(query=True, progress=True)
        max_value = cmds.progressWindow(query=True, max=True)
        if progress >= max_value:
            cmds.progressWindow(edit=True, progress=0)
        cmds.progressWindow(edit=True, step=step, status=status)

    @staticmethod
    def finished():
        cmds.progressWindow(endProgress=True)


""" ====================================================================================================================
    Main entry point.
========================================================================================================================
"""


def main():
    IO_PDX_LOG.info("Loading Maya UI.")

    maya_main_window = get_maya_mainWindow()
    pdx_tools = maya_main_window.findChild(QtWidgets.QDialog, "PDX_Maya_Tools")

    if pdx_tools is not None:
        # closing the UI deletes the widget due to flag WA_DeleteOnClose, allowing all code to be reloaded
        pdx_tools.close()

    pdx_tools = PDX_UI(parent=maya_main_window)
    pdx_tools.show()


if __name__ == "__main__":
    main()
