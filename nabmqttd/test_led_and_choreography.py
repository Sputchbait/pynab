"""
Test suite for LED per-LED control and choreography features.

These tests follow TDD approach - they should FAIL initially,
then PASS after implementation.
"""

import unittest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys

# Mock all external dependencies before importing nabmqttd
sys.modules['django'] = MagicMock()
sys.modules['django.db'] = MagicMock()
sys.modules['django.db.models'] = MagicMock()
sys.modules['aiohttp'] = MagicMock()
sys.modules['paho'] = MagicMock()
sys.modules['paho.mqtt'] = MagicMock()
sys.modules['paho.mqtt.client'] = MagicMock()

# Mock nabcommon but create a minimal NabService base class
nabcommon_mock = MagicMock()
sys.modules['nabcommon'] = nabcommon_mock
sys.modules['nabcommon.typing'] = MagicMock()

# Create a real NabService base class that doesn't interfere
class FakeNabService:
    def __init__(self):
        pass

nabcommon_settings = MagicMock()
nabcommon_settings.configure = MagicMock()
sys.modules['nabcommon.settings'] = nabcommon_settings

nabcommon_nabservice = MagicMock()
nabcommon_nabservice.NabService = FakeNabService
sys.modules['nabcommon.nabservice'] = nabcommon_nabservice


class TestPerLEDControl(unittest.IsolatedAsyncioTestCase):
    """Test suite for per-LED control (individual LED colors)."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Import after mocking Django
        from nabmqttd import NabMqttd

        # Mock Config class
        mock_config = Mock()
        mock_config.topic_prefix = "nabaztag"
        mock_config.broker_host = "192.168.1.195"
        mock_config.broker_port = 1883
        mock_config.enabled = True

        self.service = NabMqttd()
        self.service.config = mock_config
        self.service.writer = AsyncMock()
        self.service.mqtt_client = Mock()
        self.service.loop = asyncio.get_event_loop()

    async def test_per_led_individual_colors(self):
        """
        Test that individual LED colors are applied correctly.

        Note: Requires patched nabd that supports all 5 LEDs.
        """
        # Arrange - all 5 LEDs
        led_colors = {
            "nose": "ff0000",
            "left": "ff7f00",
            "center": "ffff00",
            "right": "00ff00",
            "bottom": "0000ff"
        }

        # Act
        packet = self.service._build_per_led_packet(led_colors)

        # Assert
        self.assertEqual(packet["type"], "info")
        self.assertEqual(packet["info_id"], "nabmqttd_leds")
        self.assertIn("animation", packet)
        self.assertEqual(packet["animation"]["tempo"], 1000)

        colors = packet["animation"]["colors"][0]
        self.assertEqual(colors["nose"], "FF0000")
        self.assertEqual(colors["left"], "FF7F00")
        self.assertEqual(colors["center"], "FFFF00")
        self.assertEqual(colors["right"], "00FF00")
        self.assertEqual(colors["bottom"], "0000FF")

    async def test_per_led_partial_update(self):
        """Test that partial LED updates work (only some LEDs specified)."""
        # Arrange - only specify nose and bottom
        led_colors = {
            "nose": "ffffff",
            "bottom": "ffffff"
        }

        # Act
        packet = self.service._build_per_led_packet(led_colors)

        # Assert
        colors = packet["animation"]["colors"][0]
        self.assertEqual(colors["nose"], "FFFFFF")
        self.assertEqual(colors["bottom"], "FFFFFF")
        # Others should default to black
        self.assertEqual(colors["left"], "000000")
        self.assertEqual(colors["center"], "000000")
        self.assertEqual(colors["right"], "000000")

    async def test_per_led_color_validation(self):
        """Test that invalid colors are normalized to black."""
        # Arrange - mix of valid and invalid colors
        led_colors = {
            "nose": "invalid",
            "left": "12345",  # Too short
            "center": "ff0000",  # Valid
            "right": "#00ff00",  # Valid with #
            "bottom": "0000ff"  # Valid
        }

        # Act
        packet = self.service._build_per_led_packet(led_colors)

        # Assert
        colors = packet["animation"]["colors"][0]
        self.assertEqual(colors["nose"], "000000")  # Invalid → black
        self.assertEqual(colors["left"], "000000")  # Too short → black
        self.assertEqual(colors["center"], "FF0000")  # Valid
        self.assertEqual(colors["right"], "00FF00")  # # stripped
        self.assertEqual(colors["bottom"], "0000FF")  # Valid

    async def test_led_single_color_still_works(self):
        """Test that old leds/set endpoint still works (backward compatibility)."""
        # Arrange
        data = {"color": "ff00ff"}

        # Act
        await self.service._handle_mqtt_command(
            "nabaztag/leds/set",
            json.dumps(data).encode('utf-8')
        )

        # Assert - writer should have been called with nabd packet
        self.service.writer.write.assert_called_once()
        written_data = self.service.writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())

        # All 5 LEDs should have the same color
        colors = packet["animation"]["colors"][0]
        self.assertEqual(colors["nose"], "FF00FF")
        self.assertEqual(colors["left"], "FF00FF")
        self.assertEqual(colors["center"], "FF00FF")
        self.assertEqual(colors["right"], "FF00FF")
        self.assertEqual(colors["bottom"], "FF00FF")


class TestChoreographyControl(unittest.IsolatedAsyncioTestCase):
    """Test suite for choreography playback."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Import after mocking Django
        from nabmqttd import NabMqttd

        # Mock Config class
        mock_config = Mock()
        mock_config.topic_prefix = "nabaztag"
        mock_config.broker_host = "192.168.1.195"
        mock_config.broker_port = 1883
        mock_config.enabled = True

        self.service = NabMqttd()
        self.service.config = mock_config
        self.service.writer = AsyncMock()
        self.service.mqtt_client = Mock()
        self.service.loop = asyncio.get_event_loop()

    async def test_choreography_streaming_urn(self):
        """Test streaming choreography URN."""
        # Arrange
        data = {"choreography": "urn:x-chor:streaming"}

        # Act
        await self.service._handle_choreography(data)

        # Assert - should have sent to nabd
        self.service.writer.write.assert_called_once()
        written_data = self.service.writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())

        self.assertEqual(packet["type"], "command")
        self.assertIn("sequence", packet)
        self.assertEqual(packet["sequence"][0]["choreography"], "urn:x-chor:streaming")
        self.assertIn("request_id", packet)

    async def test_choreography_named_resource(self):
        """Test playing named choreography resource."""
        # Arrange
        data = {"choreography": "nabtaichid/taichi.chor"}

        # Act
        await self.service._handle_choreography(data)

        # Assert
        self.service.writer.write.assert_called_once()
        written_data = self.service.writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())

        self.assertEqual(packet["type"], "command")
        self.assertEqual(packet["sequence"][0]["choreography"], "nabtaichid/taichi.chor")

    async def test_choreography_with_audio(self):
        """Test choreography combined with audio playback."""
        # Arrange
        data = {
            "choreography": "urn:x-chor:streaming",
            "audio": ["http://example.com/sound.mp3"]
        }

        # Act
        await self.service._handle_choreography(data)

        # Assert
        self.service.writer.write.assert_called_once()
        written_data = self.service.writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())

        self.assertEqual(packet["type"], "command")
        sequence = packet["sequence"][0]
        self.assertEqual(sequence["choreography"], "urn:x-chor:streaming")
        self.assertEqual(sequence["audio"], ["http://example.com/sound.mp3"])

    async def test_choreography_invalid_format_rejected(self):
        """Test that invalid choreography references are rejected."""
        # Arrange - invalid choreography (no recognizable format)
        data = {"choreography": "invalid_format"}

        # Act
        with patch('logging.warning') as mock_warning:
            await self.service._handle_choreography(data)

        # Assert - should log warning and not send to nabd
        mock_warning.assert_called()
        self.service.writer.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
