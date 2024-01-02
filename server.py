import pyaudio
import socket
import logging
import pickle
import os

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 48000
CHUNK = 2 * 1024

# for logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

config_file = "config-server.pkl"
config = None if not os.path.exists(
    config_file) else pickle.load(open(config_file, "rb"))

audio = pyaudio.PyAudio()
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# If config not set manually
if config is None:
    # List all audio input devices
    logger.debug("Available audio input devices:")
    device_ids = []
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_info["maxInputChannels"] > 0:
            device_ids.append(device_info['index'])
            logger.debug(
                f"ID: {device_info['index']}, Name: {device_info['name']}")

    # Get the device id from the user and ensure it is a valid id
    device_id = None
    while device_id is None or device_id not in device_ids:
        device_id = int(
            input("Please enter the ID of the audio input device to use: "))
        if device_id not in device_ids:
            logger.debug("Invalid device ID")

    port = int(
        input("Please enter the server port to use (default is 12998): ") or "12998")
    config = {"id": device_id, "port": port}
    pickle.dump(config, open(config_file, "wb"))
else:
    logger.debug(f"Using saved config: {config}")

stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK, input_device_index=config.get('id'))

try:
    server_socket.bind(("", config['port']))
    server_socket.listen(5)
    logger.debug("Server is listening...")

    while True:
        try:
            conn, addr = server_socket.accept()
            logger.debug(f"Connection from: {addr}")
            logger.debug(f"Device used: {config['id']}")
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
