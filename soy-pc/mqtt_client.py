"""
MQTT 클라이언트 싱글톤 — soy-pc IoT 제어용.

환경변수:
  MQTT_BROKER_HOST (기본 127.0.0.1)
  MQTT_BROKER_PORT (기본 1883)

사용:
  from mqtt_client import mqtt_client
  mqtt_client.connect()
  mqtt_client.publish("device/control", "DC_START:200")
  mqtt_client.subscribe("device/sensor", my_callback)
  mqtt_client.disconnect()
"""

import logging
import os
import threading
from typing import Callable

logger = logging.getLogger(__name__)

_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "127.0.0.1")
_BROKER_PORT = int(os.environ.get("MQTT_BROKER_PORT", "1883"))


class MqttClient:
    def __init__(self) -> None:
        self._client = None
        self._connected = False
        self._lock = threading.Lock()
        self._subscriptions: dict[str, list[Callable[[str, str], None]]] = {}

    def connect(self, host: str = _BROKER_HOST, port: int = _BROKER_PORT) -> None:
        """MQTT 브로커에 연결. 이미 연결되어 있으면 무시."""
        try:
            import paho.mqtt.client as paho
        except ImportError:
            logger.error("[MQTT] paho-mqtt 미설치. `uv add paho-mqtt` 실행 필요.")
            return

        with self._lock:
            if self._client is not None:
                return

            client = paho.Client(
                paho.CallbackAPIVersion.VERSION2, client_id="soy-pc", clean_session=True
            )
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message

            try:
                client.connect(host, port, keepalive=60)
                client.loop_start()
                self._client = client
                logger.info("[MQTT] connecting to %s:%d", host, port)
            except Exception as e:
                logger.warning("[MQTT] connect failed: %s", e)

    def disconnect(self) -> None:
        with self._lock:
            if self._client is None:
                return
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False
        logger.info("[MQTT] disconnected")

    def publish(self, topic: str, payload: str) -> None:
        with self._lock:
            c = self._client
        if c is None or not self._connected:
            logger.debug(
                "[MQTT] publish skipped (not connected): %s %s", topic, payload
            )
            return
        c.publish(topic, payload, qos=0)
        logger.debug("[MQTT] >> %s : %s", topic, payload)

    def subscribe(self, topic: str, callback: Callable[[str, str], None]) -> None:
        """토픽 구독. callback(topic, payload) 형태. 동일 토픽에 복수 콜백 등록 가능."""
        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        if callback not in self._subscriptions[topic]:
            self._subscriptions[topic].append(callback)
        with self._lock:
            c = self._client
        if c and self._connected:
            c.subscribe(topic, qos=0)
            logger.info("[MQTT] subscribed %s", topic)

    # ── paho 콜백 ────────────────────────────────────────────────────
    def _on_connect(
        self, client, userdata, flags, reason_code, properties=None
    ) -> None:
        if reason_code == 0:
            self._connected = True
            logger.info("[MQTT] connected")
            # 재연결 시 기존 구독 복원
            for topic in self._subscriptions:
                client.subscribe(topic, qos=0)
        else:
            logger.warning("[MQTT] connection refused, reason=%s", reason_code)

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ) -> None:
        self._connected = False
        logger.info("[MQTT] disconnected reason=%s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="ignore").strip()
        logger.debug("[MQTT] << %s : %s", topic, payload)
        callbacks = self._subscriptions.get(topic, [])
        for cb in callbacks:
            try:
                cb(topic, payload)
            except Exception as e:
                logger.warning("[MQTT] callback error %s: %s", topic, e)

    @property
    def is_connected(self) -> bool:
        return self._connected


# 전역 싱글톤
mqtt_client = MqttClient()
