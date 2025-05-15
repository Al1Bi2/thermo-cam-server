from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QPointF
import numpy as np
import cv2
import multiprocessing as mp
import time
import queue

from models.model import ProcessingSettings, Esp32Manager, AlertZone
from views.AlertsEditorOverlay import transform_coords_f2i, transform_coords_i2f

MJPEG_PORT = 80
FRAMERATE = 25
QUEUE_MAXSIZE = 5


@dataclass
class ZonePoint:
    point: QPointF = QPointF()
    temperature: float = 0




class VideoProcessWorker(mp.Process):
    def __init__(self, device_id: str, device_ip: str, image_queue: mp.Queue, pipe: mp.Pipe):
        super().__init__()
        self.device_id = device_id
        self.image_queue = image_queue
        self.pipe = pipe
        self.video_url = f"http://{device_ip}:{MJPEG_PORT}/mjpeg/1"
        self.running = True
        self.paused = True
        self.settings = None
        self.zones = None
        self.last_matrix = None

    def handle_update(self, msg):
        if msg["type"] == "matrix":
            self.last_matrix = msg["content"]
        if msg["type"] == "zones":
            self.zones = msg["content"]
        if msg["type"] == "settings":
            self.settings = msg["content"]

    def run(self):
        cap = cv2.VideoCapture(self.video_url)
        if not cap.isOpened():
            self.pipe.send({
                "type": "event",
                "event": "error",
                "id": self.device_id,
                "msg": "Failed to open stream"
            })
            return

        self.pipe.send({
            "type": "event",
            "event": "started",
            "id": self.device_id
        })

        last_frame_time = time.time()

        while self.running:
            if self.pipe.poll():
                cmd = self.pipe.recv()
                if isinstance(cmd, dict):
                    self.handle_update(cmd)
                elif cmd == "pause":
                    self.paused = True
                    self.pipe.send({
                        "type": "event",
                        "event": "paused",
                        "id": self.device_id
                    })
                elif cmd == "play":
                    self.paused = False
                    self.pipe.send({
                        "type": "event",
                        "event": "resumed",
                        "id": self.device_id
                    })
                elif cmd == "stop":
                    break

            if self.paused:
                time.sleep(0.01)
                continue

            ret, frame = cap.read()
            if not ret:
                continue

            now = time.time()
            if now - last_frame_time >= 1.0 / FRAMERATE:
                if self.image_queue.full():
                    self.image_queue.get()
                last_frame_time = now
                self.image_queue.put({
                    "type": "frame",
                    "id": self.device_id,
                    "data": frame.copy()
                })
        if cap:
            cap.release()


class VideoProcessController(QObject):
    frame_ready = pyqtSignal(str, object)  # device_id, frame
    event_received = pyqtSignal(str, str, str)  # device_id, event_type, msg (optional)

    overlay_ready = pyqtSignal(str, object)  # device_id, overlay frame
    processing_settings_changed = pyqtSignal(str, dict)  # device_id, ProcessingSettings as dict
    alert_zones_changed = pyqtSignal(str, list)  # device_id, list of zones as dicts

    def __init__(self):
        super().__init__()
        self.workers: dict[str, tuple[mp.Process, mp.Queue, mp.Pipe]] = {}

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_all)
        self.poll_timer.start(int(1000 // (FRAMERATE * 2)))

    def update_matrix(self, device_id: str, matrix: list[list[float]]):
        worker = self.workers.get(device_id)
        if worker:
            new_data = np.flipud(np.array(matrix, dtype=np.float32).T)
            _, _, pipe = worker
            pipe.send({"type": "matrix",
                       "content": new_data})

    def update_zones(self, device_id, zones):
        worker = self.workers.get(device_id)
        if worker:
            _, _, pipe = worker
            pipe.send({"type": "zones",
                       "content": zones})

    def _update_settings(self, device_id, settings):
        worker = self.workers.get(device_id)
        if worker:
            _, _, pipe = worker
            pipe.send({"type": "settings",
                       "content": settings})

    def start_stream(self, device_id: str, device_ip: str):
        worker = self.workers.get(device_id)
        if not worker:
            image_queue = mp.Queue(maxsize=QUEUE_MAXSIZE)

            parent_pipe, child_pipe = mp.Pipe()
            process = VideoProcessWorker(device_id, device_ip, image_queue, child_pipe)
            process.start()
            self.workers[device_id] = (process, image_queue, parent_pipe)
            parent_pipe.send("play")
        else:
            _, _, pipe = worker
            pipe.send("play")

    def pause_stream(self, device_id: str):
        worker = self.workers.get(device_id)
        if worker:
            _, _, pipe = worker
            pipe.send("pause")

    def stop_stream(self, device_id: str):
        worker = self.workers.get(device_id)
        if worker:
            process, _, pipe = worker
            pipe.send("stop")
            process.join(timeout=0.5)
            if process.is_alive():
                process.terminate()
            del self.workers[device_id]

    def stop_all_streams(self):
        for device_id in list(self.workers.keys()):
            self.stop_stream(device_id)

    def _poll_all(self):
        self._poll_frames()
        self._poll_events()

    def _poll_frames(self):
        for device_id, (_, image_queue, _) in self.workers.items():
            try:
                msg = image_queue.get_nowait()
                if msg["type"] == "frame":
                    self.frame_ready.emit(device_id, msg["data"])
            except queue.Empty:
                continue

    def _poll_events(self):
        for device_id, (_, _, pipe) in self.workers.items():
            while pipe.poll():
                event = pipe.recv()
                event_type = event.get("type")
                msg = event.get("msg", "")
                self.event_received.emit(device_id, event_type, msg)


class ProcessingController(QObject):
    overlay_ready = pyqtSignal(str, object)  # device_id, overlay frame
    processing_settings_changed = pyqtSignal(str, dict)  # device_id, ProcessingSettings as dict
    alert_zones_changed = pyqtSignal(str, list)  # device_id, list of zones as dicts
    temperature_changed = pyqtSignal(str, list)  # device_id, list of temperature as dicts

    def __init__(self, model: Esp32Manager):
        super().__init__()
        self.latest_matrix: dict[str, np.ndarray] = {}

        self.min = 100
        self.max = -10
        self.model = model
        self.settings = {dev.id: dev.processing_settings for dev in self.model.get_all()}
        self.processing_settings_changed.connect(self._update_local_settings)
        self.alert_zones = {dev.id: dev.alert_zones for dev in self.model.get_all()}
        self.alert_zones_changed.connect(self._update_local_zones)
        self.old_data = np.zeros((8, 8), dtype=np.float32)

        self.shape = (640, 480)

        self.str2heatmap = {
            "hsv": cv2.COLORMAP_HSV,
            "hot": cv2.COLORMAP_HOT,
            "jet": cv2.COLORMAP_JET,
            "inferno": cv2.COLORMAP_INFERNO
        }

    def _update_local_zones(self, device_id, zones):
        device = self.model.get_device(device_id)
        if device:
            self.alert_zones[device_id] = device.alert_zones

    def _update_local_settings(self, device_id, settings):
        device = self.model.get_device(device_id)
        if device:
            self.settings[device_id] = device.processing_settings

    def update_matrix(self, device_id: str, matrix: list[list[float]]):
        new_data = np.flipud(np.array(matrix, dtype=np.float32).T)

        if device_id not in self.latest_matrix:
            self.latest_matrix[device_id] = new_data
        else:
            self.latest_matrix[device_id] = (
                    0.8 * self.latest_matrix[device_id] + 0.2 * new_data
            )
        if self.alert_zones.get(device_id):
            self.temperature_changed.emit(device_id, self.update_temperature(device_id, self.latest_matrix[device_id]))

    def update_temperature(self, device_id: str, matrix):
        upscaled_matrix = cv2.resize(matrix, self.shape, interpolation=cv2.INTER_CUBIC)
        temperatures = []
        for zone in self.alert_zones[device_id]:
            if zone.enabled:
                if zone.type == "point":
                    temperatures.append(self.get_point_temperature(self.shape, zone, upscaled_matrix))
                else:
                    temperatures.append(self.get_area_temperature(self.shape, zone, upscaled_matrix))

        return temperatures

    def handle_frame(self, device_id: str, frame):
        if device_id not in self.latest_matrix:
            return  # нет матрицы — нечего обрабатывать
        self.shape = (frame.shape[1], frame.shape[0])
        matrix = self.latest_matrix[device_id]
        heatmap_colormap = self.str2heatmap[self.settings[device_id].heatmap_colormap]
        heatmap = self.create_heatmap(matrix, frame.shape, heatmap_colormap)
        processed_frame = frame
        if self.settings[device_id].video_filter == "gray":
            processed_frame = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        if self.settings[device_id].video_filter == "edges":
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
            sobel = cv2.magnitude(sobelx, sobely)
            sobel = cv2.convertScaleAbs(sobel)

            processed_frame = cv2.cvtColor(sobel, cv2.COLOR_GRAY2BGR)

        overlay = cv2.addWeighted(processed_frame, 1, heatmap, self.settings[device_id].thermo_alpha / 100, 0)

        if self.settings[device_id].overlay_mode == "both":
            overlay = cv2.addWeighted(processed_frame, 1, heatmap, self.settings[device_id].thermo_alpha / 100, 0)
        if self.settings[device_id].overlay_mode == "thermal":
            overlay = heatmap
        if self.settings[device_id].overlay_mode == "video":
            overlay = processed_frame

        self.overlay_ready.emit(device_id, overlay)

    def create_heatmap(self, data, frame_shape, heatmap_colormap):

        heatmap = cv2.resize(data, (frame_shape[1], frame_shape[0]), interpolation=cv2.INTER_CUBIC)
        self.min = heatmap.min() if heatmap.min() < self.min else self.min
        self.max = heatmap.max() if heatmap.max() > self.min else self.max

        heatmap = np.uint8(255 * (heatmap - self.min) / (self.max - self.min + 1e-5))
        return cv2.applyColorMap(heatmap, heatmap_colormap)

    def apply_overlay(self, device_id, frame, heatmap):

        for zone in self.alert_zones[device_id]:
            if zone.enabled:
                if zone.type == "point":
                    self.draw_point_overlay(frame, zone, heatmap)
                else:
                    self.draw_area_overlay(frame, zone, heatmap)


        return frame

    def get_point_temperature(self, shape, zone: AlertZone, heatmap):
        # Нарисовать точку
        point = transform_coords_f2i(zone.coords[0], shape[0], shape[1])
        point = (int(point.x()), int(point.y()))  # Преобразуем в (x, y)
        zone.temperature = heatmap[point[1]][point[0]]
        return ZonePoint(point=zone.coords[0], temperature=zone.temperature)

    def get_area_temperature(self, shape, zone: AlertZone, heatmap):
        def get_bounding_box(polygon):

            min_x = min(polygon, key=lambda p: p[0])[0]
            max_x = max(polygon, key=lambda p: p[0])[0]
            min_y = min(polygon, key=lambda p: p[1])[1]
            max_y = max(polygon, key=lambda p: p[1])[1]
            return (min_x, min_y, max_x, max_y)


        points = [transform_coords_f2i(p, shape[0], shape[1]) for p in zone.coords]
        points = [(int(p.x()), int(p.y())) for p in points]


        mask = np.zeros(shape=(shape[1], shape[0]), dtype=np.uint8)  # Маска для полигональной области
        cv2.fillPoly(mask, [np.array(points, np.int32)], 255)

        min_x, min_y, max_x, max_y = get_bounding_box(points)
        max_temp = -float('inf')
        hottest_point = (0, 0)

        for y in range(min_y, min(max_y + 1, shape[1]), 2):
            for x in range(min_x, min(max_x + 1, shape[0]), 2):
                # Проверка, внутри ли пиксель полигона (с помощью маски)
                if mask[y][x] == 255:

                    temp = heatmap[y][x]


                    if temp > max_temp:
                        max_temp = temp
                        hottest_point = (x, y)


        if hottest_point:
            zone.temperature = max_temp
            hottest_point_norm = transform_coords_i2f(QPointF(hottest_point[0], hottest_point[1]), shape[0], shape[1])
        return ZonePoint(point=hottest_point_norm, temperature=zone.temperature)
