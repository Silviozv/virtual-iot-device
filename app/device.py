from __future__ import annotations

import time
from typing import Any, Dict, Optional

import paho.mqtt.client as mqtt

from .protocol import (
    build_connect_message,
    build_get_response,
    parse_flow_command,
    parse_get_command,
)
from .sensor_worker import SensorFlowWorker


class VirtualIoTDevice:
    def __init__(self, broker_ip: str, broker_port: int, device_structure: Dict[str, Any]):
        self.broker_ip = broker_ip
        self.broker_port = int(broker_port)
        self.device_structure = device_structure

        self.device_id = device_structure["id"]
        self.command_topic = f"dev/{self.device_id}"
        self.response_topic = f"dev/{self.device_id}/RES"

        self.client = mqtt.Client(client_id=f"py-virtual-device-{self.device_id}")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._flows: Dict[str, SensorFlowWorker] = {}
        self._connected_rc: Optional[int] = None

    def start(self) -> None:
        print(f"[BOOT] device_id='{self.device_id}' broker='{self.broker_ip}:{self.broker_port}'")
        print(f"[BOOT] subscribe='{self.command_topic}' publish_res='{self.response_topic}'")

        self.client.connect(self.broker_ip, self.broker_port, keepalive=60)
        self.client.loop_start()

        self._publish_handshake_with_re4ea1e318cc1ctry()

        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("[BOOT] stopping...")
        finally:
            self.stop()

    def stop(self) -> None:
        for worker in list(self._flows.values()):
            worker.stop()
        try:
            self.client.loop_stop()
        finally:
            try:
                self.client.disconnect()
            except Exception:
                pass

    def _publish_handshake_with_retry(self) -> None:
        connect_msg = build_connect_message(self.device_structure)

        # Aguarda callback de connect (rc registrado) ou segue mesmo assim.
        for _ in range(30):
            if self._connected_rc is not None:
                break
            time.sleep(0.1)

        self.client.publish("dev/CONNECTIONS", connect_msg, qos=1)
        print(f"[SEND] topic='dev/CONNECTIONS' payload='{connect_msg}'")

    def _on_connect(self, client, userdata, flags, rc):
        self._connected_rc = rc
        print(f"[MQTT] connected rc={rc}")
        client.subscribe(self.command_topic, qos=1)
        print(f"[MQTT] subscribed topic='{self.command_topic}'")

    def _on_message(self, client, userdata, msg):
        payload_raw = msg.payload.decode("utf-8", errors="replace")
        payload = payload_raw.strip()
        print(f"[RECV] topic='{msg.topic}' payload_raw='{payload_raw}' payload='{payload}'")

        if not payload:
            return

        # Ignora respostas em JSON (ex.: CONNACK do gateway) se caírem no tópico de comandos.
        if payload.startswith("{") and "\"METHOD\"" in payload:
            print("[RECV] ignoring json-response payload on command topic")
            return

        flow_cmd = parse_flow_command(payload)
        if flow_cmd:
            self._handle_flow(flow_cmd["sensor_id"], flow_cmd["collect_ms"], flow_cmd["publish_ms"])
            return

        get_cmd = parse_get_command(payload)
        if get_cmd:
            self._handle_get(get_cmd["sensor_id"])
            return

        print("[RECV] unknown command; ignored")

    def _handle_flow(self, sensor_id: str, collect_ms: int, publish_ms: int) -> None:
        if collect_ms < 1 or publish_ms < 1:
            print(f"[FLOW] invalid timings sensor='{sensor_id}' collect={collect_ms} publish={publish_ms}")
            return

        worker = self._flows.get(sensor_id)
        if worker is None:
            worker = SensorFlowWorker(
                device_id=self.device_id,
                sensor_id=sensor_id,
                mqtt_client=self.client,
                response_topic=self.response_topic,
                collect_ms=collect_ms,
                publish_ms=publish_ms,
            )
            self._flows[sensor_id] = worker
            print(f"[FLOW] created worker sensor='{sensor_id}'")

        worker.start_or_update(collect_ms=collect_ms, publish_ms=publish_ms)

    def _handle_get(self, sensor_id: str) -> None:
        # Valor float aleatório para simular sensor
        import random

        value = round(random.uniform(0.0, 100.0), 2)
        resp = build_get_response(self.device_id, sensor_id, value)
        self.client.publish(self.response_topic, resp, qos=1)
        print(f"[SEND] topic='{self.response_topic}' payload='{resp}'")

