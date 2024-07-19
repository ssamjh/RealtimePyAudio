import argparse
import pyaudio
import socket
import time
import logging
import pickle
import os
import select
import threading
import struct
from collections import deque

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 4096
BUFFER_SIZE = 1 * CHUNK
KEEP_ALIVE_INTERVAL = 5
MAX_RETRIES = 3
PACKET_HEADER_SIZE = 8  # 4 bytes for sequence number, 4 bytes for payload size
BUFFER_DURATION = 5  # Buffer duration in seconds

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
        config = pickle.load(open(config_file, "rb"))
    else:
        config = {}

    audio = pyaudio.PyAudio()

    if is_server:
        if "id" not in config:
            logger.debug("Available audio input devices:")
            device_ids = get_available_devices(audio, True)
            config["id"] = int(
                input("Please enter the ID of the audio input device to use: ")
            )
        if "port" not in config:
            config["port"] = int(
                input("Please enter the server port to use (default is 12998): ")
                or "12998"
            )
        if "retransmit" not in config:
            config["retransmit"] = (
                input("Enable retransmission? (y/n): ").lower() == "y"
            )
    else:
        if "device_id" not in config:
            logger.debug("Available audio output devices:")
            device_ids = get_available_devices(audio, False)
            config["device_id"] = int(
                input("Please enter the ID of the audio output device to use: ")
            )
        if "ip" not in config:
            config["ip"] = input("Please enter the server IP to use: ")
        if "port" not in config:
            config["port"] = int(
                input("Please enter the server port to use (default is 12998): ")
                or "12998"
            )

    if "debugging" not in config:
        config["debugging"] = input("Enable debugging? (y/n): ").lower() == "y"

    pickle.dump(config, open(config_file, "wb"))
    return config


def pack_audio_data(seq_num, audio_data):
    header = struct.pack(">II", seq_num, len(audio_data))
    return header + audio_data


def unpack_audio_data(packet):
    header = packet[:PACKET_HEADER_SIZE]
    seq_num, payload_size = struct.unpack(">II", header)
    return seq_num, packet[PACKET_HEADER_SIZE:]


def run_server(config):
    audio = pyaudio.PyAudio()
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def audio_stream_thread(conn, stream, stop_event):
        seq_num = 0
        conn.setblocking(0)  # Set to non-blocking mode
        try:
            while not stop_event.is_set():
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    packet = pack_audio_data(seq_num, data)
                    conn.sendall(packet)
                    seq_num = (seq_num + 1) % (2**32)  # Wrap around at 2^32

                    if config["debugging"]:
                        if len(data) < CHUNK:
                            logger.debug(
                                f"Audio input dropout detected. Expected {CHUNK} bytes, got {len(data)} bytes."
                            )
                except IOError as e:
                    if config["debugging"] and not stop_event.is_set():
                        if e.errno != 10035:  # Not a "would block" error
                            logger.debug(f"Audio input error: {e}")
                except socket.error as e:
                    if e.errno != 10035:  # Not a "would block" error
                        logger.error(f"Socket error: {e}")
                        break
                except Exception as e:
                    if not stop_event.is_set():
                        logger.error(f"Audio streaming error: {e}")
                    break
        except Exception as e:
            if not stop_event.is_set():
                logger.error(f"Audio streaming thread error: {e}")

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

            stop_event = threading.Event()
            audio_thread = threading.Thread(
                target=audio_stream_thread, args=(conn, stream, stop_event), daemon=True
            )
            audio_thread.start()

            last_keep_alive = time.time()
            conn.setblocking(0)

            try:
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
            finally:
                stop_event.set()  # Signal the audio thread to stop
                conn.close()
                stream.stop_stream()
                stream.close()
                audio_thread.join(timeout=1)  # Wait for the audio thread to finish
                logger.debug("Connection closed and audio stream stopped")

    except Exception as e:
        logger.error(f"Server error occurred: {e}")
    finally:
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

    def audio_playback_thread(buffer, stop_event, playback_ready):
        playback_ready.wait()  # Wait until the buffer is filled
        logger.debug("Starting audio playback")
        while not stop_event.is_set():
            if len(buffer) > 0:
                audio_data = buffer.popleft()
                stream.write(audio_data)
            else:
                time.sleep(0.01)  # Short sleep to prevent busy-waiting

    while True:
        try:
            client_socket = connect_to_server(config)
            client_socket.setblocking(1)  # Set socket to blocking mode

            threading.Thread(
                target=keep_alive_thread, args=(client_socket,), daemon=True
            ).start()

            expected_seq_num = 0
            buffer = deque()
            packet_buffer = {}
            buffer_samples = int(BUFFER_DURATION * RATE / CHUNK)
            stop_event = threading.Event()
            playback_ready = threading.Event()

            playback_thread = threading.Thread(
                target=audio_playback_thread,
                args=(buffer, stop_event, playback_ready),
                daemon=True,
            )
            playback_thread.start()

            logger.debug(f"Buffering audio for {BUFFER_DURATION} seconds...")

            while True:
                header = client_socket.recv(PACKET_HEADER_SIZE)
                if not header:
                    raise ConnectionResetError("Server disconnected")

                seq_num, payload_size = struct.unpack(">II", header)

                # Receive the audio data
                audio_data = b""
                while len(audio_data) < payload_size:
                    chunk = client_socket.recv(payload_size - len(audio_data))
                    if not chunk:
                        raise ConnectionResetError("Server disconnected")
                    audio_data += chunk

                # Store the packet in the buffer
                packet_buffer[seq_num] = audio_data

                # Process packets in order
                while expected_seq_num in packet_buffer:
                    buffer.append(packet_buffer.pop(expected_seq_num))
                    expected_seq_num = (expected_seq_num + 1) % (2**32)

                    # Check if buffer is filled
                    if not playback_ready.is_set() and len(buffer) >= buffer_samples:
                        playback_ready.set()
                        logger.debug("Buffer filled, starting playback")

                    # Trim buffer if it exceeds the desired duration
                    while len(buffer) > buffer_samples:
                        buffer.popleft()

                # Clean up old packets
                for seq in list(packet_buffer.keys()):
                    if (seq - expected_seq_num) % (2**32) > 1000:  # Arbitrary threshold
                        del packet_buffer[seq]

                if config["debugging"]:
                    if len(audio_data) < CHUNK:
                        logger.debug(
                            f"Network dropout detected. Expected {CHUNK} bytes, got {len(audio_data)} bytes."
                        )

        except (OSError, IOError, ConnectionResetError) as e:
            logger.error(f"Connection Error: {e}")
            client_socket.close()
            stop_event.set()
            playback_thread.join(timeout=1)
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
