from __future__ import annotations

import os
import random
import uuid
from typing import Dict, Any

from .device import VirtualIoTDevice


def default_device_structure(device_id: str) -> Dict[str, Any]:
    # Espelha o formato usado pelo gateway no devices.json: id/latitude/longitude/sensors[]
    return {
        "id": device_id,
        "latitude": round(random.uniform(-90.0, 90.0), 8),
        "longitude": round(random.uniform(-180.0, 180.0), 8),
        "sensors": [
            {"id": "temperatureSensor", "type": "Thermometer", "collection_time": 2, "publishing_time": 6},
            {"id": "humiditySensor", "type": "HumiditySensor", "collection_time": 2, "publishing_time": 6},
            {"id": "pulseOxymeter", "type": "PulseOxymeter", "collection_time": 2, "publishing_time": 6},
            {"id": "windDirectionSensor", "type": "WindDirectionSensor", "collection_time": 2, "publishing_time": 6},
        ],
    }


def main() -> None:
    broker_ip = os.getenv("BROKER_IP", "127.0.0.1")
    broker_port = int(os.getenv("BROKER_PORT", "1883"))
    device_name = os.getenv("DEVICE_NAME") or str(uuid.uuid4())
    
    success_rate = float(os.getenv("SUCCESS_RATE", "100.0"))

    device_structure = default_device_structure(device_name)

    device = VirtualIoTDevice(
        broker_ip=broker_ip,
        broker_port=broker_port,
        device_structure=device_structure,
        success_rate=success_rate,  
    )
    device.start()


if __name__ == "__main__":
    main()

