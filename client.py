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

device_id_file = "client_device_id.pkl"
device_id = None if not os.path.exists(
    device_id_file) else pickle.load(open(device_id_file, "rb"))


def connect_to_server():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            client_socket.connect(("10.60.122.12", 4444))
            return client_socket
        except socket.error:
            logger.debug("Connection lost, retrying...")
            time.sleep(0.5)


def open_stream(audio):
    return audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, output_device_index=device_id,
                      frames_per_buffer=BUFFER_SIZE)


audio = pyaudio.PyAudio()

while True:
    try:
        if device_id is None:
            # List all audio output devices
            logger.debug("Available audio output devices:")
            for i in range(audio.get_device_count()):
                device_info = audio.get_device_info_by_index(i)
                if device_info["maxOutputChannels"] > 0:
                    logger.debug(
                        f"ID: {device_info['index']}, Name: {device_info['name']}")
            device_id = int(
                input("Please enter the ID of the audio output device to use: "))
            pickle.dump(device_id, open(device_id_file, "wb"))
        else:
            logger.debug(
                f"Using saved audio output device with ID: {device_id}")

        stream = open_stream(audio)

        client_socket = connect_to_server()

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
