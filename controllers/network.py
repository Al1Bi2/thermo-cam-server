
from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal
import socket
import cv2
import paho.mqtt.client as mqtt
import threading
from zeroconf import Zeroconf, ServiceBrowser, ServiceListener, ServiceInfo
import struct
import time

class MqttController(QObject):
    mqtt_message_recieved = pyqtSignal(str,bytes) #topic, payload
    device_discovered = pyqtSignal(str,str) #device_id, ip

    def __init__(self,broker_host,broker_port):
        super().__init__()
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = "rmuser"
        self.password = "pass"
        self.mqtt_id = "server"
        self.discovery_topic = "discovery"
        self.mqtt_client: mqtt.Client | None = None

    def start(self):
        self.mqtt_client = mqtt.Client(client_id=self.mqtt_id,callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.username_pw_set(self.username,self.password)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.will_set("server/status", "offline", qos=1)
        self.mqtt_client.connect(self.broker_host, self.broker_port, 60)
        threading.Thread(target=self.mqtt_client.loop_forever, daemon=True).start()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to MQTT Broker with code {reason_code}")
        self.mqtt_client.subscribe(self.discovery_topic)

    def on_message(self, client, userdata, message):
        self.mqtt_message_recieved.emit(message.topic,message.payload)
    def publish(self,topic, payload, qos = 0):
        self.mqtt_client.publish(topic,payload,qos)

    def subscribe(self,topic, qos = 0):
        self.mqtt_client.subscribe(topic,qos)

    def unsubscribe(self,topic):
        self.mqtt_client.unsubscribe(topic)
class ZeroconfService:
    def __init__(self):
        self.service_name = "MyThermoServer._http._tcp.local."
        self.service_type = "_http._tcp.local."
        self.port = 1883  # The port your service runs on

        # Get local IP address
        # host_ip = socket.gethostbyname(socket.gethostname())
        self.host_ip = "192.168.0.7"
        print(f"Local IP address: {self.host_ip}")
        self.zeroconf_server = None
        self.service_info = None
    def start(self):
        self.zeroconf_server = Zeroconf()
        self.service_info = ServiceInfo(
            self.service_type,
            self.service_name,
            addresses=[socket.inet_aton(self.host_ip)],  # Convert IP to bytes
            port=self.port,
            properties={"desc": "Test HTTP Service"},
            server="thermocam-server.local."
        )
        self.zeroconf_server.register_service(self.service_info)


