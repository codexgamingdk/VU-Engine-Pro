"""The handshake and registration use only an in-process socket pair."""
import base64
import hashlib
import json
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(next((Path(__file__).resolve().parents[1]/"plugin").glob("*.sdPlugin"))))
import meter


class Transport(unittest.TestCase):
    def test_registration(self):
        local, peer = socket.socketpair()
        seen = []
        def host():
            with peer, peer.makefile("rb") as reader:
                headers = {}
                reader.readline()
                for line in iter(reader.readline, b"\r\n"):
                    key, value = line.decode().split(":",1)
                    headers[key.lower()] = value.strip()
                challenge = headers["sec-websocket-key"]+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1(challenge.encode()).digest())
                peer.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "+accept+b"\r\n\r\n")
                header = reader.read(2)
                mask = reader.read(4)
                body = reader.read(header[1]&127)
                seen.append(json.loads(bytes(b^mask[i%4] for i,b in enumerate(body))))
                peer.sendall(b'\x81\x02{}')
        worker=threading.Thread(target=host,daemon=True)
        worker.start()
        # The library sets TCP_NODELAY, which AF_UNIX pairs do not implement.
        class Pair(socket.socket):
            def setsockopt(self,level,opt,value):
                if level != socket.IPPROTO_TCP:
                    super().setsockopt(level,opt,value)
        with patch("socket.create_connection",return_value=Pair(fileno=local.detach())):
            ws=meter.connect_opendeck(1234)
            with patch.object(meter,"_ws",ws):
                meter.send_event({"event":"registerPlugin"})
                self.assertEqual(ws.recv(timeout=2),"{}")
            ws.close()
        worker.join(2)
        self.assertEqual(seen,[{"event":"registerPlugin"}])
