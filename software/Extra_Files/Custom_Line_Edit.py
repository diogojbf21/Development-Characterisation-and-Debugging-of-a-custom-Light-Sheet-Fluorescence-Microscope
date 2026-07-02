from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QColor
from PySide6.QtWidgets import QLineEdit, QGraphicsDropShadowEffect

class CustomLineEdit(QLineEdit):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # Directly check the text and apply the glow effect if empty
            if not self.text():
                glow = QGraphicsDropShadowEffect(self)
                glow.setColor(QColor("red"))
                glow.setBlurRadius(20)
                glow.setOffset(0)
                self.setGraphicsEffect(glow)
            else:
                # Remove any previous effect if text is present
                self.setGraphicsEffect(None)
        # Process the key event as usual
        super().keyPressEvent(event)