from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional

import paho.mqtt.client as mqtt

from .protocol import build_flow_response


@dataclass
class SensorFlowWorker:
    device_id: str
    sensor_id: str
    mqtt_client: mqtt.Client
    response_topic: str
    collect_ms: int
    publish_ms: int
    value_min: float = 0.0
    value_max: float = 100.0

    _values: List[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop_evt: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = None

    def start_or_update(self, collect_ms: int, publish_ms: int) -> None:
        with self._lock:
            self.collect_ms = int(collect_ms)
            self.publish_ms = int(publish_ms)
            should_start = self._thread is None or not self._thread.is_alive()

        if should_start:
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._run, name=f"FLOW/{self.device_id}/{self.sensor_id}", daemon=True)
            self._thread.start()
            print(
                f"[FLOW] started sensor='{self.sensor_id}' collect_ms={self.collect_ms} publish_ms={self.publish_ms}"
            )
        else:
            print(
                f"[FLOW] updated sensor='{self.sensor_id}' collect_ms={self.collect_ms} publish_ms={self.publish_ms}"
            )

    def stop(self) -> None:
        self._stop_evt.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=2.0)
        print(f"[FLOW] stopped sensor='{self.sensor_id}'")

    def _run(self) -> None:
        last_collect = 0.0
        last_publish = 0.0

        while not self._stop_evt.is_set():
            with self._lock:
                collect_s = max(self.collect_ms, 1) / 1000.0
                publish_s = max(self.publish_ms, 1) / 1000.0
                collect_ms = int(self.collect_ms)
                publish_ms = int(self.publish_ms)

            now = time.time()
            if last_collect == 0.0:
                last_collect = now
                last_publish = now

            if now - last_collect >= collect_s:
                value = round(random.uniform(self.value_min, self.value_max), 2)
                with self._lock:
                    self._values.append(value)
                    buf_len = len(self._values)
                last_collect = now
                print(f"[COLLECT] sensor='{self.sensor_id}' value={value} buffer={buf_len}")

            if now - last_publish >= publish_s:
                with self._lock:
                    batch = self._values[:]
                    self._values.clear()

                if batch:
                    msg = build_flow_response(
                        device_id=self.device_id,
                        sensor_id=self.sensor_id,
                        collect_ms=collect_ms,
                        publish_ms=publish_ms,
                        values=batch,
                    )
                    self.mqtt_client.publish(self.response_topic, msg)
                    print(f"[SEND] topic='{self.response_topic}' payload='{msg}'")
                last_publish = now

            time.sleep(0.01)

