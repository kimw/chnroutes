#!/usr/bin/env python
# vim: set ts=8 et sw=4 sts=4

"""
scripts help chinese netizen, who uses vpn to combat censorship, by modifying
the route table so as routing only the censored ip to the vpn.
"""

import argparse
import math
import re
import socket
import struct
import sys
if sys.version_info.major == 2:
    import urllib2
elif sys.version_info.major == 3:
    import urllib.request
else:
    print("chnroute can run in python 2 and python 3 only.")
    exit(1)
import os


def generate_ovpn(metric):
    """
    TODO (kim): add function docstring
    """

    results = fetch_ip_data()
    rfile = open('routes.txt', 'w')
    for ip, mask, _ in results:  # pylint: disable=invalid-name
        route_item = 'route %s %s net_gateway %d\n' % (ip, mask, metric)
        rfile.write(route_item)
    rfile.close()
    print('Usage: Append the content of the newly created routes.txt to your'
          ' openvpn config file, and also add "max-routes %d", which takes a'
          ' line, to the head of the file.' % (len(results) + 20))


def generate_linux(metric):  # pylint: disable=unused-argument
    """
    TODO (kim): add function docstring
    """

    results = fetch_ip_data()
    upscript_header = (
        '#!/bin/bash\n'
        'export PATH="/bin:/sbin:/usr/sbin:/usr/bin"\n'
        '\n'
        'OLDGW=`ip route show'
        ' | grep \'^default\''
        ' | sed -e \'s/default via \\([^ ]*\\).*/\\1/\'`\n'
        '\n'
        'if [ $OLDGW == \'\' ]; then\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'if [ ! -e /tmp/vpn_oldgw ]; then\n'
        '    echo $OLDGW > /tmp/vpn_oldgw\n'
        'fi\n'
        '\n')

    downscript_header = (
        '#!/bin/bash\n'
        'export PATH="/bin:/sbin:/usr/sbin:/usr/bin"\n'
        '\n'
        'OLDGW=`cat /tmp/vpn_oldgw`\n'
        '\n')

    upfile = open('ip-pre-up', 'w')
    downfile = open('ip-down', 'w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, mask, _ in results:  # pylint: disable=invalid-name
        upfile.write('route add -net %s netmask %s gw $OLDGW\n' % (ip, mask))
        downfile.write('route del -net %s netmask %s\n' % (ip, mask))

    downfile.write('rm /tmp/vpn_oldgw\n')

    print('For pptp only, please copy the file ip-pre-up to the folder'
          ' "/etc/ppp", and copy the file ip-down to the folder'
          ' "/etc/ppp/ip-down.d".')


def generate_mac(metric):  # pylint: disable=unused-argument
    """
    TODO (kim): add function docstring
    """

    results = fetch_ip_data()

    upscript_header = (
        '#!/bin/sh\n'
        'export PATH="/bin:/sbin:/usr/sbin:/usr/bin"\n'
        '\n'
        'OLDGW=`netstat -nr'
        ' | grep \'^default\''
        ' | grep -v \'ppp\''
        ' | sed \'s/default *\\([0-9\.]*\\) .*/\\1/\''
        ' | awk \'{if($1){print $1}}\'`\n'
        '\n'
        'if [ ! -e /tmp/pptp_oldgw ]; then\n'
        '    echo "${OLDGW}" > /tmp/pptp_oldgw\n'
        'fi\n'
        '\n'
        'dscacheutil -flushcache\n'
        '\n'
        'route add 10.0.0.0/8 "${OLDGW}"\n'
        'route add 172.16.0.0/12 "${OLDGW}"\n'
        'route add 192.168.0.0/16 "${OLDGW}"\n')

    downscript_header = (
        '#!/bin/sh\n'
        'export PATH="/bin:/sbin:/usr/sbin:/usr/bin"\n'
        '\n'
        'if [ ! -e /tmp/pptp_oldgw ]; then\n'
        '    exit 0\n'
        'fi\n'
        '\n'
        'ODLGW=`cat /tmp/pptp_oldgw`\n'
        '\n'
        'route delete 10.0.0.0/8 "${OLDGW}"\n'
        'route delete 172.16.0.0/12 "${OLDGW}"\n'
        'route delete 192.168.0.0/16 "${OLDGW}"\n')

    upfile = open('ip-up', 'w')
    downfile = open('ip-down', 'w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, _, mask in results:  # pylint: disable=invalid-name
        upfile.write('route add %s/%s "${OLDGW}"\n' % (ip, mask))
        downfile.write('route delete %s/%s ${OLDGW}\n' % (ip, mask))

    downfile.write('\n\nrm /tmp/pptp_oldgw\n')
    upfile.close()
    downfile.close()

    print('For pptp on mac only, please copy ip-up and ip-down to the /etc/ppp'
          ' folder, don\'t forget to make them executable with the chmod'
          ' command.')


def generate_win(metric):
    """
    TODO (kim): add function docstring
    """

    results = fetch_ip_data()

    upscript_header = (
        '@echo off\n'
        'for /F "tokens=3" %%* in (\'route print ^| findstr "\\<0.0.0.0\\>"\')'
        ' do set "gw=%%*"\n'
        '\n')

    upfile = open('vpnup.bat', 'w')
    downfile = open('vpndown.bat', 'w')

    upfile.write(upscript_header)
    upfile.write('ipconfig /flushdns\n\n')

    downfile.write('@echo off\n')

    for ip, mask, _ in results:  # pylint: disable=invalid-name
        upfile.write('route add %s mask %s %s metric %d\n'
                     % (ip, mask, "%gw%", metric))
        downfile.write('route delete %s\n' % (ip))

    upfile.close()
    downfile.close()

    print('For pptp on windows only, run vpnup.bat before dialing to vpn,'
          ' and run vpndown.bat after disconnected from the vpn.')


def generate_android(metric):  # pylint: disable=unused-argument
    """
    TODO (kim): add function docstring
    """

    results = fetch_ip_data2()

    upscript_header = (
        '#!/bin/sh\n'
        'alias nestat=\'/system/xbin/busybox netstat\'\n'
        'alias grep=\'/system/xbin/busybox grep\'\n'
        'alias awk=\'/system/xbin/busybox awk\'\n'
        'alias route=\'/system/xbin/busybox route\'\n'
        '\n'
        'OLDGW=`netstat -rn | grep ^0\.0\.0\.0 | awk \'{print $2}\'`\n'
        '\n'
        'route add -net 10.0.0.0 netmask 255.0.0.0 gw $OLDGW\n'
        'route add -net 172.16.0.0 netmask 255.240.0.0 gw $OLDGW\n'
        'route add -net 192.168.0.0 netmask 255.255.0.0 gw $OLDGW\n')

    downscript_header = (
        '#!/bin/sh\n'
        'alias route=\'/system/xbin/busybox route\'\n'
        '\n'
        'route del -net 10.0.0.0 netmask 255.0.0.0\n'
        'route del -net 172.16.0.0 netmask 255.240.0.0\n'
        'route del -net 192.168.0.0 netmask 255.255.0.0\n')

    upfile = open('vpnup.sh', 'w')
    downfile = open('vpndown.sh', 'w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, mask, _ in results:  # pylint: disable=invalid-name
        upfile.write('route add -net %s netmask %s gw $OLDGW\n' % (ip, mask))
        downfile.write('route del -net %s netmask %s\n' % (ip, mask))

    upfile.close()
    downfile.close()

    print('Old school way to call up/down script from openvpn client.'
          ' use the regular openvpn 2.1 method to add routes if it\'s'
          ' possible.')


def fetch_ip_data():
    """
    TODO (kim): add function docstring
    """

    # fetch data from apnic
    print('Fetching data from apnic.net, it might take a few minutes,'
          ' please wait...')
    if os.path.exists("delegated-apnic-latest"):
        print("File delegated-apnic-latest is found in current directory."
              " I, robot, is going to use it.")
        with open("delegated-apnic-latest") as f:
            data = f.read()
    else:
        url = r'http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest'
        if sys.version_info.major == 2:
            data = urllib2.urlopen(url).read()
        elif sys.version_info.major == 3:
            data = urllib.request.urlopen(url).read()

    cnregex = re.compile(
        r'apnic\|cn\|ipv4\|[0-9\.]+\|[0-9]+\|[0-9]+\|a.*',
        re.IGNORECASE)
    cndata = cnregex.findall(data)

    results = []

    for item in cndata:
        unit_items = item.split('|')
        starting_ip = unit_items[3]
        num_ip = int(unit_items[4])

        imask = 0xffffffff ^ (num_ip - 1)
        # convert to string
        imask = hex(imask)[2:]
        mask = [0] * 4
        mask[0] = imask[0:2]
        mask[1] = imask[2:4]
        mask[2] = imask[4:6]
        mask[3] = imask[6:8]

        # convert str to int
        mask = [int(i, 16) for i in mask]
        mask = '%d.%d.%d.%d' % tuple(mask)

        # mask in *nix format
        mask2 = 32 - int(math.log(num_ip, 2))

        results.append((starting_ip, mask, mask2))

    return results


def fetch_ip_data2():
    """
    TODO (kim): add function docstring

    created by kim.max@gmail.com
    """

    # fetch data from apnic
    print('Fetching data from apnic.net, it might take a few minutes,'
          ' please wait...')
    if os.path.exists("delegated-apnic-latest"):
        print("File delegated-apnic-latest is found in current directory."
              " I, robot, is going to use it.")
        with open("delegated-apnic-latest") as f:
            data = f.read()
    else:
        url = r'http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest'
        if sys.version_info.major == 2:
            data = urllib2.urlopen(url).read()
        elif sys.version_info.major == 3:
            data = urllib.request.urlopen(url).read()


    cnregex = re.compile(
        r'apnic\|cn\|ipv4\|[0-9\.]+\|[0-9]+\|[0-9]+\|a.*',
        re.IGNORECASE)
    cndata = cnregex.findall(data)

    results = []

    routed = 0
    amount = 0
    start = end = 0

    for item in cndata:
        # apnic|CN|ipv4|1.0.1.0|256|20110414|allocated
        if 'CN|ipv4' not in item:
            continue
        lists = item.split('|')
        ip = lists[3]
        count = int(lists[4])
        newstart = getint(ip)
        newend = newstart + count
        if end == newstart:
            end = newend
        else:
            if end - start + 1 >= (1 << (32 - MAXBITS)):
                r = check_range(start, end - 1)
                if (r[1] != 0):
                    results += r[0]
                    routed += r[1]
            amount += end - start
            start = newstart
            end = newend
    print >> sys.stderr, (
        '%d%%' % (100 * routed / amount),
        'routed=%d, amount=%d' % (routed, amount))
    return results


getip = lambda x: socket.inet_ntoa(struct.pack('!I', x))
getint = lambda x: struct.unpack('!I', socket.inet_aton(x))[0]
MAXBITS = 16


def check_range(start, end):
    """
    TODO (kim): add function docstring
    """

    count = 0
    base = start
    results = []

    while base <= end:
        step = 0
        while (base | (1 << step)) != base:
            if (base | (0xffffffff >> (31 - step))) > end:
                break
            step += 1
        if step >= (32 - MAXBITS):
            count += (1 << step)
            results.append((getip(base), get_ipv4_mask_str(32 - step), 0))
        base += (1 << step)

    return results, count


def get_ipv4_mask_str(num):
    """
    TODO (kim): add function docstring

    writen by kim.max@gmail.com
    """
    if num == 0:
        return '0.0.0.0'
    else:
        num = 2 ** (32 - num)
    imask = 0xffffffff ^ (num - 1)
    # convert to str
    imask = hex(imask)[2:]
    mask = [0] * 4
    mask[0] = imask[0:2]
    mask[1] = imask[2:4]
    mask[2] = imask[4:6]
    mask[3] = imask[6:8]
    # convert str to int
    mask = [int(i, 16) for i in mask]
    mask = '%d.%d.%d.%d' % tuple(mask)
    return mask


def main():
    parser = argparse.ArgumentParser(
        description='Generate routing rules for vpn.')
    parser.add_argument(
        '-p', '--platform',
        dest='platform',
        default='openvpn',
        nargs='?',
        help=('Target platforms, it can be:\n openvpn, mac, linux, win,'
              ' or android. openvpn by default.'))
    parser.add_argument(
        '-m', '--metric',
        dest='metric',
        default=5,
        nargs='?',
        type=int,
        help='Metric setting for the route rules.')

    args = parser.parse_args()

    if args.platform.lower() == 'openvpn':
        generate_ovpn(args.metric)
    elif args.platform.lower() == 'linux':
        generate_linux(args.metric)
    elif args.platform.lower() == 'mac':
        generate_mac(args.metric)
    elif args.platform.lower() == 'win':
        generate_win(args.metric)
    elif args.platform.lower() == 'android':
        generate_android(args.metric)
    else:
        print >> sys.stderr, 'Platform %s is not supported.' % args.platform
        exit(1)


if __name__ == '__main__':
    main()
