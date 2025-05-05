import sys

from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QDialog,
    QLineEdit, QVBoxLayout,QGridLayout, QScrollArea, QSizePolicy, QMenu, QStyle
)
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QThread, pyqtSignal
from views.AlertsEditorOverlay import AlertsZonesEditor
import math
CAMERA_WIDGET_DEFAULT_STYLE = "border: 1px double black; padding: 5px; margin 5px"
CAMERA_WIDGET_EXPANDED_STYLE = "border: 3px solid black; padding: 15px; margin 20px"


class CameraWidget(QLabel):

    request_fullscreen = pyqtSignal(str)  # camera_id
    request_remove = pyqtSignal(str)      # camera_id
    request_settings = pyqtSignal(str)    # camera_id
    request_alerts_editor = pyqtSignal(str)
   # camera_id

    def __init__(self,cam_id,camera_name):
        super().__init__()
        self.setText(f"{camera_name}\nID: {cam_id}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("border: 1px solid black; padding: 5px; margin 5px")
        self.setMinimumSize(400,200)
        self.pixmap = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEvent)

        self.cam_id = cam_id
        self.camera_name = camera_name
        self.expanded = False

    def contextMenuEvent(self, pos):
        menu = QMenu(self)
        style = self.style()


        max_screen_icon = QStyle.StandardPixmap.SP_TitleBarMaxButton if self.expanded \
            else QStyle.StandardPixmap.SP_TitleBarNormalButton
        fullscreen_action = menu.addAction(self.style().standardIcon(max_screen_icon),"На весь экран")
        fullscreen_action.triggered.connect(lambda: self.request_fullscreen.emit(self.cam_id))

        menu.addSeparator()

        settings_action = menu.addAction(  style.standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView),"Настройки")
        settings_action.triggered.connect(lambda: self.request_settings.emit(self.cam_id))

        remove_action = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon),"Удалить")
        remove_action.triggered.connect(lambda: self.request_remove.emit(self.cam_id))

        alerts_editor_action = menu.addAction(style.standardIcon(QStyle.StandardPixmap.SP_DriveNetIcon), "Редактировать зоны")
        alerts_editor_action.triggered.connect(lambda: self.request_alerts_editor.emit(self.cam_id))

        menu.exec(self.mapToGlobal(pos))

    def handle_action(self, camera_id, action_num):
        print(f"Обработка действия {action_num} для камеры {camera_id}")
        if action_num == 3:
            # Логика удаления камеры
            pass
    def update_frame(self, frame):
        height, width, channel = frame.shape
        bytes_per_line = 3 * width
        qimg = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_BGR888)
        self.pixmap = QPixmap.fromImage(qimg)
        self.pixmap_update()

    def pixmap_update(self,a:str = ""):
        if self.pixmap:
            #print(a, self.size())
            self.setPixmap(self.pixmap.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio))


class MainWindow(QMainWindow):
    request_camera_remove = pyqtSignal(str)
    exit = pyqtSignal()
    expanded_camera_id = None
    request_editor = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.camera_widgets: dict[str,CameraWidget] = {}  # Store widgets by camera_id
        self.camera_counter = 0
        self.current_grid_dimensions = (0, 0)  # (rows, cols)

        self.setWindowTitle("Камеры")
        self.showFullScreen()

        # Создаем основной контейнер
        self.container = QWidget(self)
        self.setCentralWidget(self.container)

        # Создаем QScrollArea для прокрутки камеры
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)

        # Создаем QGridLayout для размещения камер
        self.grid_layout = QGridLayout()

        self.grid_layout.setSpacing(0)

        # Оборачиваем layout в scroll_area
        scroll_content = QWidget(self)
        scroll_content.setLayout(self.grid_layout)
        self.scroll_area.setWidget(scroll_content)

        # Кнопка для добавления новой камеры
        self.add_camera_button = QPushButton("Добавить камеру", self)
        #self.add_camera_button.clicked.connect(self._emit_add_camera)

        # Кнопки для управления настройками (например, изменение сетки)
        self.settings_button = QPushButton("Настройки", self)
        #self.settings_button.clicked.connect(self._emit_settings)

        # Нижний вертикальный layout для кнопок
        bottom_layout = QVBoxLayout()
        bottom_layout.addWidget(self.add_camera_button)
        bottom_layout.addWidget(self.settings_button)
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignBottom)  # Прикрепляем кнопки к низу

        # Главный вертикальный layout для контейнера
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.scroll_area)
        main_layout.addLayout(bottom_layout)  # Ставим кнопки внизу

        self.container.setLayout(main_layout)

        # Счётчик камер
        self.camera_counter = 0



    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.exit.emit()
                self.close()

    def toggle_chosen_camera(self, camera_id):
        self.expanded_camera_id=camera_id if not  self.expanded_camera_id else None
        self.update_grid_layout()
        if self.expanded_camera_id:
            self.camera_widgets[camera_id].setStyleSheet(CAMERA_WIDGET_EXPANDED_STYLE)
        else:
            self.camera_widgets[camera_id].setStyleSheet(CAMERA_WIDGET_DEFAULT_STYLE)
        #self.camera_widgets[camera_id].pixmap_update("TOGGLE")

    def add_camera_widget(self, camera_id,camera_name):
        if camera_id in self.camera_widgets:
            return

        widget = CameraWidget(camera_id,camera_name)
        #widget.mousePressEvent = lambda e,c_id = camera_id:self._on_camera_click(e,c_id)
        widget.request_fullscreen.connect(self.toggle_fullscreen)
        widget.request_remove.connect(self.request_camera_remove)
        widget.request_settings.connect(self.show_camera_settings)
        widget.request_alerts_editor.connect(self.request_editor)

        self.camera_widgets[camera_id] = widget
        self.camera_counter += 1

        self.update_grid_layout()


    def toggle_fullscreen(self,camera_id):
        self.camera_widgets.get(camera_id).expanded = not self.camera_widgets.get(camera_id).expanded
        self.toggle_chosen_camera(camera_id)

    def remove_camera(self, camera_id):
        self.remove_camera_widget(camera_id)

    def show_camera_settings(self, camera_id):
        pass
        #settings_dialog = SettingsView()
        #settings_dialog.exec()
    def show_alert_editor(self, camera_id,zones):
        image = self.camera_widgets[camera_id].pixmap
        alert_editor = AlertsZonesEditor(image=image)

        alert_editor.load_zones(zones)
        alert_editor.exec()
        return alert_editor.export_zones()
    def _on_camera_click(self,event,camera_id):
        self.camera_clicked.emit(camera_id,event.button())

    def update_grid_layout(self):
        for i in reversed(range(self.grid_layout.count())):
            self.grid_layout.itemAt(i).widget().setParent(None)

        for row in range(self.current_grid_dimensions[0]):
            self.grid_layout.setRowStretch(row, 0)
        for col in range(self.current_grid_dimensions[1]):
            self.grid_layout.setColumnStretch(col, 0)

        if self.expanded_camera_id:
            widget = self.camera_widgets[self.expanded_camera_id]
            self.grid_layout.addWidget(widget,0,0)
        else:
            rows, cols = self.calculate_grid_size(self.camera_counter)
            self.current_grid_dimensions = (rows,cols)



            for idx, (camera_id,widget) in enumerate(self.camera_widgets.items()):
                #widget.pixmap_update("FORCED UPDATE")
                row = idx % rows
                col = idx // rows
                self.grid_layout.addWidget(widget, row, col)
                self.grid_layout.setColumnStretch(col, 1)
                self.grid_layout.setRowStretch(row, 1)

    def remove_camera_widget(self,camera_id):
        if camera_id not in self.camera_widgets:
            return
        widget = self.camera_widgets.pop(camera_id)
        widget.deleteLater()
        self.camera_counter -= 1
        self.update_grid_layout()

    def update_camera_frame(self, camera_id: str, frame):
        widget = self.camera_widgets.get(camera_id)
        if widget:
            widget.update_frame(frame)

    def calculate_grid_size(self,num_cameras):
        if num_cameras<=0:
            return 0,0
        if num_cameras <= 9:
            cols = math.ceil(math.sqrt(num_cameras))
            rows = math.ceil(num_cameras / cols)
        else:
            rows = 3
            cols = (num_cameras + rows - 1) // rows
        return rows, cols


class SettingsView(QDialog):
    """Окно настроек камеры."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Настройки камеры")
        self.url_input = QLineEdit(self)
        self.save_btn = QPushButton("Сохранить", self)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("URL камеры:"))
        layout.addWidget(self.url_input)
        layout.addWidget(self.save_btn)
        self.setLayout(layout)
