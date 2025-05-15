# from model import CameraModel
from views.AlertsEditorOverlay import AlertsZonesEditor
from views.AvailableCamerasDialog import AvailableCamerasDialog
from views.Settings import ProcessingSettingsDialog
from views.view import SettingsView, WidgetAlertZone, AlertZoneDTO
from models.model import Esp32Device, Esp32Manager, AlertZone, ProcessingSettings, DeviceState
from views.view import MainWindow
from PyQt6.QtWidgets import (QMessageBox, QDialog)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QThread
from controllers.network import MqttController
from controllers.video import  ProcessingController,VideoProcessController,VideoProcessWorker
import struct
from dataclasses import asdict



class DeviceManager(QObject):
    request_start = pyqtSignal(str)
    request_ack = pyqtSignal(str)
    request_stop = pyqtSignal(str)
    def __init__(self, model: Esp32Manager, mqtt_client:MqttController):
        super().__init__()
        self.model = model

        self.streams = VideoProcessController()
        self.mqtt = mqtt_client

        self.processing_thread = QThread()

        self.processor = ProcessingController(model)

        self.processor.moveToThread(self.processing_thread)

        self.processing_thread.start()

        #connect ready
        self.streams.frame_ready.connect(self.processor.handle_frame)

        # Handle activation
        #self.connection.device_activated.connect(self._on_device_activated)
        #self.connection.device_deactivated.connect(self._on_device_deactivated)
        #self.connection.device_disconnected.connect(self._on_device_disconnected)

        # MQTT send commands
        self.request_start.connect(lambda id: self.mqtt.publish(f"{id}/control", "start"))
        self.request_stop.connect(lambda id: self.mqtt.publish(f"{id}/control", "stop"))
        self.request_ack.connect(lambda id: self.mqtt.publish(f"{id}/control", "ack-connect"))


    def handle_mqtt(self, topic: str, payload: bytes):

        if topic == "discovery":
            self.handle_discovery(payload.decode())
        elif topic.endswith("/status"):
            device_id = topic.split("/")[0]
            self.handle_status(device_id, payload.decode())
            print(device_id,payload.decode())
        elif topic.endswith("/amg8833"):
            device_id = topic.split("/")[0]
            floats = struct.unpack('<64f', payload)
            matrix = [floats[i * 8:(i + 1) * 8] for i in range(8)]
            self.processor.update_matrix(device_id, matrix)

    def handle_status(self, device_id: str, status: str):
        device = self.model.get_device(device_id)
        if not device:
            return

        prev_active = device.active

        if status == "active":
            device.state = DeviceState.ACTIVE
            #if not prev_active:
            self._on_device_activated(device_id)

        elif status == "connected":
            #if prev_active:
            device.state = DeviceState.AVAILABLE
            self._on_device_deactivated(device_id)

        elif status == "offline":
            device.state = DeviceState.OFFLINE
            self._on_device_disconnected(device_id)
    def handle_discovery(self,payload : str):
        print(payload)
        device_id, ip = payload.split(":")
        device = self.model.get_device(device_id)
        if not device :
            device = Esp32Device(id=device_id, ip=ip, name=f"Camera-{device_id}", state=DeviceState.AVAILABLE)

            self.model.add_device(device)

        else:
            device.ip = ip
            device.state = DeviceState.AVAILABLE
        self.mqtt.subscribe(f"{device_id}/status",1)
        self.mqtt.subscribe(f"{device_id}/amg8833")
        self.request_ack.emit(device_id)


    def _on_device_activated(self, device_id: str):
        device = self.model.get_device(device_id)
        self.processor.processing_settings_changed.emit(device_id, asdict(device.processing_settings))
        if device:
            self.streams.start_stream(device.id, device.ip)

    def _on_device_deactivated(self, device_id: str):
        self.streams.stop_stream(device_id)



    def _on_device_disconnected(self, device_id: str):
        self.streams.stop_stream(device_id)
        self.model.save_devices()


    def stop_all(self):
        self.streams.stop_all_streams()

    def start_device(self, device_id: str):
        self.request_start.emit(device_id)

    def stop_device(self, device_id: str):
        self.request_stop.emit(device_id)

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
        self.view.request_camera_settings.connect(self._open_camera_settings)

        self.devices.processor.overlay_ready.connect(self.view.update_camera_frame)
        self.devices.processor.temperature_changed.connect(self.view.update_temperature_points)
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
                self.devices.start_device(device_id)
                self.view.add_camera_widget(device_id, f"Cam-{device_id}")
                self.view.camera_widgets[device_id].set_zones(
                    [AlertZoneDTO(**asdict(zone)) for zone in self.model.devices[device_id].alert_zones if zone.enabled] )



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
            zones_dict = [asdict(zone) for zone in device.alert_zones]
            image = self.view.camera_widgets[device_id].pixmap
            alert_editor = AlertsZonesEditor(image=image)
            QTimer.singleShot(0, lambda : alert_editor.load_zones(zones_dict))
            alert_editor.exec()
            alerts_zones = []
            widget_alerts_zones = []
            for zone in alert_editor.export_zones():
                alert_zone = AlertZone(**zone)
                alerts_zones.append(alert_zone)
            device.alert_zones.clear()
            device.alert_zones = alerts_zones
            self.devices.processor.alert_zones_changed.emit(device_id, alerts_zones)
            self.model.save_devices()

            self.view.camera_widgets[device_id].set_zones([AlertZoneDTO(**zone)  for zone in alert_editor.export_zones() if zone["enabled"]])


    def _open_camera_settings(self,device_id):
        device = self.model.get_device(device_id)
        if device:
            processing_settings = asdict(device.processing_settings)
            settings_dialog = ProcessingSettingsDialog()
            settings_dialog.load_values(processing_settings)
            if settings_dialog.exec() == QDialog.DialogCode.Accepted:
                new_processing_settings = settings_dialog.export_values()
                device.processing_settings = ProcessingSettings(**new_processing_settings)
                self.devices.processor.processing_settings_changed.emit(device_id,new_processing_settings)
                self.model.save_devices()

