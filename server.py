import pyaudio
import socket

FORMAT = pyaudio.paInt16
CHANNELS = 2
RATE = 44100
CHUNK = 1024

audio = pyaudio.PyAudio()

device_id = None

# If device_id not set manually
if device_id is None:
    # List all audio input devices
    print("Available audio input devices:")
    for i in range(audio.get_device_count()):
        device_info = audio.get_device_info_by_index(i)
        if device_info["maxInputChannels"] > 0:
            print(f"ID: {device_info['index']}, Name: {device_info['name']}")

    device_id = int(
        input("Please enter the ID of the audio input device to use: "))

stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                    frames_per_buffer=CHUNK, input_device_index=device_id)

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(("", 4444))
server_socket.listen(5)

while True:
    try:
        conn, addr = server_socket.accept()
        print("Connection from", addr)
        print("Streaming audio...")

        while True:
            data = stream.read(CHUNK)
            conn.send(data)
    except Exception as e:
        print(f"Error occurred: {e}")

stream.stop_stream()
stream.close()
audio.terminate()
server_socket.close()
