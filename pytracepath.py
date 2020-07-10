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

# struct sock_extended_err origin values
SO_EE_ORIGIN_LOCAL = 1
SO_EE_ORIGIN_ICMP = 2
SO_EE_ORIGIN_ICMP6 = 3

# ICMP time exceeded type and code
ICMP_TIME_EXCEEDED = 11
ICMP_EXC_TTL = 0

# ICMPv6 time exceeded type and code
ICMPV6_TIME_EXCEEDED = 3
ICMPV6_EXC_HOPLIMIT = 0

# these constants should be defined in the socket module
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
                 dest,
                 ipv4 = False,
                 ipv6 = False,
                 max_hops=MAX_HOPS,
                 max_continuous_fails=MAX_CONTINUOUS_FAILS):
        assert(dest != None)
        assert(dest != '')

        try:
            if ipv4:
                _family = socket.AF_INET
            elif ipv6:
                _family = socket.AF_INET6
            else:
                _family = 0
            self._dest = socket.getaddrinfo(
                dest, 0,
                family=_family,
                proto=socket.IPPROTO_UDP)[0]
        except socket.error as _e:
            raise _e
        self._socket = None
        self._max_hops = max_hops
        self._max_continuous_fails = max_continuous_fails
        self._history = []
        # transitional parameters per probe
        self._start = None
        self._end = None
        self._port = random.choice(range(*PORT_RANGE))
        self._ttl = 1
        self._latency = None
        self._peer_info = None
        self._errno = 0

    @property
    def latency(self):
        return self._latency

    @property
    def history(self):
        return self._history

    @property
    def farthest_point(self):
        if len(self._history) == 0:
            return None
        for _h in reversed(self._history):
            if _h['peer'] is not None:
                return _h
        return None

    def _is_final_dest(self):
        if self._dest is None or self._peer_info is None:
            return False
        if self._errno == errno.ECONNREFUSED:
            return True
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
                socket.IPPROTO_IP,
                IP_RECVERR,
                1)
        elif self._dest[0] == socket.AF_INET6:
            _socket.setsockopt(
                socket.IPPROTO_IPV6,
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
                socket.IPPROTO_IP,
                socket.IP_TTL,
                self._ttl)
        elif self._dest[0] == socket.AF_INET6:
            self._socket.setsockopt(
                socket.IPPROTO_IPV6,
                socket.IPV6_UNICAST_HOPS,
                self._ttl)

        self._start = time.time_ns()
        self._end = None
        self._peer_info = None
        self._errno = 0
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
                _logger.debug(f'recvmsg failed: {_e}')
                if _e.errno == socket.EAGAIN:
                    self._end = None
                    self._errno = socket.EAGAIN
                    return False

            self._end = time.time_ns()

            (_ee_errno, _ee_origin, _ee_type, _ee_code, _ee_pad, _ee_info, _ee_data) = (None, None, None, None, None, None,None)
            for _level, _type, _data in _cmsgs:
                if _level == socket.IPPROTO_IP:
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
                if _level == socket.IPPROTO_IPV6:
                    if _type == IPV6_RECVERR:
                        (_ee_errno, _ee_origin, _ee_type, _ee_code,
                         _ee_pad, _ee_info, _ee_data) = struct.unpack(
                             '=LBBBBLL', _data[:16])
                        _logger.debug(f'errno = {_ee_errno}, origin = {_ee_origin}')
                        self._peer_info = [
                            socket.inet_ntop(socket.AF_INET6,
                                             _data[24:24+16]),
                            struct.unpack('!H', _data[18:20])[0],
                            struct.unpack('!L', _data[20:24])[0],
                            struct.unpack('!L', _data[40:44])[0]
                        ]
                        _logger.debug(f'error packet received from {self._peer_info}')

            if _ee_errno == None:
                # no extended err info
                return False
            self._errno = _ee_errno
            _logger.debug(f'ee_errno = {_ee_errno}, ee_origin = {_ee_origin}, ee_type = {_ee_type}, ee_code = {_ee_code}')
            if _ee_errno == errno.ETIMEDOUT:
                continue
            if _ee_errno == errno.EMSGSIZE:
                # XXX
                continue
            if _ee_errno == errno.EHOSTUNREACH:
                if (_ee_origin == SO_EE_ORIGIN_ICMP
                    and _ee_type == ICMP_TIME_EXCEEDED
                    and _ee_code == ICMP_EXC_TTL):
                    return True
                if (_ee_origin == SO_EE_ORIGIN_ICMP6
                    and _ee_type == ICMPV6_TIME_EXCEEDED
                    and _ee_code == ICMPV6_EXC_HOPLIMIT):
                    return True
                return False
            if _ee_errno == errno.ENETUNREACH:
                return False
            if _ee_errno == errno.EACCES:
                return False

            return True

        # Not reached

    def start(self, display_callback=None):
        self._create_socket()
        self._history = []
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
                    'latency': self._latency if _status else None,
                    'errno': self._errno
                }
            )
            if display_callback:
                display_callback(self._history[-1])
            if _fail_count >= self._max_continuous_fails:
                _logger.debug(f'continous failure {_fail_count} times')
                break
            if self._is_final_dest() == True:
                _logger.debug(f'reached')
                break
            if self._errno == errno.EACCES:
                break
        return self._history

def _display_callback_default(hist):
    _ttl = hist['ttl']
    _peer = hist['peer'][0] if hist['peer'] else '*'
    _latency = hist['latency']/1000000 if hist['latency'] else '*'
    _errno = hist['errno']
    print(f"{_ttl:3d}: {_peer:30s}: {str(_latency):>10s} ms: [{_errno}]")
    

def main():
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
    _parser.add_argument('-M', dest='max_continuous_fails', type=int,
                         default=MAX_CONTINUOUS_FAILS,
                         help='maximum number of repeated probe fails')
    _args = _parser.parse_args()
    if (_args.ipv4 and _args.ipv6):
        _logger.error('-4 and -6 are exclusive.')
        sys.exit(-1)
    _t = Tracepath(_args.hostname[0],
                   ipv4=_args.ipv4,
                   ipv6=_args.ipv6,
                   max_hops=_args.max_hops,
                   max_continuous_fails=_args.max_continuous_fails)
    return _t.start(display_callback=_display_callback_default)


if __name__ == '__main__':
    main()
