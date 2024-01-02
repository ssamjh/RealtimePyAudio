import pyaudio
import socket
import logging
import pickle
import os

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024

# for logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def find_device_index_by_name(audio, device_name):
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_name == device_info.get('name'):
            return i
    raise Exception('Device not found')


config_file = "config-server.pkl"
config = None if not os.path.exists(
    config_file) else pickle.load(open(config_file, "rb"))

audio = pyaudio.PyAudio()
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# If config not set manually
if config is None:
    # List all audio input devices
    logger.debug("Available audio input devices:")
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_info["maxInputChannels"] > 0:
            logger.debug(
                f"ID: {device_info['index']}, Name: {device_info['name']}")
    device_name = input(
        "Please enter the name of the audio input device to use: ")
    port = int(
        input("Please enter the server port to use (default is 12998): ") or "12998")
    config = {"name": device_name, "port": port}
    pickle.dump(config, open(config_file, "wb"))
else:
    logger.debug(f"Using saved config: {config}")

device_id = find_device_index_by_name(audio, config.get('name'))

stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK, input_device_index=device_id)

try:
    server_socket.bind(("", config['port']))
    server_socket.listen(5)
    logger.debug("Server is listening...")

    while True:
        try:
            conn, addr = server_socket.accept()
            logger.debug(f"Connection from: {addr}")
            logger.debug(f"Device used: {config['name']}")
            logger.debug("Streaming audio...")

            while True:
                data = stream.read(CHUNK)
                conn.sendall(data)
        except Exception as e:
            logger.error(f"Error occurred: {e}")

finally:
    stream.stop_stream()
    stream.close()
    audio.terminate()
    server_socket.close()
