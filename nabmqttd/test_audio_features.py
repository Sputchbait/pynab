#!/usr/bin/env python3
"""
Unit tests for Phase 1 and Phase 2 audio/voice features in nabmqttd.

Test-Driven Development approach:
1. Write test (RED)
2. Implement feature (GREEN)
3. Refactor (REFACTOR)
"""

import asyncio
import json
import unittest
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
import subprocess

# Mock Django before importing nabmqttd modules
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock Django components
sys.modules['django'] = MagicMock()
sys.modules['django.db'] = MagicMock()
sys.modules['django.db.models'] = MagicMock()
sys.modules['nabcommon'] = MagicMock()
sys.modules['nabcommon.settings'] = MagicMock()
sys.modules['nabcommon.nabservice'] = MagicMock()
sys.modules['nabcommon.typing'] = MagicMock()
sys.modules['nabcommon.singleton_model'] = MagicMock()


class TestVolumeControl(unittest.IsolatedAsyncioTestCase):
    """Test suite for MQTT volume control feature (Phase 1)."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Import after mocking
        from nabmqttd import NabMqttd
        from models import Config

        self.service = NabMqttd()
        self.service.config = Config()
        self.service.config.topic_prefix = "nabaztag"
        self.service.config.enabled = True
        self.service.mqtt_client = Mock()
        self.service.mqtt_connected = True
        self.service.loop = asyncio.get_event_loop()

    async def test_volume_set_topic_subscription(self):
        """Test that volume/set topic is subscribed on MQTT connect."""
        # Arrange
        expected_topic = "nabaztag/audio/volume/set"

        # Act
        self.service._subscribe_command_topics()

        # Assert
        subscribe_calls = self.service.mqtt_client.subscribe.call_args_list
        topics_subscribed = [call[0][0] for call in subscribe_calls]
        self.assertIn(expected_topic, topics_subscribed,
                     "Volume set topic should be subscribed")

    async def test_volume_set_mqtt_message_parsing(self):
        """Test parsing volume value from MQTT message."""
        # Arrange
        test_volume = 75
        mqtt_msg = Mock()
        mqtt_msg.topic = "nabaztag/audio/volume/set"
        mqtt_msg.payload = str(test_volume).encode('utf-8')

        # Act
        await self.service._handle_mqtt_command(mqtt_msg)

        # Assert - should call volume handler with parsed value
        # This will fail until implementation exists (RED)
        self.assertTrue(hasattr(self.service, '_handle_volume_set'),
                       "Service should have _handle_volume_set method")

    @patch('subprocess.run')
    async def test_volume_set_calls_alsa(self, mock_subprocess):
        """Test that volume change calls ALSA amixer command."""
        # Arrange
        test_volume = 80

        # Act
        await self.service._handle_volume_set(test_volume)

        # Assert
        mock_subprocess.assert_called_once()
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn('amixer', call_args)
        self.assertIn('sset', call_args)
        self.assertIn(f'{test_volume}%', call_args)

    @patch('subprocess.run')
    async def test_volume_set_bounds_checking(self, mock_subprocess):
        """Test volume value is constrained to 0-100 range."""
        # Arrange & Act & Assert

        # Test lower bound
        await self.service._handle_volume_set(-10)
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn('0%', call_args, "Negative volume should clamp to 0")

        # Test upper bound
        await self.service._handle_volume_set(150)
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn('100%', call_args, "Over-100 volume should clamp to 100")

        # Test valid range
        await self.service._handle_volume_set(50)
        call_args = mock_subprocess.call_args[0][0]
        self.assertIn('50%', call_args, "Valid volume should pass through")

    async def test_volume_state_published_after_set(self):
        """Test that volume state is published to MQTT after setting."""
        # Arrange
        test_volume = 65
        expected_topic = "nabaztag/audio/volume/state"

        with patch('subprocess.run'):
            # Act
            await self.service._handle_volume_set(test_volume)

            # Assert
            publish_calls = self.service.mqtt_client.publish.call_args_list
            published_topics = [call[0][0] for call in publish_calls]
            self.assertIn(expected_topic, published_topics,
                         "Volume state should be published after change")

            # Verify payload
            for call in publish_calls:
                if call[0][0] == expected_topic:
                    payload = call[0][1]
                    self.assertEqual(str(test_volume), payload)

    async def test_volume_discovery_message_format(self):
        """Test Home Assistant discovery message for volume control."""
        # Arrange
        expected_discovery_topic = "homeassistant/number/nabaztag/volume/config"

        # Act
        await self.service.publish_mqtt_discovery()

        # Assert
        publish_calls = self.service.mqtt_client.publish.call_args_list

        # Find discovery message
        discovery_found = False
        for call in publish_calls:
            if expected_discovery_topic in call[0][0]:
                discovery_found = True
                payload = json.loads(call[0][1])

                # Verify required fields
                self.assertEqual(payload['name'], 'Volume')
                self.assertEqual(payload['command_topic'], 'nabaztag/audio/volume/set')
                self.assertEqual(payload['state_topic'], 'nabaztag/audio/volume/state')
                self.assertEqual(payload['min'], 0)
                self.assertEqual(payload['max'], 100)
                self.assertEqual(payload['step'], 5)
                self.assertIn('unique_id', payload)
                self.assertIn('device', payload)
                break

        self.assertTrue(discovery_found,
                       "Volume discovery message should be published")


class TestAudioPlayback(unittest.IsolatedAsyncioTestCase):
    """Test suite for URL audio playback feature (Phase 1)."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        from nabmqttd import NabMqttd
        from models import Config

        self.service = NabMqttd()
        self.service.config = Config()
        self.service.config.topic_prefix = "nabaztag"
        self.service.nabd_writer = AsyncMock()
        self.service.mqtt_client = Mock()
        self.service.loop = asyncio.get_event_loop()

    async def test_audio_play_topic_subscription(self):
        """Test that audio/play topic is subscribed."""
        # Arrange
        expected_topic = "nabaztag/audio/play"

        # Act
        self.service._subscribe_command_topics()

        # Assert
        subscribe_calls = self.service.mqtt_client.subscribe.call_args_list
        topics_subscribed = [call[0][0] for call in subscribe_calls]
        self.assertIn(expected_topic, topics_subscribed)

    async def test_audio_play_sends_nabd_command(self):
        """Test that audio URL triggers nabd command packet."""
        # Arrange
        test_url = "http://example.com/sound.mp3"

        # Act
        await self.service._handle_play_audio(test_url)

        # Assert
        self.service.nabd_writer.write.assert_called_once()
        written_data = self.service.nabd_writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())

        self.assertEqual(packet['type'], 'command')
        self.assertIn('sequence', packet)
        self.assertIn('audio', packet['sequence'][0])
        self.assertEqual(packet['sequence'][0]['audio'][0], test_url)

    async def test_audio_play_validates_url_format(self):
        """Test that invalid URLs are rejected."""
        # Arrange
        invalid_urls = [
            "",  # Empty
            "not-a-url",  # No protocol
            "ftp://invalid.com/file.mp3",  # Wrong protocol
        ]

        # Act & Assert
        for url in invalid_urls:
            with self.assertRaises(ValueError):
                await self.service._handle_play_audio(url)

    async def test_audio_play_supports_local_files(self):
        """Test that local file paths are supported."""
        # Arrange
        test_path = "/opt/pynab/sounds/test.mp3"

        # Act
        await self.service._handle_play_audio(test_path)

        # Assert
        written_data = self.service.nabd_writer.write.call_args[0][0]
        packet = json.loads(written_data.decode('utf-8').strip())
        self.assertEqual(packet['sequence'][0]['audio'][0], test_path)


class TestPynabServiceTriggers(unittest.IsolatedAsyncioTestCase):
    """Test suite for Pynab service trigger features (Phase 1)."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        from nabmqttd import NabMqttd
        from models import Config

        self.service = NabMqttd()
        self.service.config = Config()
        self.service.config.topic_prefix = "nabaztag"
        self.service.mqtt_client = Mock()

    async def test_weather_trigger_topic_subscription(self):
        """Test that service trigger topics are subscribed."""
        # Arrange
        expected_topics = [
            "nabaztag/service/weather/trigger",
            "nabaztag/service/clock/trigger"
        ]

        # Act
        self.service._subscribe_command_topics()

        # Assert
        subscribe_calls = self.service.mqtt_client.subscribe.call_args_list
        topics_subscribed = [call[0][0] for call in subscribe_calls]

        for topic in expected_topics:
            self.assertIn(topic, topics_subscribed)

    @patch('aiohttp.ClientSession')
    async def test_weather_trigger_calls_http_endpoint(self, mock_session):
        """Test that weather trigger calls nabweatherd HTTP endpoint."""
        # Arrange
        mock_post = AsyncMock()
        mock_session.return_value.__aenter__.return_value.post = mock_post

        # Act
        await self.service._trigger_pynab_service("nabweatherd")

        # Assert
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertIn("nabweatherd", call_url)

    async def test_service_trigger_discovery_buttons(self):
        """Test HA discovery for service trigger buttons."""
        # Arrange
        expected_buttons = [
            "homeassistant/button/nabaztag/weather/config",
            "homeassistant/button/nabaztag/clock/config"
        ]

        # Act
        await self.service.publish_mqtt_discovery()

        # Assert
        publish_calls = self.service.mqtt_client.publish.call_args_list
        published_topics = [call[0][0] for call in publish_calls]

        for button_topic in expected_buttons:
            self.assertIn(button_topic, published_topics)


if __name__ == '__main__':
    unittest.main()
