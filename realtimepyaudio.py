import argparse
import pyaudio
import socket
import time
import logging
import pickle
import os
import select
import threading

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 4096
BUFFER_SIZE = 1 * CHUNK
KEEP_ALIVE_INTERVAL = 5

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_available_devices(audio, is_input):
    device_ids = []
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if (is_input and device_info["maxInputChannels"] > 0) or (
            not is_input and device_info["maxOutputChannels"] > 0
        ):
            device_ids.append(device_info["index"])
            logger.debug(f"ID: {device_info['index']}, Name: {device_info['name']}")
    return device_ids


def get_config(config_file, is_server):
    if os.path.exists(config_file):
        return pickle.load(open(config_file, "rb"))

    config = {}
    audio = pyaudio.PyAudio()

    if is_server:
        logger.debug("Available audio input devices:")
        device_ids = get_available_devices(audio, True)
        config["id"] = int(
            input("Please enter the ID of the audio input device to use: ")
        )
        config["port"] = int(
            input("Please enter the server port to use (default is 12998): ") or "12998"
        )
    else:
        logger.debug("Available audio output devices:")
        device_ids = get_available_devices(audio, False)
        config["device_id"] = int(
            input("Please enter the ID of the audio output device to use: ")
        )
        config["ip"] = input("Please enter the server IP to use: ")
        config["port"] = int(
            input("Please enter the server port to use (default is 12998): ") or "12998"
        )

    pickle.dump(config, open(config_file, "wb"))
    return config


def run_server(config):
    audio = pyaudio.PyAudio()
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def audio_stream_thread(conn, stream):
        try:
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                conn.sendall(data)
        except Exception as e:
            logger.error(f"Audio streaming error: {e}")

    try:
        server_socket.bind(("", config["port"]))
        server_socket.listen(5)
        logger.debug("Server is listening...")

        while True:
            conn, addr = server_socket.accept()
            logger.debug(f"Connection from: {addr}")
            logger.debug(f"Device used: {config['id']}")
            logger.debug("Streaming audio...")

            stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=config["id"],
            )

            # Start audio streaming in a separate thread
            threading.Thread(
                target=audio_stream_thread, args=(conn, stream), daemon=True
            ).start()

            last_keep_alive = time.time()
            conn.setblocking(0)

            while True:
                ready = select.select([conn], [], [], 0.1)
                if ready[0]:
                    try:
                        data = conn.recv(1024)
                        if not data:
                            raise ConnectionResetError("Client disconnected")
                        if data == b"KEEP_ALIVE":
                            last_keep_alive = time.time()
                    except ConnectionResetError:
                        logger.debug("Client disconnected")
                        break

                if time.time() - last_keep_alive > KEEP_ALIVE_INTERVAL * 2:
                    logger.debug("Keep-alive timeout, closing connection")
                    break

    except Exception as e:
        logger.error(f"Error occurred: {e}")
    finally:
        if "conn" in locals():
            conn.close()
        if "stream" in locals():
            stream.stop_stream()
            stream.close()
        audio.terminate()
        server_socket.close()
        logger.debug("Server stopped. Restarting...")
        time.sleep(1)
        run_server(config)


def connect_to_server(server_config):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    while True:
        try:
            client_socket.connect((server_config["ip"], server_config["port"]))
            return client_socket
        except socket.error:
            logger.debug("Connection lost, retrying...")
            time.sleep(5)


def run_client(config):
    audio = pyaudio.PyAudio()
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        output=True,
        output_device_index=config["device_id"],
        frames_per_buffer=BUFFER_SIZE,
    )

    def keep_alive_thread(sock):
        while True:
            try:
                sock.sendall(b"KEEP_ALIVE")
                time.sleep(KEEP_ALIVE_INTERVAL)
            except:
                break

    while True:
        try:
            client_socket = connect_to_server(config)
            client_socket.setblocking(1)  # Set socket to blocking mode

            # Start keep-alive in a separate thread
            threading.Thread(
                target=keep_alive_thread, args=(client_socket,), daemon=True
            ).start()

            while True:
                data = client_socket.recv(CHUNK)
                if not data:
                    raise ConnectionResetError("Server disconnected")
                stream.write(data)

        except (OSError, IOError, ConnectionResetError) as e:
            logger.error(f"Connection Error: {e}")
            client_socket.close()
            stream.stop_stream()
            stream.close()
            time.sleep(5)  # Wait before attempting to reconnect
            continue


def main():
    parser = argparse.ArgumentParser(description="Audio Streaming Application")
    parser.add_argument(
        "-s", "--server", action="store_true", help="Run in server mode"
    )
    parser.add_argument(
        "-c", "--client", action="store_true", help="Run in client mode"
    )
    args = parser.parse_args()

    if args.server:
        config = get_config("config-server.pkl", True)
        run_server(config)
    elif args.client:
        config = get_config("config-client.pkl", False)
        run_client(config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
