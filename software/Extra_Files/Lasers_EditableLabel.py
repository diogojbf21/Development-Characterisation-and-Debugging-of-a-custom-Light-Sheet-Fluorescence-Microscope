from PySide6.QtWidgets import QApplication, QLabel, QLineEdit
from PySide6.QtCore import Qt, Signal

class LasersEditableLabel(QLabel):
    textChanged = Signal(str)  # Define a custom signal

    def __init__(self, text="0 mW"):
        super().__init__(text)

        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: none; padding: 2px;")  # Keep QLabel clean
        
        self.line_edit = None  # Placeholder for QLineEdit
        self.mouseDoubleClickEvent = self.enable_editing

    def enable_editing(self, event):
        """Replace QLabel with QLineEdit for editing."""
        self.line_edit = QLineEdit(self.parent())  # Place QLineEdit in the same parent
        self.line_edit.setText(self.text().replace(" mW", ""))  # Remove "mW" for clean input
        self.line_edit.setAlignment(self.alignment())  # Preserve alignment
        
        self.line_edit.setStyleSheet("border: none; padding: 2px;")
        self.line_edit.setGeometry(self.geometry())  # Match label position & size
        self.line_edit.show()
        self.line_edit.setFocus()
        self.line_edit.selectAll()  # Auto-select text

        self.line_edit.editingFinished.connect(self.disable_editing)

        self.hide()  # Hide QLabel while editing

    def disable_editing(self):
        """Restore QLabel with formatted integer value + 'mW', clipping out-of-range values."""
        new_text = self.line_edit.text().strip()
        
        try:
            value = int(new_text)  # Convert to integer
            value = max(0, min(100, value))  # Clip to 0-100
        except ValueError:
            value = 0  # If invalid input, default to 0
        
        formatted_text = f"{value} mW"

        self.setText(formatted_text)  # Update label text first

        self.show()  # Show QLabel again
        self.line_edit.deleteLater()  # Remove QLineEdit
        self.line_edit = None
        
        self.textChanged.emit(self.text())  # Emit signal with the updated text