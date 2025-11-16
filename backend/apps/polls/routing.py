"""
WebSocket URL routing for polls app.
"""

from django.urls import re_path

from .consumers import PollResultsConsumer

websocket_urlpatterns = [
    re_path(r"ws/polls/(?P<poll_id>\d+)/results/$", PollResultsConsumer.as_asgi()),
]

