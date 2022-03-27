import logging
from dataclasses import dataclass

import socketio
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from dataclasses_json import DataClassJsonMixin

import player


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class InitMessage(DataClassJsonMixin):
    status: player.Status
    songs: list[player.NearerSong]
    current_song_idx: int
    time: int
    length: int

@dataclass
class AddedMessage(DataClassJsonMixin):
    status: player.Status
    song: player.NearerSong
    current_song_idx: int

@dataclass
class SongEndedMessage(DataClassJsonMixin):
    status: player.Status
    current_song_idx: int

@dataclass
class StatusUpdateMessage(DataClassJsonMixin):
    status: player.Status
    time: int
    length: int

@dataclass
class TimeUpdateMessage(DataClassJsonMixin):
    time: int
    length: int


def emit_song_ended():
    msg_json = SongEndedMessage(p.status, p.current_song_idx).to_json()
    sio.emit("ended", msg_json)

def emit_status():
    msg_json = StatusUpdateMessage(p.status, *p.get_progress()).to_json()
    sio.emit("status", msg_json)

def emit_progress():
    pass
    # msg_json = TimeUpdateMessage(*p.get_progress()).to_json()
    # sio.emit("time", msg_json)


p = player.Player(emit_song_ended, emit_status)

# sio = socketio.Server(logger=logger, async_mode='gevent', cors_allowed_origins='https://blacker.caltech.edu')
sio = socketio.Server(logger=logger, cors_allowed_origins='*')
app = socketio.WSGIApp(sio)


@sio.event
def connect(sid, environ, auth):
    logger.info(f"connected to {sid}")

    msg_json = InitMessage(p.status, p.all_songs, p.current_song_idx, *p.get_progress()).to_json()
    sio.emit("init", msg_json)

    # If a song is playing or paused, emit progress
    if p.status != player.Status.STOPPED:
        emit_progress()

@sio.event
def disconnect(sid):
    logger.info(f"disconnected from {sid}")

@sio.event
def pause(sid, data=None):
    p.toggle_pause()
    # emit_status()

@sio.event
def next(sid, data=None):
    p.next()
    emit_song_ended()

@sio.event
def add(sid, data):
    try:
        p.add_song(data)
    except ValueError as e:
        sio.emit("error", str(e), to=sid)
        pass
    else:
        msg_json = AddedMessage(p.status, p.all_songs[0], p.current_song_idx).to_json()
        sio.emit("added", msg_json)


if __name__ == "__main__":
    pywsgi.WSGIServer(('', 5000), app, handler_class=WebSocketHandler, log=logger).serve_forever()