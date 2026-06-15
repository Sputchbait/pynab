NABAZTAG_SERVICE_PRIORITY = 3
NABAZTAG_RFID_APPLICATION_ID = 14
NABAZTAG_RFID_APPLICATION_NAME = "MQTT Bridge"
NABAZTAG_EVENTS_SUBSCRIPTION = ["button", "state", "ears"]

# Lazy import for tests (dependencies may not be installed locally)
def __getattr__(name):
    if name == 'NabMqttd':
        from .nabmqttd import NabMqttd as _NabMqttd
        return _NabMqttd
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ['NabMqttd']
