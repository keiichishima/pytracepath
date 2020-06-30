# Python Tracepath

This is a clone of tracepath function written in Python3. The program supports both IPv4 and IPv6.


## Installation

Install usinb `pip`, or type `python setup.py install`.


## Usage

A command line tool `pytracepath` is available.

```
$ pytracepath -h
usage: pytracepath [-h] [-4] [-6] [-m MAX_HOPS] HOSTNAME

positional arguments:
  HOSTNAME

optional arguments:
  -h, --help   show this help message and exit
  -4           use IPv4
  -6           use IPv6
  -m MAX_HOPS  maximum number of hops (TTL)
```


## Using as a module

```
import tracepath

tp = tracepath.Tracepath('target.example.org')
tp.start()
```

The `start()` method will return the histrory of responders of the probe packets.


## Code

The code is available at [Github](https://github.com/keiichishima/pytracepath).
