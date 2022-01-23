import socket
import json
import threading
from server import NewlineReceiver

def send(client_socket, d):
    client_socket.send(f"{json.dumps(d)}\n".encode('utf-8'))

class TestClient(threading.Thread):
    def __init__(self, client_socket) -> None:
        super().__init__()
        self.client_socket = client_socket
        self.recv = NewlineReceiver(self.client_socket)

    def handle_message(self, d):
        print("received", d, "\n> ", end="")

    def run(self):
        while True:
            message = self.recv()
            if message is None:
                break
            d = json.loads(message)
            self.handle_message(d)

def main(args):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((args.server, args.port))
    send(client_socket, {"action": "identify", "name": args.name, "game_version": args.game_version})
    if args.create:
        send(client_socket, {"action": "create"})
    else:
        send(client_socket, {"action": "join", "code": args.code})

    t = TestClient(client_socket)
    t.daemon = True
    t.start()
    while True:
        try:
            json_string = input("> ")
            if json_string:
                send(client_socket, json.loads(json_string))
        except Exception as e:
            print(e)
            continue

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default='localhost')
    parser.add_argument("--port", default=9001, type=int)
    parser.add_argument("--name", default="Jacob")
    parser.add_argument("--game-version", default="Test-01")
    parser.add_argument("--code", default="ABCD")
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()

    main(args)
