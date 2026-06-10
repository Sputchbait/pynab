import json
import logging

import paho.mqtt.client as mqtt
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from . import rfid_data
from .models import Config
from .nabmqttd import NabMqttd


class SettingsView(TemplateView):
    template_name = "nabmqttd/settings.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["config"] = Config.load()
        return context

    def get(self, request, *args, **kwargs):
        if "test" in request.GET:
            return self._test_connection(request)
        context = self.get_context_data(**kwargs)
        return render(request, SettingsView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        config = Config.load()

        if "broker_host" in request.POST:
            config.broker_host = request.POST["broker_host"]

        if "broker_port" in request.POST:
            try:
                config.broker_port = int(request.POST["broker_port"])
            except ValueError:
                config.broker_port = 1883

        if "broker_username" in request.POST:
            config.broker_username = request.POST["broker_username"]

        if "broker_password" in request.POST:
            config.broker_password = request.POST["broker_password"]

        if "topic_prefix" in request.POST:
            config.topic_prefix = request.POST["topic_prefix"]

        if "client_id" in request.POST:
            config.client_id = request.POST["client_id"]

        config.enabled = "enabled" in request.POST
        config.publish_button_events = "publish_button_events" in request.POST
        config.publish_rfid_events = "publish_rfid_events" in request.POST
        config.publish_ears_state = "publish_ears_state" in request.POST
        config.publish_led_state = "publish_led_state" in request.POST

        config.save()

        # Signal the daemon to reload configuration
        self._signal_daemon()

        context = self.get_context_data(**kwargs)
        return render(request, SettingsView.template_name, context=context)

    def _test_connection(self, request):
        """Test MQTT broker connection via AJAX."""
        import threading

        broker_host = request.GET.get("broker_host", "").strip()
        broker_port = request.GET.get("broker_port", "1883")
        broker_username = request.GET.get("broker_username", "").strip()
        broker_password = request.GET.get("broker_password", "").strip()

        if not broker_host:
            return JsonResponse({
                "status": "error",
                "message": "Broker host is required"
            }, status=400)

        try:
            port = int(broker_port)
        except ValueError:
            return JsonResponse({
                "status": "error",
                "message": "Invalid port number"
            }, status=400)

        connected_event = threading.Event()

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                connected_event.set()

        try:
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                client_id="nabaztag_test",
                protocol=mqtt.MQTTv311
            )
            client.on_connect = on_connect

            if broker_username:
                client.username_pw_set(broker_username, broker_password)

            client.connect(broker_host, port, keepalive=10)
            client.loop_start()

            success = connected_event.wait(timeout=3)
            client.loop_stop()
            client.disconnect()

            if success:
                return JsonResponse({
                    "status": "success",
                    "message": "Successfully connected to MQTT broker"
                })
            else:
                return JsonResponse({
                    "status": "error",
                    "message": "Failed to connect to MQTT broker (timeout)"
                }, status=400)

        except Exception as e:
            logging.error(f"MQTT connection test failed: {e}")
            return JsonResponse({
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }, status=400)

    def _signal_daemon(self):
        """Signal the nabmqttd daemon to reload configuration."""
        NabMqttd.signal_daemon()


class RFIDDataView(TemplateView):
    template_name = "nabmqttd/rfid-data.html"

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        uid = request.GET.get("uid", None)

        event_name = rfid_data.read_data_ui_for_views(uid)

        context["event_name"] = event_name
        context["mqtt_uid"] = uid

        return render(request, RFIDDataView.template_name, context=context)

    def post(self, request, *args, **kwargs):
        data = "DATA_IN_LOCAL_DB"

        uid = request.POST.get("mqtt_uid", "")
        if not uid:
            return JsonResponse({"status": "error", "message": "Missing UID"}, status=400)

        event_name = request.POST.get("event_name", "").strip()
        if event_name:
            event_name = event_name.replace(" ", "_")
        else:
            event_name = uid

        rfid_data.write_data_ui_for_views(uid, event_name)

        return JsonResponse({"data": data})
