#!/usr/bin/env python

import argparse
import errno
import json
import logging
_logger = logging.getLogger(__name__)
import random
import select
import socket
import struct
import time

# these constants should be defined in the socket module
SOL_IPV6 = 41
IP_RECVERR = 11
IPV6_RECVERR = 25

# the starting number of the destination port of probe packets
PORT_RANGE = (35000, 40000)

MAX_HOPS = 30
MAX_SENDTO_TRIES = 3
MAX_CONTINUOUS_FAILS = MAX_HOPS

BUFFER_SIZE = 128
ANCDATA_SIZE = 512

class Error(Exception):
    def __init__(self, _message):
        self._message = _message

    def __str__(self):
        return self._message

class Tracepath(object):
    def __init__(self,
                 _dest,
                 _ipv4 = False,
                 _ipv6 = False,
                 _max_hops=MAX_HOPS,
                 _max_continuous_fails=MAX_CONTINUOUS_FAILS):
        assert(_dest != None)
        assert(_dest != '')

        try:
            if _ipv4:
                _family = socket.AF_INET
            elif _ipv6:
                _family = socket.AF_INET6
            else:
                _family = 0
            self._dest = socket.getaddrinfo(
                _dest, 0,
                family=_family,
                proto=socket.IPPROTO_UDP)[0]
        except socket.error as _e:
            raise _e
        self._socket = None
        self._port = random.choice(range(*PORT_RANGE))
        self._max_hops = _max_hops
        self._max_continuous_fails = _max_continuous_fails
        self._ttl = 1
        self._latency = None
        self._peer_info = None
        self._history = []


    @property
    def latency(self):
        return self._latency

    @property
    def history(self):
        return self._history

    def _is_final_dest(self):
        if self._dest is None or self._peer_info is None:
            return False
        if self._dest[0] == socket.AF_INET:
            return self._dest[4][0] == self._peer_info[0]
        if self._dest[0] == socket.AF_INET6:
            return (self._dest[4][0] == self._peer_info[0]
                    and self._dest[4][2] == self._peer_info[2]
                    and self._dest[4][3] == self._peer_info[3])

    def _create_socket(self):
        _logger.debug(self._dest)
        _socket = socket.socket(
            self._dest[0],
            self._dest[1],
            self._dest[2])

        if self._dest[0] == socket.AF_INET:
            _socket.setsockopt(
                socket.SOL_IP,
                IP_RECVERR,
                1)
        elif self._dest[0] == socket.AF_INET6:
            _socket.setsockopt(
                SOL_IPV6,
                IPV6_RECVERR,
                1)
        else:
            raise Error(f'protocol family ({self._dest[0]}) not supported')

        #_socket.settimeout(1)

        self._socket = _socket

    # return value: Success or not:bool
    #
    def _probe(self):
        _logger.debug(f'probing {self._dest[4]} with TTL {self._ttl}')
        if self._dest[0] == socket.AF_INET:
            self._socket.setsockopt(
                socket.SOL_IP,
                socket.IP_TTL,
                self._ttl)
        elif self._dest[0] == socket.AF_INET6:
            self._socket.setsockopt(
                SOL_IPV6,
                socket.IPV6_UNICAST_HOPS,
                self._ttl)

        self._start = time.time_ns()
        self._end = None
        self._peer_info = None
        for _i in range(MAX_SENDTO_TRIES):
            try:
                if self._dest[0] == socket.AF_INET:
                    self._socket.sendto(
                        b'',
                        (self._dest[4][0],
                         self._dest[4][1] + self._port)
                    )
                    # sendto succeeded
                    self._port += 1
                    break
                elif self._dest[0] == socket.AF_INET6:
                    self._socket.sendto(
                        b'',
                        (self._dest[4][0],
                         self._dest[4][1] + self._port,
                         self._dest[4][2],
                         self._dest[4][3])
                    )
                    # sendto succeeded
                    self._port += 1
                    break
            except OSError as _e:
                _logger.debug(f'sendto failed: {_e}')
                return self._recverr()
        if _i == (MAX_SENDTO_TRIES - 1):
            _logger.debug(f'sendto failed {MAX_SENDTO_TRIES} times, aborting')
            return False

        _readers = select.select([self._socket], [], [], 1)
        if len(_readers) == 0:
            # timeout
            _logger.debug('select timeout')
            return False

        try:
            _msg = self._socket.recv(BUFFER_SIZE, socket.MSG_DONTWAIT)
            if len(_msg) > 0:
                _logger.debug(f'data received {len(_msg)} bytes')
                self._end = time.time_ns()
                self._peer_info = _dest[4]
                return True
        except OSError as _e:
            _logger.debug(f'recv failed: {_e}')
            return self._recverr()

        return self._recverr()

    def _recverr(self):
        _logger.debug(f'check socket error queue')

        while True:
            try:
                (_msg, _cmsgs, _flags, _addr) = (None, None, None, None)
                _msg, _cmsgs, _flags, _addr = self._socket.recvmsg(
                    BUFFER_SIZE,
                    ANCDATA_SIZE,
                    socket.MSG_ERRQUEUE)
                # recvmsg succeeded to get ancillary data
            except OSError as _e:
                _logger.debug('recvmsg failed')
                if _e.errno == socket.EAGAIN:
                    self._end = None
                    return False

            self._end = time.time_ns()

            (_ee_errno, _ee_origin, _ee_type, _ee_code, _ee_pad, _ee_info, _ee_data) = (None, None, None, None, None, None,None)
            for _level, _type, _data in _cmsgs:
                if _level == socket.SOL_IP:
                    if _type == IP_RECVERR:
                        (_ee_errno, _ee_origin, _ee_type, _ee_code,
                         _ee_pad, _ee_info, _ee_data) = struct.unpack(
                             '=LBBBBLL', _data[:16])
                        _logger.debug(f'errno = {_ee_errno}, origin = {_ee_origin}')
                        self._peer_info = [
                            socket.inet_ntop(socket.AF_INET, _data[20:20+4]),
                            struct.unpack('!H', _data[18:20])[0]
                        ]
                        _logger.debug(f'error packet received from {self._peer_info}')
                if _level == SOL_IPV6:
                    if _type == IPV6_RECVERR:
                        (_ee_errno, _ee_origin, _ee_type, _ee_code,
                         _ee_pad, _ee_info, _ee_data) = struct.unpack(
                             '=LBBBBLL', _data[:16])
                        _logger.debug(f'errno = {_ee_errno}, origin = {_ee_origin}')
                        self._peer_info = [
                            socket.inet_ntop(socket.AF_INET6, _data[24:24+16]),
                            struct.unpack('!H', _data[18:20])[0],
                            struct.unpack('!L', _data[20:24])[0],
                            struct.unpack('!L', _data[40:44])[0]
                        ]
                        _logger.debug(f'error packet received from {self._peer_info}')

            if _ee_errno == None:
                return False
            if _ee_errno == errno.ETIMEDOUT:
                continue
            if _ee_errno == errno.EMSGSIZE:
                continue
            _logger.debug(f'ee_errno = {_ee_errno}, ee_origin = {_ee_origin}, ee_type = {_ee_type}, ee_code = {_ee_code}')
            return True

        # Not reached

    def start(self, _display=None):
        self._create_socket()
        _fail_count = 0
        for _ttl in range(1, self._max_hops + 1):
            self._ttl = _ttl
            _status = self._probe()
            if _status == True:
                _fail_count = 0
                self._latency = self._end - self._start
            else:
                _fail_count += 1

            self._history.append(
                {
                    'ttl': _ttl,
                    'peer': self._peer_info,
                    'latency': self._latency if _status else None
                }
            )
            if _display:
                _display(self._history[-1])
            if _fail_count >= MAX_CONTINUOUS_FAILS:
                _logger.debug(f'continous failure {_fail_count} times')
                break
            if self._is_final_dest() == True:
                _logger.debug(f'reached')
                break

def _display_default(_hist):
    _ttl = _hist['ttl']
    _peer = _hist['peer'][0] if _hist['peer'] else '*'
    _latency = _hist['latency']/1000000 if _hist['latency'] else '*'
    print(f"{_ttl:3d}: {_peer:30s}: {_latency} ms")
    

if __name__ == '__main__':
    import sys
    #_handler = logging.StreamHandler()
    #_logger.setLevel(logging.DEBUG)
    #_logger.addHandler(_handler)

    _parser = argparse.ArgumentParser()
    _parser.add_argument('hostname', metavar='HOSTNAME',
                         nargs=1, type=str)
    _parser.add_argument('-4', dest='ipv4', action='store_true',
                         help='use IPv4')
    _parser.add_argument('-6', dest='ipv6', action='store_true',
                         help='use IPv6')
    _parser.add_argument('-m', dest='max_hops', type=int,
                         default=MAX_HOPS,
                         help='maximum number of hops (TTL)')
    _args = _parser.parse_args()
    if (_args.ipv4 and _args.ipv6):
        _logger.error('-4 and -6 are exclusive.')
        sys.exit(-1)
    _t = Tracepath(_args.hostname[0],
                   _ipv4=_args.ipv4,
                   _ipv6=_args.ipv6,
                   _max_hops=_args.max_hops)
    _t.start(_display=_display_default)

