import socketio

sio = socketio.Client()

@sio.event
def connect():
    print("connected")

@sio.event
def disconnect():
    print("disconnected")
    exit()

sio.connect("http://localhost:5000")

while cmd := input("> ").split():
    sio.emit(*cmd)