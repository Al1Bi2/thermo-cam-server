
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
import numpy as np
import cv2
import multiprocessing as mp
import time
import queue
MJPEG_PORT = 80
FRAMERATE = 25


class VideoProcessWorker(mp.Process):
    def __init__(self,device_id: str,device_ip: str, queue: mp.Queue, pipe: mp.Pipe):
        super().__init__()
        self.device_id = device_id
        self.queue = queue
        self.pipe = pipe
        self.video_url = f"http://{device_ip}:{MJPEG_PORT}/mjpeg/1"
        self.running = True
        self.paused = True

    def run(self):
        cap = cv2.VideoCapture(self.video_url)
        a = 0
        if not cap.isOpened():
            self.pipe.send({
                "type" : "event",
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
                if cmd == "pause":
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
            a+=1
            print(a)
            now = time.time()
            if now - last_frame_time >= 1.0/FRAMERATE:
                last_frame_time = now
                self.queue.put({
                    "type": "frame",
                    "id": self.device_id,
                    "data": frame
                })
        if cap:
            cap.release()


class VideoProcessController(QObject):
    frame_ready = pyqtSignal(str, object)  # device_id, frame
    event_received = pyqtSignal(str, str, str)  # device_id, event_type, msg (optional)

    def __init__(self):
        super().__init__()
        self.workers: dict[str, tuple[mp.Process, mp.Queue, mp.Pipe]] = {}

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_all)
        self.poll_timer.start(int(1000//FRAMERATE-8))

    def start_stream(self,device_id: str,device_ip: str):
        worker = self.workers.get(device_id)
        if not worker:
            queue = mp.Queue()
            parent_pipe, child_pipe = mp.Pipe()
            process = VideoProcessWorker(device_id,device_ip,queue,child_pipe)
            process.start()
            self.workers[device_id] = (process,queue, parent_pipe)
            parent_pipe.send("play")
        else:
            _,_, pipe = worker
            pipe.send("play")
    def pause_stream(self,device_id: str):
        worker = self.workers.get(device_id)
        if worker:
            _, _, pipe = worker
            pipe.send("pause")

    def stop_stream(self,device_id: str):
        worker = self.workers.get(device_id)
        if worker:
            process, queue, pipe =  worker
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
        for device_id, (_, queue_, _) in self.workers.items():
            try:
                if queue_.qsize() > 5:
                    while not queue_.empty():
                        queue_.get_nowait()
                msg = queue_.get_nowait()
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

    def __init__(self):
        super().__init__()
        self.latest_matrix: dict[str, list[list[float]]] = {}
        self.min = 1000
        self.max = 0

    def update_matrix(self, device_id: str, matrix: list[list[float]]):
        self.latest_matrix[device_id] = matrix

    def handle_frame(self, device_id: str, frame):
        if device_id not in self.latest_matrix:
            return  # нет матрицы — нечего обрабатывать

        matrix = self.latest_matrix[device_id]
        matrix_array = np.flipud(np.array(matrix).T)

        heatmap = self.create_heatmap(matrix_array, frame.shape)
        gray = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
        overlay = cv2.addWeighted(gray, 1, heatmap, 1, 0)

        self.overlay_ready.emit(device_id, overlay)

    def create_heatmap(self, data, frame_shape):

        heatmap = cv2.resize(data, (frame_shape[1], frame_shape[0]), interpolation=cv2.INTER_CUBIC)
        self.min = heatmap.min() if heatmap.min() < self.min else self.min
        self.max = heatmap.max() if heatmap.max() > self.min else self.max
        heatmap = np.uint8(255 * (heatmap -  self.min) / ( self.max - self.min + 1e-5))
        return cv2.applyColorMap(heatmap, cv2.COLORMAP_HSV)