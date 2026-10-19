from __future__ import annotations

import json
import time
from typing import Any, Dict, List


def now_ms() -> int:
    return int(time.time() * 1000)


def compact_json(obj: Any) -> str:
    # Separators garantem JSON compacto e determinístico, compatível com org.json no Java.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_connect_message(device_structure: Dict[str, Any], timeout_s: float = 10.0) -> str:
    """
    Contrato TATU (handshake):
      CONNECT VALUE BROKER {json}

    Observação: o gateway em soft_iot_storage.py faz payload.find('{') e json.loads(...) a partir daí,
    então qualquer prefixo antes do '{' deve ser exatamente "CONNECT VALUE BROKER ".
    """
    device_id = device_structure["id"]
    request_body = {
        "TIME_OUT": timeout_s,
        "HEADER": {"NAME": device_id},
        "DEVICE": device_structure,
    }
    return f"CONNECT VALUE BROKER {compact_json(request_body)}"


def build_get_response(device_id: str, sensor_id: str, value: float) -> str:
    # Resposta TATU mínima esperada pelo gateway: JSON válido com CODE=POST e BODY presente.
    return compact_json(
        {
            "METHOD": "GET",
            "CODE": "POST",
            "HEADER": {"NAME": device_id, "TIMESTAMP": now_ms()},
            "BODY": {sensor_id: value},
        }
    )


def build_flow_response(
    device_id: str,
    sensor_id: str,
    collect_ms: int,
    publish_ms: int,
    values: List[float],
) -> str:
    # Inclui BODY.FLOW porque o gateway usa isso para inferir timestamps quando recebe arrays.
    return compact_json(
        {
            "METHOD": "FLOW",
            "CODE": "POST",
            "HEADER": {"NAME": device_id, "TIMESTAMP": now_ms()},
            "BODY": {sensor_id: values, "FLOW": {"collect": int(collect_ms), "publish": int(publish_ms)}},
        }
    )


def parse_flow_command(payload: str) -> Dict[str, Any] | None:
    """
    Contrato rigoroso (compatível com o Java TATUWrapper):
      FLOW VALUE {sensor_id} {json}
    Onde sensor_id == payload.split(" ")[2]
    """
    parts = payload.split(" ")
    if len(parts) < 4 or parts[0] != "FLOW":
        return None

    sensor_id = parts[2]
    json_start = payload.find("{")
    if json_start == -1:
        return None

    try:
        cfg = json.loads(payload[json_start:])
    except Exception:
        return None

    if not isinstance(cfg, dict):
        return None

    if "collect" not in cfg or "publish" not in cfg:
        return None

    return {
        "sensor_id": sensor_id.strip(),
        "collect_ms": int(cfg["collect"]),
        "publish_ms": int(cfg["publish"]),
    }


def parse_get_command(payload: str) -> Dict[str, Any] | None:
    """
    Contrato:
      GET VALUE {sensor_id}
    """
    parts = payload.split(" ")
    if len(parts) < 3 or parts[0] != "GET":
        return None

    return {"sensor_id": parts[2].strip()}

