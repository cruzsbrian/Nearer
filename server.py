import logging

import socketio
import eventlet

import player


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def song_ended():
    pass


p = player.Player(song_ended)

sio = socketio.Server(logger=logger)
app = socketio.WSGIApp(sio)


@sio.event
def connect(sid, environ, auth):
    print(f"connected to {sid}")

@sio.event
def disconnect(sid):
    print(f"disconnected from {sid}")

@sio.event
def pause(sid, data=None):
    p.toggle_pause() 

@sio.event
def next(sid, data=None):
    p.next()

@sio.event
def add(sid, data):
    p.add_song(data)

@sio.event
def info(sid):
    p.print_info()

@sio.event
def queue(sid):
    p.print_queue()


if __name__ == "__main__":
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app, log=logger)