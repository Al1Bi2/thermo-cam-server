import sys
from PyQt6.QtWidgets import QApplication
from controllers.controller import  DeviceManager,GuiController
from controllers.network import ZeroconfService, MqttController
from views.view import MainWindow
from models.model import Esp32Device,Esp32Manager


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Model
    mdns = ZeroconfService()
    mdns.start()

    model = Esp32Manager()
    model.add_device(Esp32Device("1"))
    model.add_device(Esp32Device("2"))
    model.add_device(Esp32Device("3"))
    view = MainWindow()
    mqtt = MqttController(broker_host="192.168.0.5", broker_port=1883)
    mqtt.start()
    device_manager = DeviceManager(model, mqtt)
    controller = GuiController(model, view, device_manager)

    mqtt.mqtt_message_recieved.connect(device_manager.handle_mqtt)

    # Запуск
    view.show()

    sys.exit(app.exec())