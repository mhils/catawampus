#!/usr/bin/python
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# TR-069 has mandatory attribute names that don't comply with policy
#pylint: disable-msg=C6409

"""tr-181 Device.Hosts implementation

Provides a way to discover network topologies.
"""

__author__ = 'dgentry@google.com (Denton Gentry)'

import binascii
import os
import struct
import time
import tr.session
import tr.tr181_v2_6
import tr.types

BASE181HOSTS = tr.tr181_v2_6.Device_v2_6.Device.Hosts
BASE181HOST = tr.tr181_v2_6.Device_v2_6.Device.Hosts.Host

# Unit tests can override these
SYS_CLASS_NET_PATH = "/sys/class/net"
TIMENOW = time.time


class Hosts(BASE181HOSTS):
  """Implement tr-181 Device.Hosts table."""

  def __init__(self, iflookup=None, bridgename=None,
               dnsmasqfile=None, dmroot=None):
    """Device.Hosts.

    Args:
      iflookup: a dict mapping Linux ifnames to tr-69
        parameter paths. Ex:
        {'eth0': 'Device.Ethernet.Interface.1.',
         'eth1': 'Device.MoCA.Interface.1.'}
      bridgename: name of the Linux bridge device. Ex: 'br0'
      dnsmasqfile: path to dnsmasq's dhcp.leases file.
      dmroot: root of the Export tree (ex: there should be an
        InternetGatewayDevice attribute for tr-98)
    """
    super(Hosts, self).__init__()
    self.bridges = list()
    self.iflookup = dict()
    self.dnsmasqleases = list()
    self.dmroot = dmroot
    if iflookup:
      self.iflookup = iflookup
    if bridgename:
      x = bridgename if type(bridgename) == list else [bridgename]
      self.bridges.extend(x)
    if dnsmasqfile:
      x = dnsmasqfile if type(dnsmasqfile) == list else [dnsmasqfile]
      self.dnsmasqleases.extend(x)

  def _GetInterfacesInBridge(self, brname):
    """Return list of all interfaces in brname. """
    if_path = os.path.join(SYS_CLASS_NET_PATH, brname, "brif")
    return os.listdir(if_path)

  def _GetHostsInBridge(self, brname):
    """Iterate over all client addresses in the FDB of brname.
    Args:
      brname: name of the bridge netdev, like 'br0'

    Returns:
      iterable of (mac, iface) where:
        mac: MAC address of the station
        iface: name of the interface where the MAC was seen, like 'eth0'
    """
    interfaces = dict()
    for (idx, ifc) in enumerate(self._GetInterfacesInBridge(brname), start=1):
      interfaces[idx] = ifc
    fdb_path = os.path.join(SYS_CLASS_NET_PATH, brname, 'brforward')
    with open(fdb_path) as f:
      fdb = f.read()  # proc file only works if read all at once
      offset = 0
      while offset < len(fdb):
        (m1, m2, m3, m4, m5, m6, port_lo, unused_local, unused_age_timer,
         port_hi, unused_pad1, unused_pad2) = struct.unpack(
             'BBBBBBBBIBBH', fdb[offset:offset+16])
        mac = '%02x:%02x:%02x:%02x:%02x:%02x' % (m1, m2, m3, m4, m5, m6)
        port = (port_hi << 8) | port_lo
        iface = interfaces.get(port, 'unknown')
        yield (mac, iface)
        offset += 16

  def _GetHostsFromBridges(self, hosts):
    """Populate dict of known hosts on bridge devices.

    Walks through the bridge forwarding table.

    Args:
      hosts: a dict (with MAC addresses as keys) of fields
        to be populated for Device.Hosts.Host
    """
    for brname in self.bridges:
      try:
        for (mac, iface) in self._GetHostsInBridge(brname):
          host = hosts.get(mac, dict())
          host['Layer1Interface'] = self.iflookup.get(iface, '')
          host['PhysAddress'] = mac
          hosts[mac] = host
      except (OSError, IOError):
        print '_GetHostsFromBridges unable to process %s' % brname

  def _BinAsciitize(self, s):
    return '' if s == '*' else binascii.hexlify(s)

  def _GetHostsFromDnsmasqLeases(self, hosts):
    """Populate a dict of known hosts from dnsmasq leases file.

    Args:
      hosts: a dict (with MAC addresses as keys) of fields
        to be populated for Device.Hosts.Host
    """
    now = int(TIMENOW())
    for filename in self.dnsmasqleases:
      line = ''
      try:
        with open(filename) as f:
          for line in f:
            (expiry, mac, ip, name, client_id) = line.split()
            mac = mac.lower()
            client_id = self._BinAsciitize(client_id)
            name = '' if name == '*' else name
            host = hosts.get(mac, dict())
            host['PhysAddress'] = mac
            ip4 = host.get('ip4', list())
            ip4.append(ip)
            host['ip4'] = ip4
            host['AddressSource'] = 'DHCP'
            remaining = max(int(expiry) - now, 0)
            host['LeaseTimeRemaining'] = remaining
            host['ClientID'] = client_id
            host['HostName'] = name
            hosts[mac] = host
      except (OSError, IOError, ValueError):
        print 'Unable to process dnsmasq %s : %s' % (filename, line)
        continue

  def _GetTr98WifiObjects(self):
    """Yield tr-98 WLANConfiguration objects, if any."""
    try:
      lan = self.dmroot.GetExport('InternetGatewayDevice.LANDevice.1')
    except (AttributeError, KeyError):
      return
    for (idx, wifi) in lan.WLANConfigurationList.iteritems():
      l1if = 'InternetGatewayDevice.LANDevice.1.WLANConfiguration.%s.' % idx
      yield (l1if, wifi)

  def _GetHostsFromWifiAssociatedDevices(self, hosts):
    """Populate a dict of known hosts from wifi clients.

    Args:
      hosts: a dict (with MAC addresses as keys) of fields
        to be populated for Device.Hosts.Host
    """
    for (l1interface, wifi) in self._GetTr98WifiObjects():
      for (idx, device) in wifi.AssociatedDeviceList.iteritems():
        assocdev = l1interface + 'AssociatedDevice.' + str(idx)
        mac = device.AssociatedDeviceMACAddress.lower()
        host = hosts.get(mac, dict())
        host['AssociatedDevice'] = assocdev
        host['Layer1Interface'] = l1interface
        host['PhysAddress'] = mac
        hosts[mac] = host

  def _GetTr181MocaObjects(self):
    """Yield tr-181 Device.MoCA. objects, if any."""
    try:
      moca = self.dmroot.GetExport('Device.MoCA')
    except (AttributeError, KeyError):
      return
    for (idx, interface) in moca.InterfaceList.iteritems():
      l1if = 'Device.MoCA.Interface.%s.' % idx
      yield (l1if, interface)

  def _GetHostsFromMocaAssociatedDevices(self, hosts):
    """Populate a dict of known hosts from wifi clients."""
    for (l1interface, moca) in self._GetTr181MocaObjects():
      for (idx, device) in moca.AssociatedDeviceList.iteritems():
        assocdev = l1interface + 'AssociatedDevice.' + str(idx)
        mac = device.MACAddress.lower()
        host = hosts.get(mac, dict())
        host['AssociatedDevice'] = assocdev
        host['Layer1Interface'] = l1interface
        host['PhysAddress'] = mac
        hosts[mac] = host

  @tr.session.cache
  def _GetHostList(self):
    hosts = dict()
    self._GetHostsFromBridges(hosts=hosts)
    self._GetHostsFromDnsmasqLeases(hosts=hosts)
    self._GetHostsFromWifiAssociatedDevices(hosts=hosts)
    self._GetHostsFromMocaAssociatedDevices(hosts=hosts)
    host_list = dict()
    for idx, host in enumerate(hosts.values(), start=1):
      host_list[str(idx)] = Host(**host)
    return host_list

  @property
  def HostList(self):
    return self._GetHostList()

  @property
  def HostNumberOfEntries(self):
    return len(self.HostList)


class Host(BASE181HOST):
  """A single network entity; a host system on the network.

  This is an ephemeral object, created from some data source and
  peristing only for the duration of one CWMP session.
  """
  Active = tr.types.ReadOnlyBool(True)
  AddressSource = tr.types.ReadOnlyString('')
  AssociatedDevice = tr.types.ReadOnlyString('')
  ClientID = tr.types.ReadOnlyString('')
  DHCPClient = tr.types.ReadOnlyString('')
  HostName = tr.types.ReadOnlyString('')
  Layer1Interface = tr.types.ReadOnlyString('')
  Layer3Interface = tr.types.ReadOnlyString('')
  LeaseTimeRemaining = tr.types.ReadOnlyInt(0)
  PhysAddress = tr.types.ReadOnlyString('')
  UserClassID = tr.types.ReadOnlyString('')
  VendorClassID = tr.types.ReadOnlyString('')

  def __init__(self, PhysAddress='', ip4=None, ip6=None,
               DHCPClient='', AddressSource='None', AssociatedDevice='',
               Layer1Interface='', Layer3Interface='', HostName='',
               LeaseTimeRemaining=-1, VendorClassID='',
               ClientID='', UserClassID=''):
    super(Host, self).__init__()
    self.Unexport('Alias')

    type(self).AssociatedDevice.Set(self, AssociatedDevice)
    type(self).AddressSource.Set(self, AddressSource)
    type(self).ClientID.Set(self, ClientID)
    type(self).DHCPClient.Set(self, DHCPClient)
    type(self).HostName.Set(self, HostName)
    self.IPv4AddressList = self._PopulateIpList(ip4, HostIPv4Address)
    self.IPv6AddressList = self._PopulateIpList(ip6, HostIPv6Address)
    type(self).Layer1Interface.Set(self, Layer1Interface)
    type(self).Layer3Interface.Set(self, Layer3Interface)
    type(self).LeaseTimeRemaining.Set(self, int(LeaseTimeRemaining))
    type(self).PhysAddress.Set(self, PhysAddress)
    type(self).UserClassID.Set(self, UserClassID)
    type(self).VendorClassID.Set(self, VendorClassID)

  def _PopulateIpList(self, l, obj):
    """Return a dict with d[n] for each item in l."""
    d = dict()
    if l is None:
      return d
    for n, address in enumerate(l, start=1):
      d[str(n)] = obj(address=address)
    return d

  @property
  def IPv4AddressNumberOfEntries(self):
    return len(self.IPv4AddressList)

  @property
  def IPv6AddressNumberOfEntries(self):
    return len(self.IPv6AddressList)

  @property
  def IPAddress(self):
    ip4 = self.IPv4AddressList.get('1', '')
    ip6 = self.IPv6AddressList.get('1', '')
    return ip4 or ip6


class HostIPv4Address(BASE181HOST.IPv4Address):
  IPAddress = tr.types.ReadOnlyString('')
  def __init__(self, address=''):
    super(HostIPv4Address, self).__init__()
    type(self).IPAddress.Set(self, address)


class HostIPv6Address(BASE181HOST.IPv6Address):
  IPAddress = tr.types.ReadOnlyString('')
  def __init__(self, address=''):
    super(HostIPv6Address, self).__init__()
    type(self).IPAddress.Set(self, address)
