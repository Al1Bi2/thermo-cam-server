import json
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Dict, Literal, List

from PyQt6.QtCore import QPointF


class DeviceState(Enum):
    INIT = auto()
    OFFLINE = auto()
    AVAILABLE = auto()
    ACTIVE = auto()
    ERROR = auto()

    def __str__(self):
        return self.name


TRANSITIONS = {
    (DeviceState.INIT, DeviceState.OFFLINE): "ack",
    (DeviceState.OFFLINE, DeviceState.AVAILABLE): "connect",
    (DeviceState.AVAILABLE, DeviceState.ACTIVE): "activate",
    (DeviceState.ACTIVE, DeviceState.ERROR): "fail",
    (DeviceState.ERROR, DeviceState.OFFLINE): "reset",
}


@dataclass
class ProcessingSettings:
    overlay_mode: str = "both"
    thermo_alpha: int = 50
    video_filter: str = "gray"
    filter_intensity: int = 100
    heatmap_colormap: str = "jet"


@dataclass
class AlertZone:
    type: Literal["point", "area", "global"] = "global"
    coords : List[QPointF] = field(default_factory=lambda: [QPointF(0, 0)])
    threshold: float = 50
    color: str = "red"
    enabled: bool = True

    #id: int = 0 # Поле не передается в __init__, но будет доступно
    #_id_counter: int = field(default=0, init=False, repr=False, compare=False)  # Счетчик (скрытый)

    #def __post_init__(self):
     #   AlertZone._id_counter += 1
    #    self.id = AlertZone._id_counter
    def serialize(self):
        zone_dict = asdict(self)
        zone_dict["coords"] = [[p.x(), p.y()] for p in zone_dict["coords"]]
        return zone_dict


@dataclass
class Esp32Device:
    id: str
    ip: str = "127.0.0.1"
    name: str = None
    state: DeviceState = DeviceState.OFFLINE
    # connected: bool = True
    # active: bool = False
    alert_zones: List[AlertZone] = field(default_factory=lambda: [AlertZone(type="global", enabled=False)])
    processing_settings: ProcessingSettings = field(default_factory=ProcessingSettings)

    def __post_init__(self):
        self.name = self.name or f"Camera-{self.id}"

    def to_dict(self):
        data = asdict(self)
        data.pop("ip")

        data["state"] = str(self.state)
        data["alert_zones"] = [zone.serialize() for zone in self.alert_zones]
        return data

    @classmethod
    def from_dict(cls, data: dict, ip: str = "127.0.0.1"):
        data["ip"] = ip
        state = DeviceState.OFFLINE
        data["state"] = state
        data["processing_settings"] = ProcessingSettings(**data["processing_settings"])
        alert_zones = []
        has_global_zone = False
        for zone_data in data.pop("alert_zones", []):
            zone_data["coords"] = [QPointF(x, y) for [x, y] in zone_data["coords"]]
            zone = AlertZone(**zone_data)
            alert_zones.append(zone)
            if zone.type == "global":
                has_global_zone = True
        if not has_global_zone:
            alert_zones.append(AlertZone(type="global",enabled=False))
        data["alert_zones"] = alert_zones
        return cls(**data)

    def is_connected(self):
        return self.connected

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False


class Esp32Manager:
    SETTINGS_FILE = "camera_settings.json"

    def __init__(self):
        self.devices: Dict[str, Esp32Device] = {}

    def update_state(self, device_id: str, target_state: DeviceState):
        dev = self.devices.get(device_id)
        if not dev:
            return False
        key = (dev.state, target_state)
        if key in TRANSITIONS:
            action = TRANSITIONS[key]
            # Выполняем действие, логгируем, отправляем MQTT, и т.д.
            dev.update_state(target_state)
            self.deviceStateChanged.emit(device_id, target_state)
            print(f"[FSM] {dev.state} -> {target_state} via '{action}'")
            return True
        else:
            print(f"[FSM] Invalid transition: {dev.state} → {target_state}")
            return False

    def save_devices(self):

        data = {dev_id: device.to_dict() for dev_id, device in self.devices.items()}
        with open(Esp32Manager.SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def load_devices() -> Dict[str, Esp32Device]:
        try:
            with open(Esp32Manager.SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {}

        return {
            dev_id: Esp32Device.from_dict(dev_data)
            for dev_id, dev_data in data.items()
        }

    @staticmethod
    def get_device_status_summary(devices: Dict[str, Esp32Device]) -> str:
        """Generate human-readable status report"""
        return "\n".join(
            f"{dev.id}: {dev.state.name} (IP: {dev.ip})"
            for dev in devices.values()
        )

    def connect_device(self, id):
        if device := self.devices.get(id):
            device.active = True
            return True
        return False

    def disconnect_device(self, id):
        if device := self.devices.get(id):
            device.active = False
            return True
        return False

    def add_device(self, new_device: Esp32Device):
        if not self.get_device(new_device.id):
            self.devices[new_device.id] = new_device

    def remove_device(self, id):
        self.devices.pop(id)

    def get_connected_devices(self):
        return list(device for device in self.devices.values() if (device.state == DeviceState.ACTIVE))

    def get_available_devices(self):
        return list(device for device in self.devices.values() if (device.state == DeviceState.AVAILABLE))

    def get_device(self, id) -> Esp32Device | None:
        return self.devices.get(id)

    def get_all(self) -> list[Esp32Device]:
        return list(self.devices.values())


if __name__ == "__main__":
    import os

    # Тестовые данные
    test_zones = [
        AlertZone(type="point", coords=[QPointF(10, 20)], color="green"),
        AlertZone(type="area", coords=[QPointF(0, 0), QPointF(100, 100)], threshold=75)
    ]
    test_settings = ProcessingSettings(thermo_alpha=80, heatmap_colormap="jet")

    # 1. Создаем тестовые устройства
    devices = {
        "cam1": Esp32Device(
            id="cam1",
            ip="192.168.1.100",
            name="Test Camera",
            state=DeviceState.ACTIVE,
            alert_zones=test_zones,
            processing_settings=test_settings
        ),
        "cam2": Esp32Device(id="cam2", ip="192.168.1.101")
    }
    TEST_FILE = "test_settings.json"
    # 2. Сохраняем во временный файл
    Esp32Manager.SETTINGS_FILE = TEST_FILE
    Esp32Manager.save_devices(devices)
    print(f"\nСохраненные данные:\n{open(TEST_FILE).read()}")

    # 3. Загружаем обратно
    loaded_devices = Esp32Manager.load_devices()

    # 4. Проверяем корректность загрузки
    print("\nРезультаты проверки:")
    for dev_id, device in loaded_devices.items():
        print(f"\nУстройство {dev_id}:")
        print(f"IP: {device.ip}")
        print(f"Состояние: {device.state}")
        print(f"Имя: {device.name}")
        print(f"Зоны: {len(device.alert_zones)} шт.")
        print(f"Настройки: {device.processing_settings}")

        # Проверка сохранения QPointF
        if device.alert_zones:
            print("Координаты первой зоны:",
                  [[p.x(), p.y()] for p in device.alert_zones[1].coords])

    # 5. Проверка перехода состояний
    cam1 = loaded_devices["cam1"]
    print("\nТест перехода состояний:")
    print(f"Исходное состояние: {cam1.state}")
    cam1.update_state(DeviceState.ERROR)
    print(f"После ошибки: {cam1.state}")
    cam1.update_state(DeviceState.ACTIVE)
    print(f"При повторном подключении: {cam1.state} ")

    # Удаляем временный файл
    # os.remove(TEST_FILE)
