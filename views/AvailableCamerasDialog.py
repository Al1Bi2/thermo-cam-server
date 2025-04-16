from PyQt6.QtWidgets import (
    QDialog, QListWidget, QPushButton,
    QVBoxLayout, QListWidgetItem,QDialogButtonBox
)
from PyQt6 import QtGui


class AvailableCamerasDialog(QDialog):
    def __init__(self, cameras: list[list[str]]):
        super().__init__()
        self.setWindowTitle("Доступные камеры")

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        #QBtn = QDialogButtonBox.Ok
        #self.buttonBox = QDialogButtonBox(QBtn)
        #self.add_btn = QPushButton("Добавить выбранные")

        layout = QVBoxLayout()
        layout.addWidget(self.list)
        #layout.addWidget(self.add_btn)


        self._load_cameras(cameras)
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setLayout(layout)

    def _load_cameras(self, cameras):
        for cam_id,camera_name in cameras:
            item = QListWidgetItem(camera_name)
            item.setData(256, cam_id)  # Qt.ItemDataRole.UserRole
            self.list.addItem(item)

    def get_selected(self) -> list[str]:
        return [
            item.data(256)
            for item in self.list.selectedItems()
        ]