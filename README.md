# Python Tracepath

This is a subset version of the `tracepath` command written in Python3. The program supports both IPv4 and IPv6.

One interesting point of this program is that it provides maximum continous failure count parameter to stop measurement when no response is received.

This program doesn't require root privilege.

Although this software is a pure Python3 code, it may not work on platforms other than Linux beacuse of lack of supported ancillary data types of the socket interface.


## Installation

Install using `pip`, or type `python setup.py install`.


## Usage

A command line tool `pytracepath` is available.

```
usage: pytracepath [-h] [-4] [-6] [-m MAX_HOPS] [-e MAX_CONTINUOUS_FAILS]
                   HOSTNAME

positional arguments:
  HOSTNAME

optional arguments:
  -h, --help            show this help message and exit
  -4                    use IPv4
  -6                    use IPv6
  -m MAX_HOPS           maximum number of hops (TTL)
  -e MAX_CONTINUOUS_FAILS
                        maximum number of repeated probe fails
```


## Using as a module

```
import pytracepath

tp = pytracepath.Tracepath('target.example.org',
                           ipv6=True,
                           max_hops=15,
                           max_continous_fails=5)
print(tp.start())
```

The `start()` method will return the histrory of responders of the probe packets. IPv6 is used and the maximum Hop Limit is 15 in the aboe example. Also, if the program failed to receive any response 5 times continuously while measuring, it will stop the rest of the measurement even though the Hop Limit is smaller than 15.


## Code

The code is available at [Github](https://github.com/keiichishima/pytracepath).
