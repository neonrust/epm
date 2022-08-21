import subprocess
import sys

def run():
    subprocess.run(
        [sys.executable, '-u', '-m', 'unittest', 'discover', '-s', 'test']
    )
