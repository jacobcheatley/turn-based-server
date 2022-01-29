import json
import random
import socket
import threading
from typing import Dict, List


class LobbyDoesntExistException(Exception):
    pass

class LobbyFullException(Exception):
    pass

class MismatchedVersionException(Exception):
    pass

class AlreadyConnectedException(Exception):
    pass

class Lobby:
    lobbies: Dict[str, "Lobby"] = {}

    def __init__(self, code: str, version: str) -> None:
        self.code = code
        self.version = version
        self.clients: Dict[str, "ClientThread"] = {}
        self.max_players = 2

    def message(self, d: dict, exclude=None):
        if exclude is None:
            exclude = []

        for client_name, client_thread in self.clients.items():
            if client_thread not in exclude:
                client_thread.send_json(d)

    def disconnect(self, name: str):
        self.clients[name] = None
        # TODO: Maybe allow reconnects to bricked lobbies? Otherwise, eh
        if all([c is None for c in self.clients.values()]):
            del self.lobbies[self.code]
            print(f"Deleting lobby {self.code}")
            # And then we should be garbage collected?
        for client_name, client_thread in self.clients.items():
            if client_thread is not None:
                client_thread.send_json({"action": "disconnect", "name": name})

    def connect(self, client_thread):
        self.clients[client_thread.name] = client_thread
        self.message({"action": "connect", "name": client_thread.name})

    @classmethod
    def generate_code(cls):
        while True:
            code = "".join([random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(4)])
            if code not in cls.lobbies:
                return code

    @classmethod
    def create(cls, client_thread: "ClientThread", version: str) -> "Lobby":
        code = cls.generate_code()
        lobby = cls(code, version)
        cls.lobbies[code] = lobby
        lobby.connect(client_thread)
        lobby.message({"action": "code", "code": code})
        return lobby

    @classmethod
    def join(cls, client_thread: "ClientThread", code: str, version: str) -> "Lobby":
        if code not in cls.lobbies:
            raise LobbyDoesntExistException()
        lobby = cls.lobbies[code]
        if lobby.version != version:
            raise MismatchedVersionException(lobby.version)
        if client_thread.name in lobby.clients and lobby.clients[client_thread.name] is not None:
            raise AlreadyConnectedException()
        if client_thread.name not in lobby.clients and len(lobby.clients) >= lobby.max_players:
            raise LobbyFullException()
        lobby.connect(client_thread)
        return lobby

class NewlineReceiver:
    def __init__(self, client_socket: socket.socket) -> None:
        self.buffer = b''
        self.client_socket = client_socket

    def __call__(self):
        delimiter = b'\n'
        while delimiter not in self.buffer:
            try:
                data = self.client_socket.recv(1024)
            except ConnectionResetError:
                return None
            if not data:  # Client connection closed
                return None
            self.buffer += data
        line, sep, self.buffer = self.buffer.partition(delimiter)
        return line.decode('utf-8')

class ClientThread(threading.Thread):
    def __init__(self, client_socket: socket.socket, address) -> None:
        super().__init__()
        self.client_socket = client_socket
        self.address = address

        self.recv = NewlineReceiver(self.client_socket)

        self.name: str = None
        self.game_version: str = None
        self.lobby: Lobby = None

    def send_json(self, d: dict):
        self.send_string(json.dumps(d))

    def send_string(self, message: str):
        self.client_socket.send(f"{message}\n".encode('utf-8'))

    def handle_message(self, d: dict):
        print("message", d)
        if "action" not in d:
            self.send_json({"action": "error", "type": "unknown_action"})
            return
        match d["action"]:
            case "identify":
                self.action_identify(d)
            case "create":
                self.action_create(d)
            case "join":
                self.action_join(d)
            case "turn":
                self.action_turn(d)
            case _:
                self.send_json({"action": "error", "type": "unknown_action"})

    def action_identify(self, d: dict):
        self.name = d["name"]
        self.game_version = d["game_version"]
        self.send_json({"action": "message", "message": f"Hi {self.name} using {self.game_version}"})

    def action_create(self, d: dict):
        if self.name is None:
            self.send_json({"action": "error", "type": "unidentified"})
        else:
            self.lobby = Lobby.create(self, self.game_version)

    def action_join(self, d: dict):
        if self.name is None:
            self.send_json({"action": "error", "type": "unidentified"})
        else:
            try:
                self.lobby = Lobby.join(self, d["code"], self.game_version)
            except LobbyDoesntExistException:
                self.send_json({"action": "error", "type": "lobby_doesnt_exist"})
            except MismatchedVersionException as e:
                self.send_json({"action": "error", "type": "mismatched_version", "message": str(e)})
            except AlreadyConnectedException:
                self.send_json({"action": "error", "type": "already_connected"})
            except LobbyFullException:
                self.send_json({"action": "error", "type": "lobby_full"})

    def action_turn(self, d: dict):
        if self.name is None:
            self.send_json({"action": "error", "type": "unidentified"})
        elif self.lobby is None:
            self.send_json({"action": "error", "type": "not_in_lobby"})
        else:
            self.lobby.message({**d, "name": self.name}, exclude=[self])

    def run(self):
        while True:
            message = self.recv()
            if message is None:
                break
            d = json.loads(message)
            self.handle_message(d)
        # Handle disconnect logic
        if self.lobby is not None:
            self.lobby.disconnect(self.name)
            print(f"Client {str(self)} disconnected")
        self.client_socket.close()
    
    def __str__(self):
        return f"Client(name={self.name}, lobby={None if self.lobby is None else self.lobby.code})"

def main(args):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((args.host, args.port))
    server_socket.listen(16)
    print(f"Listening on {server_socket}")

    while True:
        client_socket, address = server_socket.accept()
        client_thread = ClientThread(client_socket, address)
        client_thread.daemon = True
        client_thread.start()
    
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=9001, type=int)
    parser.add_argument("--host", default="localhost")  # 0.0.0.0 for external
    args = parser.parse_args()

    main(args)
