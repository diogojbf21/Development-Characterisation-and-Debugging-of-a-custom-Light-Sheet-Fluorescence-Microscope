import sys
import os
import json

from PySide6.QtCore import (
    QDir, Qt, QModelIndex,
    QThreadPool, QRunnable, Signal, Slot, QPoint, QEvent
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QTreeView, QFileSystemModel,
    QInputDialog, QMessageBox, QHeaderView, QDialog
)
from PySide6.QtGui import QIcon, QCursor
from PySide6.QtCore import QSize, QFile

from pathlib import Path

class ClickableTreeView(QTreeView):
    """Uses eventFilter on blank-space clicks to clear selection; no focusOut override."""
    pass

class _FolderSizeWorker(QRunnable):
    """
    QRunnable that computes the total size of a directory, then
    emits model.sizeComputed(path, size).
    """
    def __init__(self, path: str, notify_signal: Signal):
        super().__init__()
        self.path = path
        self.notify = notify_signal

    def run(self):
        total = 0
        for root, dirs, files in os.walk(self.path):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        self.notify.emit(self.path, total)

class FileSystemModelWithFolderSizes(QFileSystemModel):
    sizeComputed = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._size_cache = {}
        self._pending = set()
        self._pool = QThreadPool.globalInstance()
        self.sizeComputed.connect(self._on_size_computed)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return super().columnCount(parent) + 1

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        # Size column (column 1)
        if role == Qt.DisplayRole and index.column() == 1:
            info = self.fileInfo(index)
            if info.isDir():
                path = info.absoluteFilePath()
                if path in self._size_cache:
                    return self._humanReadable(self._size_cache[path])
                if path not in self._pending:
                    self._pending.add(path)
                    worker = _FolderSizeWorker(path, self.sizeComputed)
                    self._pool.start(worker)
                return "Calculating..."
        # "Date Created" column (column 4)
        if role == Qt.DisplayRole and index.column() == 4:
            info = self.fileInfo(index)
            dt = info.birthTime()
            if dt.isValid():
                return dt.toString("     HH:mm, yyyy-MM-dd")
            return ""
        return super().data(index, role)

    @Slot(str, int)
    def _on_size_computed(self, path: str, size: int):
        self._size_cache[path] = size
        self._pending.discard(path)
        idx = self.index(path)
        if idx.isValid():
            size_idx = idx.sibling(idx.row(), 1)
            self.dataChanged.emit(size_idx, size_idx, [Qt.DisplayRole])

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            headers = ["Name", "Size", "Type", "Date Modified", "Date Created"]
            if 0 <= section < len(headers):
                return headers[section]
        return super().headerData(section, orientation, role)

    def _humanReadable(self, size: int) -> str:
        for unit in ["B","KB","MB","GB","TB","PB"]:
            if size < 1024.0:
                return f"{size:.1f}\u00a0{unit}"
            size /= 1024.0
        return f"{size:.1f}\u00a0EB"

class File_Explorer(QWidget):

    # Signal for the current Path
    currentPathChanged = Signal(str)

    @property
    def current_path(self) -> str:
        return self.path_edit.text()
    
    def _save_last_folder(self, path: str):
        """Write the given path into Last_Folder.json."""
        try:
            with open(self.folder_json_path, "w") as f:
                json.dump({"last_folder": path}, f, indent=4)
        except Exception as e:
            print(f"Could not save last folder: {e}")

    def __init__(self, start_path: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("File Explorer")
        self.setFixedSize(500, 450-120)

        # Last Folder JSON setup
        base = os.getcwd()
        self.folder_json_path = os.path.join(base, "Extra_Files", "Last_Folder.json")
        os.makedirs(os.path.dirname(self.folder_json_path), exist_ok=True)

        # At the top of your module or inside your widget init:
        script_path        = Path(__file__).resolve()
        dropdown_normal_fp = script_path.parent / "icons" / "dropdown_normal.png"
        dropdown_down_fp   = script_path.parent / "icons" / "dropdown_down.png"

        dark_qss = f"""
        /* 
        BASE PAINTING
        */
        QMainWindow, QWidget, QDialog, QFrame {{
            background-color: #222222;
            color: #FFFFFF;
        }}

        /* 
        BUTTONS (with softened green accent when checked)
        */
        QPushButton {{
            background-color: #2E2E2E;
            color: #FFFFFF;
            border: 2px solid #555;
            border-radius: 6px;
            padding: 0px 16px;
            font-size: 13px;
            outline: none;
        }}
        QPushButton:hover {{
            background-color: #3C3C3C;
            border: 2px solid #777;
        }}
        QPushButton:pressed {{
            background-color: #1E1E1E;
            border: 2px solid #999;
        }}
        QPushButton:disabled {{
            background-color: #2A2A2A;
            border: 2px solid #444444;
            color: #CCCCCC;
        }}
        QPushButton:checked {{
            background-color: #25472D;      /* softer green */
            border: 2px solid #5EB868;
            color: #000000;
            font-weight: bold;
        }}
        QPushButton:checked:hover {{
            background-color: #448F3E;
            border: 2px solid #6EBF7E;
        }}
        QPushButton:checked:pressed {{
            background-color: #307033;
            border: 2px solid #539652;
        }}

        /* 
        TEXT CONTROLS
        */
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: #2A2A2A;
            color: #FFFFFF;
            border: 1px solid #444444;
            selection-background-color: #555555;
            selection-color: #FFFFFF;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border: 1px solid #25472D;
        }}

        /* 
        CHECKBOX & RADIO (green when checked)
        */
        QCheckBox::indicator, QRadioButton::indicator {{
            width: 16px; height: 16px;
            border: 1px solid #555;
            border-radius: 3px;
            background: #2E2E2E;
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: #25472D;
            border: 1px solid #5EB868;
        }}

        /* 
        TREE & TABLE VIEWS (green selection)
        */
        QTreeView, QTableView, QListView {{
            background-color: #222222;
            color: #FFFFFF;
            gridline-color: #444444;
            show-decoration-selected: 1;
            alternate-background-color: #2A2A2A;
        }}
        QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{
            background-color: #25472D;
            color: #FFFFFF;
        }}
        QHeaderView::section {{
            background-color: #2A2A2A;
            color: #FFFFFF;
            padding: 2px;
            border: 1px solid #444444;
        }}

        QTreeView::branch:has-children:closed {{
            image: url("{dropdown_normal_fp.as_posix()}") !important;
        }}
        QTreeView::branch:has-children:open {{
            image: url("{dropdown_down_fp.as_posix()}") !important;
        }}

        /* when Qt paints the icon in “Disabled” mode (i.e. unfocused) */
        QTreeView::branch:has-children:closed:disabled {{
            image: url("{dropdown_normal_fp.as_posix()}") !important;
        }}
        QTreeView::branch:has-children:open:disabled {{
            image: url("{dropdown_down_fp.as_posix()}") !important;
        }}

        /* 
        SLIDER (green handle on hover/active)
        */
        QSlider::groove:horizontal {{
            background: #444444;
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: #666666;
            width: 12px;
            margin: -3px 0;
            border-radius: 6px;
        }}
        QSlider::handle:horizontal:hover {{
            background: #25472D;
        }}
        QSlider::handle:horizontal:pressed {{
            background: #307033;
            border: 2px solid #539652;
        }}

        /* 
        SCROLLBARS
        */
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: #222222;
            width: 12px; height: 12px;
            margin: 0px;
        }}
        /* hide the default arrows and pages */
        QScrollBar::add-line, QScrollBar::sub-line,
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
            border: none;
            width: 0px; height: 0px;
        }}
        /* the draggable handle */
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: #444444;
            min-height: 20px;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: #666666;
        }}

        /* 
        TOOLTIP
        */
        QToolTip {{
            background-color: #333333;
            color: #FFFFFF;
            border: 1px solid #555555;
        }}
        """

        self.setStyleSheet(dark_qss)

        # controls
        self.back_btn = QPushButton(self)
        self.back_btn.setFixedWidth(30)
        self.back_btn.setEnabled(False)
        self.back_btn.setIcon(QIcon("icons//backarrow.png"))

        self.path_edit      = QLineEdit(self)
        self.browse_btn     = QPushButton("Browse…", self)
        self.new_folder_btn = QPushButton("New Folder", self)
        self.delete_btn     = QPushButton("Delete", self)

        # prevent these buttons from stealing focus
        for btn in (self.back_btn, self.browse_btn, self.new_folder_btn, self.delete_btn):
            btn.setFocusPolicy(Qt.NoFocus)

        # model & view
        self.model = FileSystemModelWithFolderSizes(self)
        self.model.setFilter(QDir.NoDotAndDotDot | QDir.AllEntries)

        self.tree = ClickableTreeView(self)
        self.tree.setModel(self.model)
        self.tree.viewport().installEventFilter(self)
        for col in (2, 3):
            self.tree.setColumnHidden(col, True)

        # Set initial column widths, but keep Interactive resize mode
        hdr = self.tree.header()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setFixedHeight(23)
        self.tree.setColumnWidth(0, 260)  # Name
        self.tree.setColumnWidth(1, 80)   # Size
        self.tree.setColumnWidth(4, 120)  # Date Created

        # layout
        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addWidget(self.path_edit)
        top.addWidget(self.browse_btn)

        second = QHBoxLayout()
        second.addStretch()
        second.addWidget(self.new_folder_btn)
        second.addWidget(self.delete_btn)

        main = QVBoxLayout(self)
        main.addLayout(top)
        main.addLayout(second)
        main.addWidget(self.tree)

        # signals
        self.back_btn.clicked.connect(self.on_up)
        self.browse_btn.clicked.connect(self.on_browse)
        self.new_folder_btn.clicked.connect(self.on_new_folder)
        self.delete_btn.clicked.connect(self.on_delete)
        self.path_edit.returnPressed.connect(self.on_path_edited)
        self.tree.doubleClicked.connect(self.on_tree_activated)

        # go to default start_path (fall back to home if None)
        default = start_path or QDir.homePath()
        self._navigate_to(default)

    def _navigate_to(self, path: str):
        """Set view to `path` and enable/disable the Up button based on parent existence."""
        self.path_edit.setText(path)
        idx = self.model.setRootPath(path)
        self.tree.setRootIndex(idx)

        parent = os.path.dirname(path.rstrip(os.sep))
        can_up = bool(parent and os.path.isdir(parent))
        self.back_btn.setEnabled(can_up)

        # emits the current path
        self.currentPathChanged.emit(path)

        # save the changed path in the Last_Folder.json file
        self._save_last_folder(path)

    def on_up(self):
        current = self.path_edit.text().rstrip(os.sep)
        parent = os.path.dirname(current)
        if parent and os.path.isdir(parent):
            self._navigate_to(parent)

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder",
            self.path_edit.text() or QDir.homePath(),
            QFileDialog.ShowDirsOnly | QFileDialog.ReadOnly
        )
        if folder:
            self._navigate_to(folder)

    def on_path_edited(self):
        path = self.path_edit.text()
        if os.path.isdir(path):
            self._navigate_to(path)
        else:
            QMessageBox.warning(self, "Error", f"Invalid path:\n{path}")

    def on_tree_activated(self, index: QModelIndex):
        info = self.model.fileInfo(index)
        if info.isDir():
            self._navigate_to(info.absoluteFilePath())

    def on_new_folder(self):
        current = self.path_edit.text()
        if not os.path.isdir(current):
            QMessageBox.warning(self, "Error", f"Invalid path:\n{current}")
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("New Folder")
        dialog.setLabelText("Folder name:")
        dialog.setOkButtonText("Create")
        dialog.setCancelButtonText("Cancel")
        dialog.move(QCursor.pos() + QPoint(-110, -50))

        if dialog.exec() != QDialog.Accepted:
            return
        name = dialog.textValue()
        if not name:
            return

        new_dir = os.path.join(current, name)
        try:
            os.mkdir(new_dir)
            idx = self.model.index(current)
            try:
                self.model.refresh(idx)
            except AttributeError:
                self.model.setRootPath(self.model.rootPath())
            self.tree.expand(idx)
            new_idx = self.model.index(new_dir)
            if new_idx.isValid():
                self.tree.scrollTo(new_idx)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")

    def on_delete(self):
        selected = self.tree.selectionModel().selectedRows(0)
        if not selected:
            return

        idx = selected[0]
        path = self.model.filePath(idx)
        info = self.model.fileInfo(idx)

        msg = QMessageBox(self)
        msg.setWindowTitle("Confirm Delete")
        msg.setText(f"Are you sure you want to delete:\n{path}")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setIcon(QMessageBox.Warning)
        msg.move(QCursor.pos() + QPoint(-200, -50))

        if msg.exec() != QMessageBox.Yes:
            return

        if info.isDir():
            success = QDir(path).removeRecursively()
        else:
            success = QFile.remove(path)

        if not success:
            QMessageBox.warning(self, "Error", f"Could not delete:\n{path}")

    def eventFilter(self, obj, event):
        if obj is self.tree.viewport() and event.type() == QEvent.MouseButtonPress:
            idx = self.tree.indexAt(event.pos())
            if not idx.isValid():
                self.tree.selectionModel().clearSelection()
                self.tree.setCurrentIndex(self.tree.rootIndex())
        return super().eventFilter(obj, event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = File_Explorer()
    window.show()
    sys.exit(app.exec())
