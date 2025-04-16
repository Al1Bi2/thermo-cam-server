# mock_esp32cam.py

import threading
import time
import socket
import struct
import random

import cv2
import numpy as np
from flask import Flask, Response
import paho.mqtt.client as mqtt
from zeroconf import Zeroconf,ServiceBrowser, ServiceListener

# === CONFIG ===
DEVICE_ID = "esp32-mock"
FAKE_IP = "192.168.0.123"  # должен быть назначен вручную через виртуальный адаптер
MJPEG_PORT = 8080             # можно заменить на 8080 если порт занят

SERVICE_TYPE = "_http._tcp.local."
MDNS_HOSTNAME = "thermocam-server.local."

MQTT_USERNAME = "rmuser"
MQTT_PASSWORD = "pass"
# === MJPEG Flask app ===
app = Flask(__name__)
counter = 0

def generate_mjpeg():
    global counter
    while True:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, f"Frame {counter}", (50, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        counter += 1
        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(1.0/25)

@app.route('/mjpeg/1')
def mjpeg():
    return Response(generate_mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')


def start_flask():
    print(f"[MJPEG] Serving on http://{FAKE_IP}:{MJPEG_PORT}/mjpeg/1")
    app.run(host=FAKE_IP, port=MJPEG_PORT, threaded=True)
class ServerResolver(ServiceListener):
    def __init__(self, zc: Zeroconf):
        self.zc = zc
        self.found_ip = None

    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name)
        if info and info.server == MDNS_HOSTNAME:
            ip = socket.inet_ntoa(info.addresses[0])
            print(f"[mDNS] Resolved {MDNS_HOSTNAME} → {ip}")
            self.found_ip = ip

    def remove_service(self, zc, type_, name):
        pass

    def update_service(self, zc, type_, name):
        pass

def resolve_server_ip():
    zc = Zeroconf()
    listener = ServerResolver(zc)
    browser = ServiceBrowser(zc, SERVICE_TYPE, listener)
    print(f"[mDNS] Looking for server {MDNS_HOSTNAME}...")

    while listener.found_ip is None:
        time.sleep(0.5)

    return listener.found_ip
# === MQTT Logic ===
def generate_matrix():
    floats = [random.uniform(20.0, 35.0) for _ in range(64)]
    return struct.pack('<64f', *floats)
connected = False
active = False
client = mqtt.Client(client_id=DEVICE_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
def message_handler( client_a, userdata, message):
    global client, active,connected
    print(message.payload.decode())
    if message.topic == "server/status":
        if message.payload.decode() == "offline":
            active = False
            connected = False
    if message.topic ==f"{DEVICE_ID}/control":
        if message.payload.decode() == "ack-connect":
            connected = True
        if message.payload.decode() == "start":
            client.publish(f"{DEVICE_ID}/status","active")
            active = True
        if message.payload.decode() == "stop":

            client.publish(f"{DEVICE_ID}/status","connected")
            active = False

def start_mqtt():
    global client, active,connected
    while True:
        if client.is_connected():
            client.disconnect()
        broker_ip = resolve_server_ip()
        client.will_clear()
        client.username_pw_set(MQTT_USERNAME,MQTT_PASSWORD)
        client.on_connect = lambda a,b,c,d,e: print(DEVICE_ID+" connected to MQTT")
        client.on_message = message_handler
        client.will_set(DEVICE_ID+"/status", "offline", qos=1)
        client.connect(broker_ip, 1883, 60)
        client.loop_start()
        client.subscribe(DEVICE_ID+"/control")
        client.subscribe("server/status")

        # Discovery
        discovery_payload = f"{DEVICE_ID}:{FAKE_IP}"

        while not connected:
            client.publish("discovery", discovery_payload)
            print(f"[MQTT] Sent discovery to {broker_ip} → {discovery_payload}")
            time.sleep(1)
        while connected:
            if active:
                matrix = generate_matrix()
                client.publish(f"{DEVICE_ID}/amg8833", matrix)
            time.sleep(1.0/2)

# === mDNS Lookup ===


# === MAIN ===
if __name__ == "__main__":


    threading.Thread(target=start_flask, daemon=True).start()
    threading.Thread(target=start_mqtt, daemon=True).start()

    print("[Mock ESP32-CAM] Running")
    while True:
        time.sleep(1)


