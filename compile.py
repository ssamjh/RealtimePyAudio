import os
import subprocess
import sys

def install_dependencies():
    print("Installing required dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller", "pyaudio"])

def compile_script(script_name):
    print(f"Compiling {script_name} to executable...")
    subprocess.check_call([
        "pyinstaller",
        "--onefile",
        "--add-data", f"{script_name};.",
        "--hidden-import", "pyaudio",
        script_name
    ])

def main():
    install_dependencies()
    compile_script("realtimepyaudio.py")
    print("Compilation complete. The executable can be found in the 'dist' folder.")

if __name__ == "__main__":
    main()