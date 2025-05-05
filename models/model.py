from dataclasses import dataclass
from typing import Dict, Literal


@dataclass
class AlertZone:
    id: str
    type: Literal["point", "area", "global"]
    coords: list[tuple[int, int]]
    threshold: float
    color: str = "red"
    enabled: bool = True

    def serialize(self) -> tuple[list[tuple[int,int]],str,bool,float]:
        return (self.coords,self.type,self.enabled,self.threshold)

    def deserialize(self,zone):
        self.coords = zone[0]
        self.type = zone[1]
        self.enabled = zone[2]
        self.threshold = zone[3]

@dataclass
class Esp32Device:
    def __init__(self, id, ip="127.0.0.1",name=None,connected = True, active = False):
        self.id = id
        self.ip = ip
        self.name = name if name is not None else "Camera-"+id
        self.connected = connected
        self.active = active
        self.alert_zones : list[AlertZone] = []

    def is_connected(self):
        return self.connected
    def connect(self):
        self.connected=True

    def disconnect(self):
        self.connected=False


class Esp32Manager:
    def __init__(self):

        self.devices : Dict[str,Esp32Device] = {}

    def connect_device(self,id):
        if device := self.devices.get(id):
            device.active = True
            return True
        return False
    def disconnect_device(self,id):
        if device := self.devices.get(id):
            device.active = False
            return True
        return False
    def add_device(self,new_device:Esp32Device):
        if not self.get_device(new_device.id):
            self.devices[new_device.id] = new_device
    def remove_device(self,id):
        self.devices.pop(id)

    def get_connected_devices(self):
        return list(device for device in self.devices.values() if (device.connected==True and device.active==True))
    def  get_available_devices(self):
        return list(device for device in self.devices.values() if (device.connected==True and device.active==False))

    def get_device(self, id) -> Esp32Device | None:
        return self.devices.get(id)
    def get_all(self) -> list[Esp32Device]:
        return list(self.devices.values())
