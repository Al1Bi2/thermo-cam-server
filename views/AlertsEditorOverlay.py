import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsPolygonItem, QGraphicsItem, QGraphicsEllipseItem,
    QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QFrame, QWidget, QSizePolicy, QGraphicsPathItem, QMenu, QDialog, QCheckBox, QGraphicsPixmapItem, QSplitter
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QPoint, QTimer, QLine
from PyQt6.QtGui import (QColor, QPen, QPainter, QPolygonF, QBrush,
                         QPainterPath, QMouseEvent, QPixmap)


class AlertPopupPanel(QDialog):
    def __init__(self, parent=None, item=None, threshold_value=None, is_active=True):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setFixedSize(200, 120)
        self.current_item = item

        layout = QVBoxLayout()
        self.threshold_label = QLabel("Порог:")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(threshold_value)

        self.is_active_chk = QCheckBox("Активен")
        if is_active:
            self.is_active_chk.setCheckState(Qt.CheckState.Checked)
        else:
            self.is_active_chk.setCheckState(Qt.CheckState.Unchecked)
        self.delete_btn = QPushButton("Удалить")

        layout.addWidget(self.threshold_label)
        layout.addWidget(self.slider)
        layout.addWidget(self.is_active_chk)
        layout.addWidget(self.delete_btn)
        self.setLayout(layout)

        # Подключение сигналов
        self.delete_btn.clicked.connect(self.delete_current_item)
        self.slider.valueChanged.connect(self.update_threshold)
        self.is_active_chk.stateChanged.connect(self.update_is_active)

    def mousePressEvent(self, event):
        if not self.rect().contains(event.pos()):
            event.accept()  # Помечаем событие как обработанное
            self.close()
        else:
            super().mousePressEvent(event)

    def set_item(self, item):
        """Установка текущего элемента для редактирования"""
        self.current_item = item
        if item:
            self.slider.setValue(item.threshold)

    def delete_current_item(self):
        if self.current_item:
            self.current_item.scene().removeItem(self.current_item)
            self.current_item = None
            self.accept()
            self.close()
            # self.hide()

    def update_threshold(self, value):
        if self.current_item:
            self.current_item.threshold = value

    def update_is_active(self):
        if self.current_item:
            self.current_item.is_active = self.is_active_chk.checkState() == Qt.CheckState.Checked


class AlertPointItem(QGraphicsEllipseItem):
    def __init__(self, pos = QPointF(), threshold=50):
        super().__init__(QRectF(-10, -10, 20, 20))
        self.setPos(pos)
        print(pos)
        self.setBrush(QColor(255, 0, 0, 150))
        self.setPen(QPen(Qt.GlobalColor.red, 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.threshold = threshold
        self.points = [pos]
        self.is_active = True
    def serialize(self,width,height):
        return (transform_coords([self.pos()],width,height),"point",self.is_active,self.threshold)

    def deserialize(self,zone,width,height):
        self.points = transform_coords_reverse(zone[0],width,height)
        self.setPos(self.points[0])
        #self.type = zone[1]
        self.is_active = zone[2]
        self.threshold = zone[3]

    def contextMenuEvent(self, event):
        popup = AlertPopupPanel(item=self, threshold_value=self.threshold, is_active=self.is_active)

        popup.move(event.screenPos())
        popup.exec()
        print(self.is_active, self.threshold)



class AlertPolygonItem(QGraphicsPolygonItem):
    def __init__(self, points=None, threshold=50):
        super().__init__()
        if points is None:
            points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
        self.setPolygon(QPolygonF(points))
        self.setBrush(QColor(0, 0, 255, 50))
        self.setPen(QPen(Qt.GlobalColor.blue, 2))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.threshold = threshold
        self.points = points
        self.is_active = True


    def serialize(self,width,height):
        points = [self.mapToScene(self.polygon().value(i)) for i in range(self.polygon().size())]
        return (transform_coords(points,width,height),"area",self.is_active,self.threshold)

    def deserialize(self,zone,width,height):
        self.points = transform_coords_reverse(zone[0],width,height)
        self.setPolygon(QPolygonF(self.points))
        #self.type = zone[1]
        self.is_active = zone[2]
        self.threshold = zone[3]

    def contextMenuEvent(self, event):
        popup = AlertPopupPanel(item=self, threshold_value=self.threshold, is_active=self.is_active)

        popup.move(event.screenPos())
        popup.exec()
        print(self.is_active, self.threshold)

    def contains(self, point):
        return self.polygon().containsPoint(point, Qt.FillRule.OddEvenFill)


class PolygonEditor:
    def __init__(self, scene):
        self.scene = scene
        self.points = []
        self.temp_path = None
        self.first_point = None
        self.double_click_timer = QTimer()
        self.double_click_timer.setInterval(300)
        self.double_click_timer.setSingleShot(True)
        self.double_click_timer.timeout.connect(self.reset_double_click)
        self.waiting_for_double_click = False
        self.vertex_items = []

    def add_point(self, pos):
        if not self.points:
            self.first_point = pos
            self.points.append(pos)
            self.create_temp_path()
            self.add_vertex(pos)
        else:
            # Проверка двойного клика по первой точке
            if (self.waiting_for_double_click and
                    self.is_near_first_point(pos) and
                    len(self.points) >= 3):
                self.finish_polygon()
                return

            self.points.append(pos)
            self.update_temp_path()
            self.add_vertex(pos)

            # Запускаем таймер для проверки двойного клика
            if self.is_near_first_point(pos) and len(self.points) >= 3:
                self.waiting_for_double_click = True
                self.double_click_timer.start()

    def add_vertex(self, pos):
        """Добавляем видимую точку вершины"""
        vertex = QGraphicsEllipseItem(-5, -5, 10, 10)
        vertex.setPos(pos)
        vertex.setBrush(QColor(255, 255, 0, 200))
        vertex.setPen(QPen(Qt.GlobalColor.yellow, 1))
        self.scene.addItem(vertex)
        self.vertex_items.append(vertex)

    def is_near_first_point(self, pos, radius=10):
        if not self.first_point:
            return False
        return ((pos.x()-self.first_point.x())**2+ (pos.y()-self.first_point.y())**2)**0.5 <= radius

    def reset_double_click(self):
        self.waiting_for_double_click = False

    def create_temp_path(self):
        path = QPainterPath()
        path.moveTo(self.points[0])
        self.temp_path = QGraphicsPathItem(path)
        self.temp_path.setPen(QPen(Qt.GlobalColor.green, 2, Qt.PenStyle.DashLine))
        self.scene.addItem(self.temp_path)

    def update_temp_path(self):
        if not self.temp_path or len(self.points) < 2:
            return

        path = QPainterPath()
        path.moveTo(self.points[0])
        for point in self.points[1:]:
            path.lineTo(point)
        self.temp_path.setPath(path)

    def finish_polygon(self):
        if len(self.points) >= 3:
            polygon = AlertPolygonItem(self.points)
            self.scene.addItem(polygon)
        self.cleanup()

    def cancel(self):
        self.cleanup()

    def cleanup(self):
        if self.temp_path:
            self.scene.removeItem(self.temp_path)
            self.temp_path = None
        for vertex in self.vertex_items:
            self.scene.removeItem(vertex)
        self.vertex_items = []
        self.points = []
        self.first_point = None
        self.waiting_for_double_click = False
        self.double_click_timer.stop()


class AlertEditorOverlay(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMouseTracking(True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.current_item = None
        self.drag_mode = False
        self.start_pos = QPointF()
        self.bg_item = None
        self.polygon_editor = PolygonEditor(self.scene)
        self.polygon_mode = False

        self.global_threshold = 50
        self.global_zone_is_active = False

        self.setSceneRect(0, 0, 640, 480)
        self.view_width = 640
        self.view_height = 480

    def set_background_later(self, image: QPixmap):
        QTimer.singleShot(0, lambda: self.set_background(image))

    def set_background(self, image: QPixmap):
        if self.bg_item:
            self.scene.removeItem(self.bg_item)
        if image:
            view_width = self.viewport().width()
            image_width = image.width()
            image_height = image.height()

            scale_factor = view_width / image_width
            scaled_height = int(image_height * scale_factor)
            self.setFixedSize(view_width,scaled_height)
            self.setMinimumSize(view_width,scaled_height)
            self.setMaximumSize(view_width, scaled_height)
            print("New Size: ", view_width, ", ", scaled_height)
            scaled_pixmap = QPixmap(image).scaled(
                view_width,
                scaled_height,
                Qt.AspectRatioMode.KeepAspectRatio
            )

            self.bg_item = self.scene.addPixmap(scaled_pixmap)
            self.bg_item.setZValue(-1)

            # Устанавливаем размер сцены строго по изображению
            self.setSceneRect(QRectF(0, 0, view_width, scaled_height))
            print(self.scene)
            self.width = view_width
            self.height = scaled_height

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = self.viewport().size()
        self.setSceneRect(0, 0, size.width(), size.height())
        self.view_width = size.width()
        self.view_height = size.height()
        # if self.bg_item:
        #    self.bg_item.setPixmap(
        #        self.bg_item.pixmap().scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio))

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.polygon_mode:
            scene_pos = self.mapToScene(event.pos())
            if (self.polygon_editor.waiting_for_double_click and
                    self.polygon_editor.is_near_first_point(scene_pos) and
                    len(self.polygon_editor.points) >= 3):
                self.polygon_editor.finish_polygon()
                # self.polygon_mode = False
        super().mouseDoubleClickEvent(event)
        # self.setRenderHint(QPainter.Antialiasing)

    def mousePressEvent(self, event):
        scene_pos = self.mapToScene(event.pos())

        if event.button() == Qt.MouseButton.LeftButton:
            item = self.scene.itemAt(scene_pos, self.transform())

            if not isinstance(item,(AlertPointItem,AlertPolygonItem)):
                if self.polygon_mode:
                    self.polygon_editor.add_point(scene_pos)
                else:
                    self.current_item = AlertPointItem(scene_pos)
                    self.scene.addItem(self.current_item)
        super().mousePressEvent(event)


def transform_coords(points: QPointF | list[QPointF], width, height) -> list[tuple[int, int]]:
    if isinstance(points, QPointF):
        return [(points.x() / width, points.y() / height)]
    if isinstance(points, list):
        transformed_points = []
        for point in points:
            transformed_points.append((point.x() / width, point.y() / height))
        return transformed_points

def transform_coords_reverse(points, width, height) -> list[QPointF]:
    if isinstance(points, QPointF):
        return [QPointF(points.x() * width, points.y() * height)]
    if isinstance(points, list):
        transformed_points = []
        for point in points:
            transformed_points.append(QPointF(point[0] * width, point[1] * height))
        return transformed_points
class AlertsZonesEditor(QDialog):
    def __init__(self, initial_alerts=None, parent=None, image=None):
        super().__init__(parent)
        self.setWindowTitle("Редактор зон наблюдения")
        self.setMinimumSize(800, 660)

        self.alerts = initial_alerts or []

        self.layout = QVBoxLayout()


        self.editor = AlertEditorOverlay()
        # self.editor.bg_item = image
        self.editor.set_background_later(image)
        self.layout.addWidget(self.editor, 1)

        self.control_panel = QFrame()
        self.control_layout = QHBoxLayout()

        self.control_panel.setLayout(self.control_layout)

        self.polygon_btn = QPushButton("Режим полигона")
        self.polygon_btn.clicked.connect(self.toggle_polygon_mode)
        self.control_layout.addWidget(self.polygon_btn)

        self.clear_btn = QPushButton("Очистить сцену")
        self.clear_btn.clicked.connect(self.clear_scene)
        self.control_layout.addWidget(self.clear_btn)

        self.save_button = QPushButton("Сохранить")
        self.save_button.clicked.connect(self.on_save)
        self.control_layout.addWidget(self.save_button)

        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.clicked.connect(self.reject)
        self.control_layout.addWidget(self.cancel_button)

        #self.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Preferred)
        self.layout.addWidget(self.control_panel)
        self.setLayout(self.layout)



    def load_zones(self,zones):
        scene_width = self.editor.view_width
        scene_height = self.editor.view_height

        for zone  in zones:
            item = None
            if zone[1] == "point":
                item = AlertPointItem()
            elif zone[1] == "area":
                item = AlertPolygonItem()
            item.deserialize(zone,scene_width,scene_height)
            self.editor.scene.addItem(item)
    def keyPressEvent(self, event):
        """Обработка нажатия клавиш"""
        if event.key() == Qt.Key.Key_Delete and self.editor.current_item:
            self.editor.scene.removeItem(self.editor.current_item)
            self.editor.current_item = None
        elif event.key() == Qt.Key.Key_P:
            # Включение/выключение режима рисования полигона
            self.toggle_polygon_mode()

    def toggle_polygon_mode(self):
        self.editor.polygon_mode = not self.editor.polygon_mode
        if self.editor.polygon_mode:
            self.polygon_btn.setStyleSheet("background-color: lightgreen")
        else:
            self.editor.polygon_editor.cancel()
            self.polygon_btn.setStyleSheet("")

    def clear_scene(self):
        self.editor.scene.clear()
        self.editor.polygon_editor.cleanup()

    def export_zones(self):
        scene_width = self.editor.view_width
        scene_height = self.editor.view_height
        zones = []
        for item in self.editor.scene.items():
            if isinstance(item, (AlertPointItem, AlertPolygonItem)):

                zones.append(item.serialize(scene_width,scene_height))

        return zones

    def on_save(self):
        print("on save")
        pass
