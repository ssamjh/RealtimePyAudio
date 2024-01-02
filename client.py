import socket
import sounddevice as sd
import pickle
import logging

logging.basicConfig(filename='client.log', level=logging.DEBUG)


class Client:
    def __init__(self, device_name):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.device_id = None
        self.device_name = device_name

    def setup_sound_card(self):
        devices = sd.query_devices()
        for device in devices:
            if self.device_name in device['name']:
                self.device_id = device['device']
                logging.info(f'Set sound card: {device["name"]}')

    def start(self, host, port):
        self.setup_sound_card()

        self.sock.connect((host, port))
        logging.debug(f'Connected to server at {host}:{port}')

        stream = sd.OutputStream(device=self.device_id)
        stream.start()

        while True:
            data = self.sock.recv(4096)
            if not data:
                logging.warning('Connection dropped. Reconnecting...')
                self.sock.connect((host, port))

            try:
                # Assuming the server is periodically sending audio packets
                audio_data = pickle.loads(data)
                stream.write(audio_data)
            except (pickle.UnpicklingError, EOFError):
                logging.warning(
                    'Corrupted packet received. Requesting retransmission...')
                # Send your retransmission request here
