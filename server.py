import logging
from dataclasses import dataclass

import socketio

from dataclasses_json import DataClassJsonMixin

import player


logging.basicConfig(level=logging.INFO, filename="nearer.log")
logger = logging.getLogger(__name__)
userlog = logging.getLogger("users")
userlog.addHandler(logging.FileHandler("nearer_users.log"))

usernames = {}


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

sio = socketio.Server(logger=logging.getLogger('socketio'), cors_allowed_origins='*', async_mode='threading')
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
    if sid in usernames:
        userlog.info(f"{usernames[sid]} disconnected")
        del usernames[sid]
    else:
        logger.info(f"disconnected from {sid}")

@sio.event
def user(sid, data):
    usernames[sid] = data 
    userlog.info(f"{usernames[sid]} connected")

@sio.event
def pause(sid, data=None):
    if p.status == player.Status.PAUSED:
        userlog.info(f"{usernames[sid]} played")
    else:
        userlog.info(f"{usernames[sid]} paused")

    p.toggle_pause()

@sio.event
def next(sid, data=None):
    userlog.info(f"{usernames[sid]} skipped")
    p.next()
    emit_song_ended()

@sio.event
def add(sid, data):
    userlog.info(f"{usernames[sid]} added {data}")
    try:
        p.add_song(usernames[sid], data)
    except ValueError as e:
        sio.emit("error", str(e), to=sid)

    msg_json = AddedMessage(p.status, p.all_songs[0], p.current_song_idx).to_json()
    sio.emit("added", msg_json)
