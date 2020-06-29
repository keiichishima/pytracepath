# Python Tracepath

This is a clone of tracepath function written in Python3. The program supports both IPv4 and IPv6.


## Usage

To show available options, call `tracepath.py` with option `-h`.

```
$ python tracepath.py -h
```

## Usage as a Module

'''
import tracepath

tp = tracepath.Tracepath('target.example.org')
tp.start()
```

The `start()` method will return the histrory of responders of the probe packets.
