import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSlider, QLabel, QDoubleSpinBox
from PySide6.QtCore import Qt
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import *
from OpenGL.GLU import *


class ZUpStageWidget(QOpenGLWidget):
    def __init__(self, width=1.3312, depth=1.3312, height=5.0, parent=None):
        super().__init__(parent)
        self.width = width
        self.depth = depth
        self.height = height
        # Current plane position (0..height)
        self.plane_z = 0.5 * height

    def initializeGL(self):
        glClearColor(0.2667, 0.2667, 0.2667, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()

        # since Z → X, the half-width is half the model height
        half_w = 0.62 * self.height

        # keep pixels square
        aspect = (w / h) if h else 1.0

        if aspect >= 1.0:
            glOrtho(-half_w, +half_w,
                    -half_w/aspect, +half_w/aspect,
                    -10*self.height, +10*self.height)
        else:
            glOrtho(-half_w*aspect, +half_w*aspect,
                    -half_w,          +half_w,
                    -10*self.height, +10*self.height)

        glMatrixMode(GL_MODELVIEW)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        # Compute center of the box
        cx = 0.5 * self.width
        cy = 0.5 * self.depth
        cz = 0.5 * self.height

        # Position the camera looking at the box center
        ex = cx + 2.5
        ey = cy - 4.0
        ez = cz + 2.0
        gluLookAt(ex, ey, ez,
                  cx, cy, cz,
                  0.0, 0.0, 1.0)

        # Rotate scene so Z→X, Y→Z
        glTranslatef(cx, cy, cz)
        glRotatef(90.0, 1.0, 0.0, 0.0)
        glRotatef(90.0, 0.0, 1.0, 0.0)
        glTranslatef(-cx, -cy, -cz)

        # Draw semi-transparent blue outer box with varied face hues
        face_colors = [
            (0.5, 0.6, 0.9, 0.25),  # top
            (0.3, 0.4, 0.7, 0.25),  # bottom
            (0.35, 0.45, 0.75, 0.25),# front
            (0.45, 0.55, 0.85, 0.25),# back
            (0.4, 0.5, 0.8, 0.25),   # right
            (0.25, 0.35, 0.65, 0.25) # left
        ]
        # Disable culling so both sides of each face get colored
        glDisable(GL_CULL_FACE)
        self.draw_box_face_colors(0, 0, 0,
                                   self.width, self.depth, self.height,
                                   face_colors)
        glEnable(GL_CULL_FACE)

        # Draw box wireframe
        self.draw_box_wireframe(0, 0, 0,
                                self.width, self.depth, self.height,
                                color=(1.0, 1.0, 1.0))

        # Draw horizontal plane at plane_z
        self.draw_xy_plane(self.plane_z, color=(0.2, 0.8, 0.2, 0.6))

    def draw_box_face_colors(self, x, y, z, w, d, h, colors):
        """Draws a filled box with per-face colors on both sides"""
        vertices = [
            (x,     y,     z),
            (x + w, y,     z),
            (x + w, y + d, z),
            (x,     y + d, z),
            (x,     y,     z + h),
            (x + w, y,     z + h),
            (x + w, y + d, z + h),
            (x,     y + d, z + h)
        ]
        faces = [
            (4, 5, 6, 7),  # top
            (0, 1, 2, 3),  # bottom
            (0, 1, 5, 4),  # front
            (2, 3, 7, 6),  # back
            (1, 2, 6, 5),  # right
            (0, 3, 7, 4)   # left
        ]
        glDepthMask(GL_FALSE)
        glBegin(GL_QUADS)
        for face, col in zip(faces, colors):
            glColor4f(*col)
            for idx in face:
                glVertex3fv(vertices[idx])
        glEnd()
        glDepthMask(GL_TRUE)

    def draw_box_wireframe(self, x, y, z, w, d, h, color):
        """Draws the edges of a box as a wireframe."""
        r, g, b = color
        glColor3f(r, g, b)
        glLineWidth(1.5)
        verts = [
            (x,     y,     z),
            (x + w, y,     z),
            (x + w, y + d, z),
            (x,     y + d, z),
            (x,     y,     z + h),
            (x + w, y,     z + h),
            (x + w, y + d, z + h),
            (x,     y + d, z + h)
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7)
        ]
        glBegin(GL_LINES)
        for i0, i1 in edges:
            glVertex3fv(verts[i0]); glVertex3fv(verts[i1])
        glEnd()

    def draw_xy_plane(self, z_plane, color):
        z = max(0, min(self.height, z_plane))
        glColor4f(*color)
        glBegin(GL_QUADS)
        glVertex3f(0, 0, z)
        glVertex3f(self.width, 0, z)
        glVertex3f(self.width, self.depth, z)
        glVertex3f(0, self.depth, z)
        glEnd()

    def set_z_position(self, z_value):
        """Slot to update plane_z from external signal"""
        self.plane_z = max(0.0, min(self.height, float(z_value)))
        self.update()
