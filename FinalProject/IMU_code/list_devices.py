#run this script and the number before "array inputs: " should be used for the DEVICE_INDEX in  voice_commands.py
#mine was "9 array inputs: 2"

import pyaudio

p = pyaudio.PyAudio()

for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(i, info["name"], "inputs:", info["maxInputChannels"])

