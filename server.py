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

audio = pyaudio.PyAudio()
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

device_id_file = "server_device_id.pkl"
device_id = None if not os.path.exists(
    device_id_file) else pickle.load(open(device_id_file, "rb"))

# If device_id not set manually
if device_id is None:
    # List all audio input devices
    logger.debug("Available audio input devices:")
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_info["maxInputChannels"] > 0:
            logger.debug(
                f"ID: {device_info['index']}, Name: {device_info['name']}")
    device_id = int(
        input("Please enter the ID of the audio input device to use: "))
    pickle.dump(device_id, open(device_id_file, "wb"))
else:
    logger.debug(f"Using saved audio input device with ID: {device_id}")

device_info = audio.get_device_info_by_index(device_id)
stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                    frames_per_buffer=CHUNK, input_device_index=device_id)

try:
    server_socket.bind(("", 4444))
    server_socket.listen(5)
    logger.debug("Server is listening...")

    while True:
        try:
            conn, addr = server_socket.accept()
            logger.debug(f"Connection from: {addr}")
            logger.debug(f"Device used: {device_info['name']}")
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
