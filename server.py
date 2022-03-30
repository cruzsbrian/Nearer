import logging
from dataclasses import dataclass

import socketio
from dataclasses_json import DataClassJsonMixin

import player


# Set up logging:
# All logs are written to nearer.log, and only user actions (adding, pausing, skipping, etc)
# are also written to nearer_users.log.
logging.basicConfig(level=logging.INFO, filename="nearer.log")
logger = logging.getLogger(__name__)
sio_logger = logging.getLogger('socketio')
userlog = logging.getLogger("users")
userlog.addHandler(logging.FileHandler("nearer_users.log"))

# Dict to store the username associated with each client.
# Deleted when the client disconnects.
usernames = {}


# SocketIO message types:

@dataclass
class InitMessage(DataClassJsonMixin):
    """
    server -> client message sent upon connection.
    Sent only to the client that connected.
    """
    status: player.Status
    songs: list[player.NearerSong]
    current_song_idx: int
    time: int
    length: int

@dataclass
class AddedMessage(DataClassJsonMixin):
    """
    server -> client message sent when a song is successfully added.
    Sent to all clients.
    """
    status: player.Status
    song: player.NearerSong
    current_song_idx: int

@dataclass
class SongEndedMessage(DataClassJsonMixin):
    """
    server -> client message sent when the current song ends.
    Sent to all clients.
    """
    status: player.Status
    current_song_idx: int

@dataclass
class StatusUpdateMessage(DataClassJsonMixin):
    """
    server -> client message sent when player status updates (playing/pausing/etc).
    Sent to all clients.
    """
    status: player.Status
    time: int
    length: int


# Message emit functions used by the player:

def emit_song_ended():
    msg_json = SongEndedMessage(p.status, p.current_song_idx).to_json()
    sio.emit("ended", msg_json)

def emit_status():
    msg_json = StatusUpdateMessage(p.status, *p.get_progress()).to_json()
    sio.emit("status", msg_json)

p = player.Player(emit_song_ended, emit_status)

# Initialize socketio server.
# Async mode must be 'threading' for vlc callbacks to be able to emit messages.
sio = socketio.Server(sio_logger, cors_allowed_origins='*', async_mode='threading')
app = socketio.WSGIApp(sio)


# Upon connection, send init message.
@sio.event
def connect(sid, environ, auth):
    logger.info(f"connected to {sid}")

    msg_json = InitMessage(p.status, p.all_songs, p.current_song_idx, *p.get_progress()).to_json()
    sio.emit("init", msg_json, to=sid)

# Upon disconnection, delete username from dict.
@sio.event
def disconnect(sid):
    if sid in usernames:
        userlog.info(f"{usernames[sid]} disconnected")
        del usernames[sid]
    else:
        logger.info(f"disconnected from {sid}")

# Client should send its username immediately after connecting.
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
    
    # Player.add_song() throws a ValueError if it can't get a valid stream for the song.
    try:
        p.add_song(usernames[sid], data)
    except ValueError as e:
        sio.emit("error", str(e), to=sid)
    else:
        msg_json = AddedMessage(p.status, p.all_songs[0], p.current_song_idx).to_json()
        sio.emit("added", msg_json)
