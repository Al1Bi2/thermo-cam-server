from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QSlider, QComboBox, QPushButton, QHBoxLayout, QListWidget, \
    QWidget, QAbstractItemView, QSizePolicy, QScrollArea, QLineEdit, QDialogButtonBox
from PyQt6.QtCore import Qt, QSize, QObject
from PyQt6.QtGui import QColor, QPainter



class DeviceSettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Основные настройки устройства")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Название:"))
        self.name_input = QLineEdit("{test}")

        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("IP-адрес: (только для чтения)"))
        self.ip_label = QLabel("192.168.x.x")
        layout.addWidget(self.ip_label)

        btns = QHBoxLayout()
        btns.addStretch()
        btns.addWidget(QPushButton("OK"))
        layout.addLayout(btns)

        self.setLayout(layout)


BASE_DIALOG_SIZE = QSize(400, 300)



class ProcessingSettingsDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Постобработка")
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(QLabel("Канал отображения:"))
        self.overlay_mode = QComboBox()
        self.overlay_mode.addItem("Видео","video")
        self.overlay_mode.addItem("Тепловое", "thermal")
        self.overlay_mode.addItem("Оба", "both")
        layout.addWidget(self.overlay_mode)


        layout.addWidget(QLabel("Прозрачность тепловизора:"))
        blend_layout = QHBoxLayout()
        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setMinimum(0)
        self.alpha_slider.setMaximum(100)
        self.alpha_slider.setValue(30)
        blend_layout.addWidget(self.alpha_slider)

        self.slider_value = QLabel("30")
        self.slider_value.setFixedWidth(self.slider_value.fontMetrics().horizontalAdvance("00000"))
        blend_layout.addWidget(self.slider_value)

        self.alpha_slider.valueChanged.connect(lambda v: self.slider_changed(v,self.slider_value))
        layout.addLayout(blend_layout)

        layout.addWidget(QLabel("Вид тепловой карты:"))
        self.heatmap_mode = QComboBox()
        self.heatmap_mode.addItem("Hot", "hot")
        self.heatmap_mode.addItem("Jet", "jet")
        self.heatmap_mode.addItem("HSV", "hsv")
        self.heatmap_mode.addItem("Inferno", "inferno")
        layout.addWidget(self.heatmap_mode)

        layout.addWidget(QLabel("Фильтр видео:"))
        self.video_filter = QComboBox()
        self.video_filter.addItem("Ничего", "none")
        self.video_filter.addItem("Серый", "gray")
        self.video_filter.addItem("Выделение краёв", "edges")
        layout.addWidget(self.video_filter)

        filter_slider_layout = QHBoxLayout()
        self.filter_slider = QSlider(Qt.Orientation.Horizontal)
        self.filter_slider.setMinimum(0)
        self.filter_slider.setMaximum(100)
        self.filter_slider.setValue(30)

        filter_slider_layout.addWidget(self.filter_slider)
        self.filter_value = QLabel("30")
        self.filter_value.setFixedWidth(self.filter_value.fontMetrics().horizontalAdvance("00000"))
        filter_slider_layout.addWidget(self.filter_value)
        self.filter_slider.valueChanged.connect(lambda v: self.slider_changed(v, self.filter_value))
        layout.addLayout(filter_slider_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)
        self.video_filter.currentIndexChanged.connect(self.handle_filter_change)

    def load_values(self, settings: dict):
        self.overlay_mode.setCurrentIndex(self.overlay_mode.findData(settings["overlay_mode"]))
        self.alpha_slider.setValue(settings["thermo_alpha"])
        self.video_filter.setCurrentIndex(self.video_filter.findData(settings["video_filter"]))
        self.filter_slider.setValue(settings["filter_intensity"])
        self.heatmap_mode.setCurrentIndex(self.heatmap_mode.findData(settings["heatmap_colormap"]))

    def export_values(self) -> dict:
        return {
            "overlay_mode": self.overlay_mode.currentData(),
            "thermo_alpha": self.alpha_slider.value(),
            "video_filter": self.video_filter.currentData(),
            "filter_intensity": self.filter_slider.value(),
            "heatmap_colormap": self.heatmap_mode.currentData()
        }

    def slider_changed(self, value, item):
        item.setText(str(value))

    def handle_filter_change(self,index):
        if self.video_filter.currentData() == "none":
            self.filter_slider.setEnabled(False)
        else:
            self.filter_slider.setEnabled(True)


if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dlg = DeviceSettingsDialog()  # или любой другой
    dlg.show()
    sys.exit(app.exec())