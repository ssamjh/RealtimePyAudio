import pyaudio
import socket
import time
import logging
import pickle
import os

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024
BUFFER_SIZE = 1 * CHUNK

# for logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

device_info_file = "client_device_info.pkl"
device_info = None if not os.path.exists(
    device_info_file) else pickle.load(open(device_info_file, "rb"))

server_config_file = "server_config.pkl"
server_config = None if not os.path.exists(
    server_config_file) else pickle.load(open(server_config_file, "rb"))


def connect_to_server(server_config):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            client_socket.connect(
                (server_config.get("ip"), server_config.get("port")))
            return client_socket
        except socket.error:
            logger.debug("Connection lost, retrying...")
            time.sleep(0.5)


def find_device_index_by_name(audio, device_name):
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_name == device_info.get('name'):
            return i
    raise Exception('Device not found')


def open_stream(audio):
    device_id = find_device_index_by_name(audio, device_info.get('name'))
    return audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, output_device_index=device_id,
                      frames_per_buffer=BUFFER_SIZE)


audio = pyaudio.PyAudio()

while True:
    try:
        if device_info is None:
            # List all audio output devices
            logger.debug("Available audio output devices:")
            for i in range(audio.get_device_count()):
                device_info_iter = audio.get_device_info_by_index(i)
                if device_info_iter["maxOutputChannels"] > 0:
                    logger.debug(
                        f"ID: {device_info_iter['index']}, Name: {device_info_iter['name']}")
            device_name = input(
                "Please enter the name of the audio output device to use: ")
            device_info = {"name": device_name}
            pickle.dump(device_info, open(device_info_file, "wb"))
        else:
            logger.debug(
                f"Using saved audio output device with name: {device_info.get('name')}")

        if server_config is None:
            # Prompt for server details
            ip = input("Please enter the server IP to use: ")
            port = int(input("Please enter the server port to use: "))
            server_config = {"ip": ip, "port": port}
            pickle.dump(server_config, open(server_config_file, "wb"))
        else:
            logger.debug(
                f"Using saved server config: {server_config}")

        stream = open_stream(audio)

        client_socket = connect_to_server(server_config)

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
