#!/usr/bin/env python

import configparser
import logging

# The config files we're working with
INTERFACES_PATH = '/etc/network/interfaces'
NETWORK_PATH = '/boot/network.ini'
RESOLV_PATH = '/etc/resolv.conf'
NTP_PATH = '/etc/ntp.conf'

INTERFACES_TEMPLATE = """# Generated by Screenly Network Manager
auto lo
  iface lo inet loopback
"""


logging.basicConfig(level=logging.INFO,
                    format='%(message)s')


def if_config(
        static=False,
        ip=None,
        netmask=None,
        gateway=None,
        interface=None,
        ssid=None,
        passphrase=None,
        hidden_ssid=False,
):
    if not interface:
        raise ValueError

    if ip and netmask and gateway:
        static = True

    if static:
        interface_stanza = """
auto {}
  iface {} inet static
  address {}
  netmask {}
  gateway {}""".format(interface, interface, ip, netmask, gateway)
    else:
        interface_stanza = """
auto {}
  iface {} inet dhcp""".format(interface, interface)

    # If WiFi configuration
    if 'wlan' in interface:
        interface_stanza += '\n  wireless-power off'

        if ssid:
            interface_stanza += '\n  wpa-ssid "{}"'.format(ssid)
        if passphrase:
            interface_stanza += '\n  wpa-psk "{}"'.format(passphrase)
        if hidden_ssid:
            if str(hidden_ssid).lower() in ['true', 'yes', 'on', '1']:
                interface_stanza += '\n  wpa-ap-scan 1\n  wpa-scan-ssid 1'

    # Make sure we end with a newline
    interface_stanza += '\n'

    return interface_stanza


def generate_ntp_conf(ntpservers=[
        '0.pool.ntp.org',
        '1.pool.ntp.org',
        '2.pool.ntp.org'
]):
    """
    Generates a `ntp.conf` file.
    :param ntpservers: NTP servers (list)
    """

    if not isinstance(ntpservers, list):
        logging.error('"{}" is an invalid NTP option.'.format(ntpservers))
        return False

    ntp_conf = """# Generated by Screenly Network Manager
driftfile /var/lib/ntp/ntp.drift

statistics loopstats peerstats clockstats
filegen loopstats file loopstats type day enable
filegen peerstats file peerstats type day enable
filegen clockstats file clockstats type day enable
restrict -4 default kod notrap nomodify nopeer noquery
restrict -6 default kod notrap nomodify nopeer noquery

restrict 127.0.0.1
restrict ::1
"""

    for s in ntpservers:
        ntp_conf += "server {} iburst\n".format(s.lower())

    return ntp_conf


def generate_resolv_conf(dns=[
    '8.8.8.8',
    '8.8.4.4'
]):
    """
    Generates a `resolv.conf` file.
    :param dns: DNS servers (list)
    """

    if not isinstance(dns, list):
        logging.error('"{}" is an invalid DNS option.'.format(dns))
        return False

    resolv_file = "# Generated by Screenly Network Manager\n"

    for i in dns:
        resolv_file += 'nameserver {}\n'.format(i.lower())

    return resolv_file


def write_file(path, content):

    with open(path, 'r') as f:
        orig_file = f.read()

    differs = orig_file != content

    if differs:
        with open(path, 'w') as f:
            f.write(content)
        logging.info('Wrote an updated version of {}'.format(path))
    else:
        logging.info('No changes were made to {}.'.format(path))


def lookup(config, interface, key):
    try:
        value = config[interface][key]
        logging.info('[{}] Found value "{}" for key "{}".'.format(interface, value, key))
    except:
        logging.error('[{}] Unable to find value for key {}.'.format(interface, key))
        return False

    return value


def is_dhcp(config, interface):
    """
    Determine if DHCP should be used or not with some basic logic.
    """
    try:
        if_mode = config[interface]['mode']
        if if_mode.lower() in ['dynamic', 'dhcp']:
            return True
        elif if_mode.lower() == 'static':
            return False
        else:
            logging.error('[{}] "{}" is an invalid network mode.'.format(interface, if_mode))
            logging.error('[{}] Reverting to DHCP.'.format(interface))
    except:
        logging.error('[{}] No mode specified. Using DHCP.'.format(interface))

    try:
        # If 'ip', 'netmask' and 'gateway' is set, use static mode.
        if config[interface]['ip'] and config[interface]['netmask'] and config[interface]['gateway']:
            logging.error('[{}] Found static components. Using static config.'.format(interface))
            return False
    except:
        return True


def get_active_iface(config, prefix):
    for n in range(10):
        iface = '{}{}'.format(prefix, n)
        if config.has_section(iface):
            return iface
    return False


def main():
    config = configparser.ConfigParser()
    config.read(NETWORK_PATH)

    logging.info('Started Screenly Network Manager.')

    """
    Configure network interfaces
    """

    interfaces = INTERFACES_TEMPLATE

    ethernet = get_active_iface(config, 'eth')
    wifi = get_active_iface(config, 'wlan')

    if ethernet:
        ethernet_dhcp = is_dhcp(config, ethernet)

        if ethernet_dhcp:
            interfaces += if_config(interface=ethernet)
        else:
            ethernet_ip = lookup(config, ethernet, 'ip')
            ethernet_netmask = lookup(config, ethernet, 'netmask')
            ethernet_gateway = lookup(config, ethernet, 'gateway')

            interfaces += if_config(
                interface=ethernet,
                ip=ethernet_ip,
                netmask=ethernet_netmask,
                gateway=ethernet_gateway
            )

    if wifi:
        wifi_dhcp = is_dhcp(config, wifi)
        ssid = lookup(config, wifi, 'ssid')
        passphrase = lookup(config, wifi, 'passphrase') if config.has_option(wifi, 'passphrase') else None
        hidden_ssid = lookup(config, wifi, 'hidden_ssid') if config.has_option(wifi, 'hidden_ssid') else False

        if wifi_dhcp:
            interfaces += if_config(
                interface=wifi,
                ssid=ssid,
                passphrase=passphrase,
                hidden_ssid=hidden_ssid,
            )
        else:
            wifi_ip = lookup(config, wifi, 'ip')
            wifi_netmask = lookup(config, wifi, 'netmask')
            wifi_gateway = lookup(config, wifi, 'gateway')

            interfaces += if_config(
                interface=wifi,
                ip=wifi_ip,
                netmask=wifi_netmask,
                gateway=wifi_gateway,
                ssid=ssid,
                passphrase=passphrase,
                hidden_ssid=hidden_ssid,
            )

    write_file(INTERFACES_PATH, interfaces)

    """
    Configure DNS
    """

    if config.has_option('generic', 'dns'):
        resolv_conf = generate_resolv_conf(config['generic']['dns'].split(','))
        if resolv_conf:
            write_file(RESOLV_PATH, resolv_conf)
        else:
            logging.error('Unable to read DNS settings.')

    """
    Configure NTP
    """

    if config.has_option('generic', 'ntp'):
        ntp_conf = generate_ntp_conf(config['generic']['ntp'].split(','))
        if ntp_conf:
            write_file(NTP_PATH, ntp_conf)
        else:
            logging.error('Unable to read NTP settings.')

    logging.info('Screenly Network Manager finished.')


if __name__ == "__main__":
    main()
