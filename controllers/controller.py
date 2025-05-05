# from model import CameraModel
from views.AlertsEditorOverlay import AlertsZonesEditor
from views.AvailableCamerasDialog import AvailableCamerasDialog
from views.view import SettingsView
from models.model import Esp32Device,Esp32Manager, AlertZone
from views.view import MainWindow
from PyQt6.QtWidgets import (QMessageBox)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer
from controllers.network import MqttController
from controllers.video import  ProcessingController,VideoProcessController,VideoProcessWorker
import struct

class DeviceConnectionManager(QObject):
    device_discovered = pyqtSignal(str,str)
    device_acknowledged = pyqtSignal(str)
    device_activated = pyqtSignal(str)
    device_deactivated = pyqtSignal(str)
    device_disconnected = pyqtSignal(str)

    request_start = pyqtSignal(str)
    request_ack = pyqtSignal(str)
    request_stop = pyqtSignal(str)

    def __init__(self, model: Esp32Manager, mqtt: MqttController):
        super().__init__()
        self.model = model
        self.mqtt = mqtt

    def handle_discovery(self,payload : str):
        print(payload)
        device_id, ip = payload.split(":")
        device = self.model.get_device(device_id)
        if not device:
            device = Esp32Device(id=device_id, ip=ip, name=f"Camera-{device_id}", connected=True, active=False)
            self.mqtt.subscribe(f"{device_id}/status",1)
            self.mqtt.subscribe(f"{device_id}/amg8833")
            self.model.add_device(device)
            self.device_discovered.emit(device_id, ip)
        else:
            device.ip = ip
            device.connected = True
            device.active = False
        self.request_ack.emit(device_id)
        self.device_acknowledged.emit(device_id)

    def handle_status(self, device_id: str, status: str):
        device = self.model.get_device(device_id)
        if not device:
            return

        prev_active = device.active

        if status == "active":
            device.active = True
            #if not prev_active:
            self.device_activated.emit(device_id)

        elif status == "connected":
            #if prev_active:
            device.active = False
            self.device_deactivated.emit(device_id)

        elif status == "offline":
            device.connected = False
            device.active = False
            self.device_disconnected.emit(device_id)

    def request_start_device(self, device_id: str):
        self.request_start.emit(device_id)

    def request_stop_device(self, device_id: str):
        self.request_stop.emit(device_id)

class DeviceManager(QObject):
    def __init__(self, model: Esp32Manager, mqtt_client:MqttController):
        super().__init__()
        self.model = model
        self.connection = DeviceConnectionManager(model,mqtt_client)
        self.streams = VideoProcessController()
        self.processor = ProcessingController()
        self.mqtt = mqtt_client

        # Bind stream output to processor
        self.streams.frame_ready.connect(self.processor.handle_frame)

        # Bind processor output to GUI (connect in GuiController)
        #self.processor.overlay_ready.connect(...)

        # Handle activation
        self.connection.device_activated.connect(self._on_device_activated)
        self.connection.device_deactivated.connect(self._on_device_deactivated)
        self.connection.device_disconnected.connect(self._on_device_disconnected)

        # MQTT send commands
        self.connection.request_start.connect(lambda id: self.mqtt.publish(f"{id}/control", "start"))
        self.connection.request_stop.connect(lambda id: self.mqtt.publish(f"{id}/control", "stop"))
        self.connection.request_ack.connect(lambda id: self.mqtt.publish(f"{id}/control", "ack-connect"))

    def handle_mqtt(self, topic: str, payload: bytes):
        if topic == "discovery":
            self.connection.handle_discovery(payload.decode())
        elif topic.endswith("/status"):
            device_id = topic.split("/")[0]
            self.connection.handle_status(device_id, payload.decode())
            print(device_id,payload.decode())
        elif topic.endswith("/amg8833"):
            device_id = topic.split("/")[0]
            floats = struct.unpack('<64f', payload)
            matrix = [floats[i * 8:(i + 1) * 8] for i in range(8)]
            self.processor.update_matrix(device_id, matrix)

    def _on_device_activated(self, device_id: str):
        device = self.model.get_device(device_id)
        if device:
            self.streams.start_stream(device.id, device.ip)

    def _on_device_deactivated(self, device_id: str):
        self.streams.stop_stream(device_id)
        self.model.get_device(device_id).active=False


    def _on_device_disconnected(self, device_id: str):
        self.streams.stop_stream(device_id)
        self.model.get_device(device_id).active=False
        self.model.get_device(device_id).connected = False
        self.model.remove_device(device_id)


    def stop_all(self):
        self.streams.stop_all_streams()

    def start_device(self, device_id: str):
        self.connection.request_start_device(device_id)

    def stop_device(self, device_id: str):
        self.connection.request_stop_device(device_id)

class GuiController:
    exit = pyqtSignal()
    def __init__(self, model: Esp32Manager,view: MainWindow, device_manager:DeviceManager):

        self.model = model
        self.view = view
        self.devices = device_manager

        self.view.settings_button.clicked.connect(self._open_settings)
        self.view.add_camera_button.clicked.connect(self._open_available_cameras)
        self.view.request_camera_remove.connect(self._handle_camera_click)

        self.view.request_editor.connect(self._open_alert_editor)

        self.devices.processor.overlay_ready.connect(self.view.update_camera_frame)
        self.view.exit.connect(self.stop)

    def _handle_camera_click(self, camera_id):
        if self.view.expanded_camera_id == camera_id:
            QMessageBox.warning(
                self.view,
                "Удаление невозможно",
                "Нельзя удалить развернутую камеру. Сначала сверните её."
            )
            return
        confirm = QMessageBox.question(
            self.view,
            "Подтверждение удаления",
            f"Удалить камеру {camera_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.devices.stop_device(camera_id)
            self.model.disconnect_device(camera_id)
            self.view.remove_camera_widget(camera_id)


    def _open_available_cameras(self):
        cameras = [(d.id, d.name) for d in self.model.get_available_devices()]
        dialog = AvailableCamerasDialog(cameras)
        if dialog.exec():
            for device_id in dialog.get_selected():
                self.model.get_device(device_id).active = True
                self.view.add_camera_widget(device_id, f"Cam-{device_id}")
                self.devices.start_device(device_id)

    def _open_settings(self):
        settings_view = SettingsView()
        settings_view.url_input.setText("http://default-camera-url.com")

        def save_and_close():
            new_url = settings_view.url_input.text()
            # TODO: save to device config
            settings_view.close()

        settings_view.save_btn.clicked.connect(save_and_close)
        settings_view.exec()

    def stop(self):
        self.devices.mqtt.publish("server/status","offline",1)
        #self.devices.mqtt.disconnect()

        self.devices.stop_all()

    def _open_alert_editor(self,device_id):
        device = self.model.get_device(device_id)
        if device:
            zones = []
            for zone in device.alert_zones:
                zones.append(zone.serialize())
            image = self.view.camera_widgets[device_id].pixmap
            alert_editor = AlertsZonesEditor(image=image)
            QTimer.singleShot(0, lambda : alert_editor.load_zones(zones))
            alert_editor.exec()
            alerts_zones = []
            for zone in alert_editor.export_zones():
                alert_zone = AlertZone(
                    id="some_id",  # Required field
                    type="point",  # Required field (default if you don't have it)
                    coords=[],  # Empty, will be filled by deserialize()
                    threshold=0.0  # Default value
                )
                alert_zone.deserialize(zone)
                alerts_zones.append(alert_zone)
            device.alert_zones.clear()
            device.alert_zones = alerts_zones


