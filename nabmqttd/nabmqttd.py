#!/usr/bin/env python3
"""
MQTT Bridge Service for Nabaztag

Bidirectional bridge connecting nabd daemon to MQTT broker for Home Assistant
integration. Translates between nabd JSON protocol and MQTT topics.

Architecture:
    - Asyncio-based single-process design for Pi Zero W efficiency
    - Stateless bridge - nabd is source of truth for hardware state
    - Exponential backoff reconnection for MQTT
    - QoS 0 for commands (low latency), QoS 1 for state (reliability)
"""

import asyncio
import datetime
import json
import logging
import os
import sys
import uuid
from typing import Any, Dict

import paho.mqtt.client as mqtt

from nabcommon import settings as nabsettings
nabsettings.configure("nabmqttd")

from nabcommon.nabservice import NabService
from nabcommon.typing import NabdPacket

from .models import Config


class NabMqttd(NabService):
    """
    MQTT Bridge Service for Nabaztag.

    Subscribes to MQTT command topics and translates to nabd JSON protocol.
    Publishes nabd events to MQTT state topics for Home Assistant.
    """

    # QoS levels
    QOS_COMMAND = 0  # Fire-and-forget for low latency
    QOS_STATE = 1     # At-least-once for reliability

    # Reconnection settings
    MQTT_RECONNECT_BASE_DELAY = 1  # seconds
    MQTT_RECONNECT_MAX_DELAY = 60  # seconds

    def __init__(self):
        super().__init__()

        self.config = None

        # MQTT client
        self.mqtt_client = None
        self.mqtt_connected = False
        self.mqtt_reconnect_count = 0
        self._reconnecting = False

        # State tracking (for retained messages)
        self.current_ears_state = {"left": 0, "right": 0}

        # Last activity tracking
        self.last_activity = datetime.datetime.now()
        self.message_count = 0

    async def load_config(self):
        """Load configuration from database."""
        self.config = await Config.load_async()
        logging.info(f"Loaded config: broker={self.config.broker_host}:{self.config.broker_port}, enabled={self.config.enabled}")

    async def reload_config(self):
        """Reload configuration on SIGUSR1 signal."""
        logging.info("Reloading MQTT bridge configuration")
        try:
            await self.load_config()
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            return

        if self.config.enabled:
            if self.mqtt_client:
                logging.info("Reconnecting to MQTT broker with new configuration")
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            self.setup_mqtt_client()
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self.mqtt_client.connect(
                        self.config.broker_host,
                        self.config.broker_port,
                        keepalive=60
                    )
                )
                self.mqtt_client.loop_start()
            except Exception as e:
                logging.error(f"Failed to reconnect to MQTT broker: {e}")
        else:
            logging.info("MQTT bridge is disabled in configuration")
            if self.mqtt_client and self.mqtt_connected:
                await self.publish_status_offline()
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()

    async def publish_status_offline(self):
        """Publish offline status before graceful disconnect."""
        if not self.mqtt_connected or not self.config:
            return
        topic = f"{self.config.topic_prefix}/status"
        payload = json.dumps({
            "status": "offline",
            "timestamp": datetime.datetime.now().isoformat()
        })
        try:
            self.mqtt_client.publish(topic, payload, qos=self.QOS_STATE, retain=True)
        except Exception as e:
            logging.error(f"Failed to publish offline status: {e}")

    def setup_mqtt_client(self):
        """Initialize MQTT client with configuration and callbacks."""
        logging.info(f"Setting up MQTT client: {self.config.broker_host}:{self.config.broker_port}")

        self.mqtt_client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id=self.config.client_id,
            clean_session=True,
            userdata=None,
            protocol=mqtt.MQTTv311,
            transport="tcp"
        )

        if self.config.broker_username:
            self.mqtt_client.username_pw_set(
                self.config.broker_username,
                self.config.broker_password or ""
            )

        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_mqtt_message

        lwt_topic = f"{self.config.topic_prefix}/status"
        lwt_payload = json.dumps({
            "status": "offline",
            "nabd_connected": False,
            "mqtt_connected": False
        })
        self.mqtt_client.will_set(
            lwt_topic,
            payload=lwt_payload,
            qos=self.QOS_STATE,
            retain=True
        )

    def on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback when MQTT connection is established."""
        if rc == 0:
            logging.info("MQTT connected successfully")
            self.mqtt_connected = True
            self.mqtt_reconnect_count = 0
            self._reconnecting = False

            self._subscribe_command_topics()

            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(self.publish_status())
            )
            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(self.publish_mqtt_discovery())
            )
        else:
            error_msg = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized"
            }.get(rc, f"Connection refused - unknown error code {rc}")
            logging.error(f"MQTT connection failed: {error_msg}")
            self.mqtt_connected = False

    def on_mqtt_disconnect(self, client, userdata, rc):
        """Callback when MQTT connection is lost."""
        self.mqtt_connected = False
        if rc != 0 and self.running and not self._reconnecting:
            delay = self._get_reconnect_delay()
            logging.warning(
                f"MQTT disconnected unexpectedly (rc={rc}), "
                f"reconnecting in {delay}s..."
            )
            self._reconnecting = True
            self.loop.call_soon_threadsafe(
                lambda: self.loop.create_task(self._mqtt_reconnect(delay))
            )
        elif rc == 0:
            logging.info("MQTT disconnected cleanly")

    def _get_reconnect_delay(self) -> int:
        """Calculate exponential backoff delay for reconnection."""
        delay = min(
            self.MQTT_RECONNECT_BASE_DELAY * (2 ** self.mqtt_reconnect_count),
            self.MQTT_RECONNECT_MAX_DELAY
        )
        self.mqtt_reconnect_count += 1
        return delay

    async def _mqtt_reconnect(self, delay: int):
        """Attempt to reconnect to MQTT broker with retry loop."""
        loop = asyncio.get_event_loop()
        try:
            await asyncio.sleep(delay)
            while self.running:
                try:
                    logging.info(f"MQTT reconnection attempt {self.mqtt_reconnect_count}")
                    await loop.run_in_executor(None, self.mqtt_client.reconnect)
                    return
                except Exception as e:
                    logging.error(f"MQTT reconnect failed: {e}")
                    delay = self._get_reconnect_delay()
                    await asyncio.sleep(delay)
        finally:
            if not self.mqtt_connected:
                self._reconnecting = False

    def _subscribe_command_topics(self):
        """Subscribe to MQTT command topics."""
        topics = [
            (f"{self.config.topic_prefix}/ears/set", self.QOS_COMMAND),
            (f"{self.config.topic_prefix}/ears/set_left", self.QOS_COMMAND),
            (f"{self.config.topic_prefix}/ears/set_right", self.QOS_COMMAND),
            (f"{self.config.topic_prefix}/leds/set", self.QOS_COMMAND),
            (f"{self.config.topic_prefix}/tts/say", self.QOS_COMMAND),
        ]

        for topic, qos in topics:
            self.mqtt_client.subscribe(topic, qos)
            logging.debug(f"Subscribed to {topic} (QoS {qos})")

    def on_mqtt_message(self, client, userdata, msg):
        """Callback when MQTT message is received on subscribed topic."""
        logging.debug(f"MQTT message: {msg.topic} = {msg.payload}")

        # Schedule coroutine to handle message in asyncio loop
        self.loop.call_soon_threadsafe(
            lambda: self.loop.create_task(
                self._handle_mqtt_command(msg.topic, msg.payload)
            )
        )

    async def _handle_mqtt_command(self, topic: str, payload: bytes):
        """
        Translate MQTT command to nabd JSON packet.

        Args:
            topic: MQTT topic (e.g., "nabaztag/ears/set")
            payload: MQTT message payload (JSON or plain number)
        """
        try:
            # Strip topic prefix
            prefix = f"{self.config.topic_prefix}/"
            if topic.startswith(prefix):
                relative_topic = topic[len(prefix):]
            else:
                relative_topic = topic

            # Parse payload
            try:
                data = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Try as plain number, then fall back to raw string
                raw = payload.decode("utf-8", errors="replace").strip()
                try:
                    data = int(raw)
                except ValueError:
                    data = raw

            # Translate to nabd packet
            nabd_packet = None

            if relative_topic == "ears/set":
                # Both ears: {"left": 0-16, "right": 0-16}
                if isinstance(data, dict):
                    left = self._clamp_ear(data.get("left", 0))
                    right = self._clamp_ear(data.get("right", 0))
                    nabd_packet = {
                        "type": "ears",
                        "left": left,
                        "right": right
                    }

            elif relative_topic == "ears/set_left":
                # Left ear only: integer 0-16
                if isinstance(data, int):
                    left = self._clamp_ear(data)
                    nabd_packet = {
                        "type": "ears",
                        "left": left
                    }

            elif relative_topic == "ears/set_right":
                # Right ear only: integer 0-16
                if isinstance(data, int):
                    right = self._clamp_ear(data)
                    nabd_packet = {
                        "type": "ears",
                        "right": right
                    }

            elif relative_topic == "leds/set":
                # LED color: {"color": "RRGGBB"}
                if isinstance(data, dict):
                    color = self._validate_color(data.get("color", "000000"))
                    nabd_packet = {
                        "type": "info",
                        "info_id": "nabmqttd",
                        "animation": {
                            "tempo": 1000,
                            "colors": [
                                {
                                    "left": color,
                                    "center": color,
                                    "right": color
                                }
                            ]
                        }
                    }

            elif relative_topic == "tts/say":
                await self._handle_tts(data)
                self.message_count += 1
                self.last_activity = datetime.datetime.now()
                return

            # Send to nabd if packet was created
            if nabd_packet:
                await self._send_to_nabd(nabd_packet)
                self.message_count += 1
                self.last_activity = datetime.datetime.now()
            else:
                logging.warning(f"Could not translate MQTT message: {topic} = {data}")

        except Exception as e:
            logging.error(f"Error handling MQTT command: {e}", exc_info=True)

    def _clamp_ear(self, value) -> int:
        """Clamp ear position to valid range 0-16."""
        try:
            return max(0, min(16, int(value)))
        except (TypeError, ValueError):
            return 0

    def _validate_color(self, color: str) -> str:
        """
        Validate and normalize color hex string.

        Args:
            color: Hex color string (with or without '#')

        Returns:
            Normalized hex color string (RRGGBB format)
        """
        # Remove '#' if present
        color = color.lstrip('#').upper()

        # Validate hex format
        if len(color) != 6:
            logging.warning(f"Invalid color format: {color}, using black")
            return "000000"

        try:
            int(color, 16)
        except ValueError:
            logging.warning(f"Invalid hex color: {color}, using black")
            return "000000"

        return color

    async def _handle_tts(self, data):
        """
        Generate TTS audio and play via nabd.

        Accepts: {"text": "...", "lang": "en"} or plain string
        """
        if isinstance(data, str):
            text = data
            lang = "en"
        elif isinstance(data, dict):
            text = data.get("text", "")
            lang = data.get("lang", "en")
        else:
            logging.warning(f"Invalid TTS payload: {data}")
            return

        if not text:
            return

        max_length = 500
        if len(text) > max_length:
            text = text[:max_length]
            logging.warning(f"TTS text truncated to {max_length} characters")

        try:
            loop = asyncio.get_event_loop()
            mp3_path = await loop.run_in_executor(None, self._generate_tts_audio, text, lang)
            if mp3_path:
                nabd_packet = {
                    "type": "command",
                    "sequence": [{"audio": [mp3_path]}]
                }
                await self._send_to_nabd(nabd_packet)
                logging.info(f"TTS playing: '{text[:50]}' ({lang})")
                self._cleanup_old_tts_files(mp3_path)
        except Exception as e:
            logging.error(f"TTS failed: {e}")

    TTS_SOUND_DIR = "/opt/pynab/nabmqttd/sounds"

    def _generate_tts_audio(self, text: str, lang: str) -> str:
        """Generate MP3 from text using gTTS. Runs in executor thread."""
        from gtts import gTTS

        os.makedirs(self.TTS_SOUND_DIR, exist_ok=True)
        filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        mp3_path = os.path.join(self.TTS_SOUND_DIR, filename)
        tts = gTTS(text=text, lang=lang)
        tts.save(mp3_path)
        return filename

    def _cleanup_old_tts_files(self, keep_filename: str):
        """Remove old TTS files, keeping only the most recent."""
        try:
            for f in os.listdir(self.TTS_SOUND_DIR):
                if f.startswith("tts_") and f.endswith(".mp3") and f != keep_filename:
                    os.remove(os.path.join(self.TTS_SOUND_DIR, f))
        except OSError:
            pass

    async def _send_to_nabd(self, packet: Dict[str, Any]):
        """
        Send JSON packet to nabd daemon.

        Args:
            packet: Dictionary representing nabd JSON packet
        """
        if not self.writer:
            logging.warning("Cannot send to nabd: not connected")
            return

        try:
            packet_json = json.dumps(packet) + "\r\n"
            self.writer.write(packet_json.encode("utf-8"))
            await self.writer.drain()
            logging.debug(f"Sent to nabd: {packet}")
        except Exception as e:
            logging.error(f"Error sending to nabd: {e}")

    async def process_nabd_packet(self, packet: NabdPacket):
        """
        Process incoming packet from nabd and translate to MQTT.

        Args:
            packet: Parsed JSON packet from nabd
        """
        if not self.config:
            return

        packet_type = packet.get("type")

        if packet_type == "state":
            await self._handle_state_packet(packet)
        elif packet_type == "ears_event":
            await self.handle_ears_state(packet)
        elif packet_type == "button_event":
            await self.handle_button_event(packet)
        elif packet_type == "rfid_event":
            await self.handle_rfid_event(packet)
        else:
            logging.debug(f"Ignoring nabd packet type: {packet_type}")

    async def _handle_state_packet(self, packet: NabdPacket):
        """Handle state change packet from nabd."""
        state = packet.get("state")
        logging.info(f"Nabaztag state: {state}")
        await self.publish_status()

    async def handle_ears_state(self, packet: NabdPacket):
        """
        Handle ears position update from nabd.

        Publishes to: nabaztag/ears/state
        """
        if self.config and not self.config.publish_ears_state:
            return

        left = packet.get("left")
        right = packet.get("right")

        # Update cached state
        if left is not None:
            self.current_ears_state["left"] = left
        if right is not None:
            self.current_ears_state["right"] = right

        # Publish to MQTT
        topic = f"{self.config.topic_prefix}/ears/state"
        payload = json.dumps(self.current_ears_state)
        await self._publish_mqtt(topic, payload, qos=self.QOS_STATE, retain=True)

    async def handle_button_event(self, packet: NabdPacket):
        """
        Handle button press event from nabd.

        Publishes to: nabaztag/button/event
        """
        if self.config and not self.config.publish_button_events:
            return

        event = packet.get("event")
        if event:
            topic = f"{self.config.topic_prefix}/button/event"
            payload = json.dumps({
                "event": event,
                "timestamp": datetime.datetime.now().isoformat()
            })
            await self._publish_mqtt(topic, payload, qos=self.QOS_STATE, retain=False)

    async def handle_rfid_event(self, packet: NabdPacket):
        """
        Handle RFID tag detection event from nabd.

        Publishes to: nabaztag/rfid/detected or nabaztag/rfid/removed
        """
        if self.config and not self.config.publish_rfid_events:
            return

        event = packet.get("event")
        if event not in ("detected", "removed"):
            return

        uid = packet.get("uid", "")
        topic = f"{self.config.topic_prefix}/rfid/{event}"
        payload = json.dumps({
            "uid": uid,
            "timestamp": datetime.datetime.now().isoformat()
        })
        await self._publish_mqtt(topic, payload, qos=self.QOS_STATE, retain=False)

    async def _publish_mqtt(self, topic: str, payload: str, qos: int = 0, retain: bool = False):
        """
        Publish message to MQTT broker.

        Args:
            topic: MQTT topic
            payload: Message payload (string or JSON)
            qos: Quality of Service level (0 or 1)
            retain: Whether message should be retained by broker
        """
        if not self.mqtt_connected:
            logging.warning(f"Cannot publish to MQTT: not connected ({topic})")
            return

        try:
            result = self.mqtt_client.publish(
                topic,
                payload=payload,
                qos=qos,
                retain=retain
            )
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logging.warning(f"MQTT publish failed: {result.rc}")
            else:
                logging.debug(f"Published to MQTT: {topic} = {payload[:100]}")
        except Exception as e:
            logging.error(f"Error publishing to MQTT: {e}")

    async def publish_status(self):
        """
        Publish bridge status to MQTT.

        Publishes to: nabaztag/status (retained)
        """
        topic = f"{self.config.topic_prefix}/status"
        payload = json.dumps({
            "status": "online",
            "nabd_connected": self.writer is not None,
            "mqtt_connected": self.mqtt_connected,
            "message_count": self.message_count,
            "last_activity": self.last_activity.isoformat(),
            "timestamp": datetime.datetime.now().isoformat()
        })
        await self._publish_mqtt(topic, payload, qos=self.QOS_STATE, retain=True)

    async def publish_mqtt_discovery(self):
        """
        Publish Home Assistant MQTT discovery messages for auto-configuration.

        Creates entities:
        - number.nabaztag_left_ear
        - number.nabaztag_right_ear
        - light.nabaztag_led
        - binary_sensor.nabaztag_button
        - sensor.nabaztag_rfid
        - binary_sensor.nabaztag_connection
        """
        logging.info("Publishing Home Assistant MQTT discovery messages")

        device_info = {
            "identifiers": ["nabaztag_aaron"],
            "name": "Aaron's Nabaztag",
            "model": "Nabaztag v2",
            "manufacturer": "Violet/Nabaztag"
        }

        # Left ear number entity
        await self._publish_discovery_config(
            "number", "left_ear",
            {
                "name": "Nabaztag Left Ear",
                "unique_id": "nabaztag_left_ear",
                "command_topic": f"{self.config.topic_prefix}/ears/set_left",
                "state_topic": f"{self.config.topic_prefix}/ears/state",
                "value_template": "{{ value_json.left }}",
                "min": 0,
                "max": 16,
                "step": 1,
                "mode": "slider",
                "icon": "mdi:rabbit",
                "device": device_info
            }
        )

        # Right ear number entity
        await self._publish_discovery_config(
            "number", "right_ear",
            {
                "name": "Nabaztag Right Ear",
                "unique_id": "nabaztag_right_ear",
                "command_topic": f"{self.config.topic_prefix}/ears/set_right",
                "state_topic": f"{self.config.topic_prefix}/ears/state",
                "value_template": "{{ value_json.right }}",
                "min": 0,
                "max": 16,
                "step": 1,
                "mode": "slider",
                "icon": "mdi:rabbit",
                "device": device_info
            }
        )

        # Button binary sensor
        await self._publish_discovery_config(
            "binary_sensor", "button",
            {
                "name": "Nabaztag Button",
                "unique_id": "nabaztag_button",
                "state_topic": f"{self.config.topic_prefix}/button/event",
                "value_template": "{{ 'ON' if value_json.event else 'OFF' }}",
                "device_class": "motion",
                "icon": "mdi:gesture-tap-button",
                "device": device_info
            }
        )

        # RFID sensor
        await self._publish_discovery_config(
            "sensor", "rfid",
            {
                "name": "Nabaztag RFID",
                "unique_id": "nabaztag_rfid",
                "state_topic": f"{self.config.topic_prefix}/rfid/detected",
                "value_template": "{{ value_json.uid }}",
                "icon": "mdi:nfc-variant",
                "device": device_info
            }
        )

        # Connection status binary sensor
        await self._publish_discovery_config(
            "binary_sensor", "status",
            {
                "name": "Nabaztag Connection",
                "unique_id": "nabaztag_status",
                "state_topic": f"{self.config.topic_prefix}/status",
                "value_template": "{{ 'ON' if value_json.status == 'online' else 'OFF' }}",
                "device_class": "connectivity",
                "icon": "mdi:wifi",
                "device": device_info
            }
        )

        # TTS text input
        await self._publish_discovery_config(
            "text", "tts",
            {
                "name": "Nabaztag TTS",
                "unique_id": "nabaztag_tts",
                "command_topic": f"{self.config.topic_prefix}/tts/say",
                "min": 1,
                "max": 255,
                "icon": "mdi:text-to-speech",
                "device": device_info
            }
        )

    async def _publish_discovery_config(self, component: str, object_id: str, config: Dict):
        """
        Publish Home Assistant discovery configuration.

        Args:
            component: Component type (e.g., "number", "binary_sensor")
            object_id: Object identifier (e.g., "left_ear")
            config: Configuration dictionary
        """
        topic = f"homeassistant/{component}/nabaztag/{object_id}/config"
        payload = json.dumps(config)
        await self._publish_mqtt(topic, payload, qos=self.QOS_STATE, retain=True)

    def start_service_loop(self, loop):
        """Start MQTT client loop in background thread."""
        # Load configuration from database
        async def _load_config_and_start():
            await self.load_config()

            # Only connect if enabled
            if not self.config.enabled:
                logging.info("MQTT bridge is disabled in configuration, not connecting")
                return

            # Setup MQTT client
            self.setup_mqtt_client()

            # Connect to MQTT broker (non-blocking)
            try:
                logging.info(f"Connecting to MQTT broker: {self.config.broker_host}:{self.config.broker_port}")
                await loop.run_in_executor(
                    None,
                    lambda: self.mqtt_client.connect(
                        self.config.broker_host,
                        self.config.broker_port,
                        keepalive=60
                    )
                )
                # Start MQTT network loop in background thread
                self.mqtt_client.loop_start()
            except Exception as e:
                logging.error(f"Failed to connect to MQTT broker: {e}")

        # Schedule config load in asyncio loop
        loop.create_task(_load_config_and_start())

        return None

    async def stop_service_loop(self):
        """Stop MQTT client and publish offline status."""
        self.running = False
        logging.info("Stopping MQTT bridge service")

        if self.mqtt_client:
            await self.publish_status_offline()
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

        logging.info("MQTT bridge stopped")


if __name__ == "__main__":
    NabMqttd.main(sys.argv[1:])
