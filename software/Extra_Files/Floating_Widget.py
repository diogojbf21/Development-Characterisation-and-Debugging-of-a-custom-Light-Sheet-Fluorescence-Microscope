from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QPainter, QPen
from PySide6.QtCore import Qt

from PySide6.QtWidgets import QMdiSubWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtCore import Qt, QPoint

class FloatingWidget(QMdiSubWindow):
    def __init__(self, widget, title="Floating Window", width=300, height=200):
        super().__init__()
        self.inner_widget = widget
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)  # Remove native decorations

        # **Wrap everything in a named QFrame to apply the border properly**
        self.outer_frame = QFrame()
        self.outer_frame.setObjectName("OuterFrame")  # Unique identifier

        self.outer_frame.setStyleSheet("""
            #OuterFrame {  /* Only apply to the outer frame */
                background-color: #222222;
                border: 2px solid black;
                border-radius: 5px;
            }
        """)

        # Custom title bar
        self.title_bar = QWidget(self)
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background-color: #414851; border-bottom: 2px solid black;")

        # Title label
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; padding-left: 10px;")  # Ensure no borders on labels

        # Title bar layout
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(5, 0, 5, 0)
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        self.title_bar.setLayout(title_layout)

        # Main content layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.title_bar)
        main_layout.addWidget(widget)

        # Set up frame with the layout
        self.outer_frame.setLayout(main_layout)
        self.setWidget(self.outer_frame)  # Set the frame as the widget inside QMdiSubWindow

        # **Ensure the floating window starts at the correct size**
        self.resize(width, height)

        # Enable dragging
        self.moving = False
        self.offset = QPoint()

    def mousePressEvent(self, event):
        """Enable dragging when clicking on the title bar."""
        if event.button() == Qt.LeftButton and event.position().toPoint().y() <= self.title_bar.height():
            self.moving = True
            self.offset = event.position().toPoint()

    def mouseMoveEvent(self, event):
        """Move the window when dragging."""
        if self.moving:
            new_pos = self.mapToParent(event.position().toPoint() - self.offset)
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        """Stop dragging when mouse is released."""
        if event.button() == Qt.LeftButton:
            self.moving = False

    def closeEvent(self, event):
        if hasattr(self, "inner_widget") and hasattr(self.inner_widget, "shutdown"):
            print(f"🧹 FloatingWidget shutting down inner widget: {type(self.inner_widget).__name__}")
            try:
                self.inner_widget.shutdown()
            except Exception as e:
                print(f"⚠️ Error during shutdown of {type(self.inner_widget).__name__}: {e}")

        super().closeEvent(event)