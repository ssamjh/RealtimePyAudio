import pyaudio
import socket
import time
import logging
import pickle
import os

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
CHUNK = 1024
BUFFER_SIZE = 8 * CHUNK

# for logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

config_file = "config-client.pkl"
config = None if not os.path.exists(
    config_file) else pickle.load(open(config_file, "rb"))


def connect_to_server(server_config):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            client_socket.connect(
                (server_config['ip'], server_config['port']))
            return client_socket
        except socket.error:
            logger.debug("Connection lost, retrying...")
            time.sleep(5)


def open_stream(audio, device_id):
    return audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True,
                      output_device_index=device_id, frames_per_buffer=BUFFER_SIZE)


audio = pyaudio.PyAudio()

while True:
    try:
        if config is None:
            # List all audio output devices
            logger.debug("Available audio output devices:")
            device_ids = []
            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if device_info["maxOutputChannels"] > 0:
                    device_ids.append(device_info['index'])
                    logger.debug(
                        f"ID: {device_info['index']}, Name: {device_info['name']}")
            device_id = int(
                input("Please enter the ID of the audio output device to use: "))
            if device_id not in device_ids:
                logger.debug("Invalid device ID")
                continue
            ip = input("Please enter the server IP to use: ")
            port = int(
                input("Please enter the server port to use (default is 12998): ") or "12998")
            config = {"device_id": device_id, "ip": ip, "port": port}
            pickle.dump(config, open(config_file, "wb"))
        else:
            logger.debug(f"Using saved config: {config}")

        stream = open_stream(audio, config['device_id'])

        client_socket = connect_to_server(config)

        while True:
            data = b''
            while len(data) < CHUNK:
                packet = client_socket.recv(CHUNK - len(data))
                if not packet:
                    break
                data += packet

            stream.write(data, exception_on_underflow=True)

    except (OSError, IOError) as e:
        logger.error(f"Buffer Error: {e}")
        client_socket.close()
        try:
            stream.stop_stream()
            stream.close()
        except OSError:
            logger.debug("Stream already closed")
        continue
