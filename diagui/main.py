#!/usr/bin/python
#
"""Implementation of the read-only Diagnostics UI."""

__author__ = 'anandkhare@google.com (Anand Khare)'

import hashlib
import json
import mimetypes
import os
import errno
import google3
import tornado.ioloop
import tornado.web
import tr.cwmptypes
import tr.helpers
import tr.pyinotify

# For unit test overrides.
ONU_STAT_FILE = '/tmp/cwmp/monitoring/onu/onustats.json'
ACTIVEWAN = 'activewan'
AP_DIR = '/tmp/waveguide/signals_json'
SELFSIGNALS_FILE = '/tmp/waveguide/signals_json/self_signals'
APSIGNAL_FILE = '/tmp/waveguide/signals_json/ap_signals'
SOFTWARE_VERSION_FILE = '/etc/version'
MOCAGLOBALJSON = '/tmp/cwmp/monitoring/moca2/globals'


class TechUIJsonHandler(tornado.web.RequestHandler):
  """Provides JSON-formatted info for the TechUI."""

  @tornado.web.asynchronous
  def get(self):
    print 'techui GET JSON data for diagnostics page'
    self.application.techui.UpdateTechUIDict()
    try:
      self.set_header('Content-Type', 'application/json')
      self.write(json.dumps(self.application.techui.data))
      self.finish()
    except IOError:
      pass


class DiagnosticsHandler(tornado.web.RequestHandler):
  """Displays the diagnostics UI."""

  def get(self):
    print 'diagui GET diagnostics HTML page'
    self.render('template.html', run_techui=self.application.run_techui)


class DiagUIJsonHandler(tornado.web.RequestHandler):
  """Provides JSON-formatted content to be displayed in the UI."""

  @tornado.web.asynchronous
  def get(self):    # pylint: disable=g-bad-name
    print 'diagui GET JSON data for diagnostics page'
    self.application.diagui.UpdateDiagUIDict()
    if (self.get_argument('checksum') !=
        self.application.diagui.data.get('checksum', None)):
      try:
        self.set_header('Content-Type', 'text/javascript')
        self.write(tornado.escape.json_encode(self.application.diagui.data))
        self.finish()
      except IOError:
        pass
    else:
      self.application.diagui.callbacklist.append(self.ReturnData)

  def ReturnData(self):
    diagui = self.application.diagui
    if self.get_argument('checksum') != diagui.data['checksum']:
      self.application.diagui.callbacklist.remove(self.ReturnData)
      try:
        self.set_header('Content-Type', 'text/javascript')
        self.write(tornado.escape.json_encode(diagui.data))
        self.finish()
      except IOError:
        pass


class DiagUIRestartHandler(tornado.web.RequestHandler):
  """Restart the network box."""

  def get(self):    # pylint: disable=g-bad-name
    print 'diagui displaying restart interstitial screen'
    self.render('restarting.html')

  def post(self):    # pylint: disable=g-bad-name
    print 'diagui user requested restart'
    self.redirect('/restart')
    os.system('(sleep 5; reboot) &')


def LoadJson(filename):
  try:
    return json.loads(open(filename).read())
  except ValueError:
    return {}  # No json to read
  except IOError as e:
    if e.errno == errno.ENOENT:
      return {}  # file doesn't exist, harmless
    raise


class TechUI(object):
  """Class for the technical UI."""

  def __init__(self, root):
    self.data = {}
    self.root = root
    if self.root:
      for unused_i, inter in self.root.Device.MoCA.InterfaceList.iteritems():
        tr.cwmptypes.AddNotifier(type(inter),
                                 'AssociatedDeviceCount',
                                 lambda unused_obj: self.UpdateMocaDict)
      landevlist = self.root.InternetGatewayDevice.LANDeviceList
      for unused_i, dev in landevlist.iteritems():
        for unused_j, wlconf in dev.WLANConfigurationList.iteritems():
          tr.cwmptypes.AddNotifier(type(wlconf),
                                   'SignalsStr',
                                   lambda unused_obj: self.UpdateWifiDict)
    ioloop = tornado.ioloop.IOLoop.instance()
    mask = tr.pyinotify.IN_MODIFY
    self.ap_wm = tr.pyinotify.WatchManager()
    self.ap_notifier = tr.pyinotify.TornadoAsyncNotifier(
        self.ap_wm, ioloop, callback=lambda unused_obj: self.UpdateAPDict)
    if os.path.exists(AP_DIR):
      self.ap_wm.add_watch(AP_DIR, mask)

  def UpdateMocaDict(self):
    """Updates the dictionary with Moca data from catawampus."""
    snr = {}
    bitloading = {}
    corrected_cw = {}
    uncorrected_cw = {}
    nbas = {}

    global_content = LoadJson(MOCAGLOBALJSON)
    try:
      global_node_id = global_content['NodeId']
    except KeyError:
      global_node_id = 17  # max number of nodes is 16
    for unused_i, inter in self.root.Device.MoCA.InterfaceList.iteritems():
      for unused_j, dev in inter.AssociatedDeviceList.iteritems():
        if dev.NodeID != global_node_id:  #  to avoid getting info about self
          snr[dev.MACAddress] = dev.X_CATAWAMPUS_ORG_RxSNR_dB
          bitloading[dev.MACAddress] = dev.X_CATAWAMPUS_ORG_RxBitloading
          nbas[dev.MACAddress] = dev.X_CATAWAMPUS_ORG_RxNBAS
          corrected = (dev.X_CATAWAMPUS_ORG_RxPrimaryCwCorrected +
                       dev.X_CATAWAMPUS_ORG_RxSecondaryCwCorrected)
          uncorrected = (dev.X_CATAWAMPUS_ORG_RxPrimaryCwUncorrected +
                         dev.X_CATAWAMPUS_ORG_RxSecondaryCwUncorrected)
          no_errors = (dev.X_CATAWAMPUS_ORG_RxPrimaryCwNoErrors +
                       dev.X_CATAWAMPUS_ORG_RxSecondaryCwNoErrors)
          total = corrected + uncorrected + no_errors
          try:
            corrected_cw[dev.MACAddress] = corrected/total
            uncorrected_cw[dev.MACAddress] = uncorrected/total
          except ZeroDivisionError:
            corrected_cw[dev.MACAddress] = 0
            uncorrected_cw[dev.MACAddress] = 0
    self.data['moca_signal_strength'] = snr
    self.data['moca_corrected_codewords'] = corrected_cw
    self.data['moca_uncorrected_codewords'] = uncorrected_cw
    self.data['moca_bitloading'] = bitloading
    self.data['moca_nbas'] = nbas

  def UpdateWifiDict(self):
    """Updates the wifi signal strength dict using catawampus."""
    wifi_signal_strengths = {}
    landevlist = self.root.InternetGatewayDevice.LANDeviceList
    for unused_i, dev in landevlist.iteritems():
      for unused_j, wlconf in dev.WLANConfigurationList.iteritems():
        wifi_signal_strengths = wlconf.signals

    self.data['wifi_signal_strength'] = wifi_signal_strengths

  def UpdateAPDict(self):
    """Reads JSON from the access points files and updates the dict."""
    # TODO(theannielin): waveguide data should be in cwmp, but it's not,
    # so we read it here
    self.data['other_aps'] = LoadJson(APSIGNAL_FILE)
    self.data['self_signals'] = LoadJson(SELFSIGNALS_FILE)

  def UpdateTechUIDict(self):
    """Updates the data dictionary."""

    if not self.root:
      return

    self.data = {}

    host_names = {}
    ip_addr = {}
    try:
      hostinfo = self.root.Device.Hosts.HostList
    except AttributeError:
      hostinfo = {}
    for host in hostinfo.itervalues():
      host_names[host.PhysAddress] = host.HostName
      ip_addr[host.PhysAddress] = host.IPAddress
    self.data['host_names'] = host_names
    self.data['ip_addr'] = ip_addr

    deviceinfo = self.root.Device.DeviceInfo
    self.data['softversion'] = deviceinfo.SoftwareVersion

    self.UpdateMocaDict()
    self.UpdateWifiDict()
    self.UpdateAPDict()


class DiagUI(object):
  """Class for the diagnostics UI."""

  def __init__(self, root, cpemach):
    self.data = {}
    self.root = root
    self.cpemach = cpemach
    self.pathname = os.path.dirname(__file__)
    if self.root:
      # TODO(anandkhare): Add notifiers on more parameters using the same format
      # as below, as and when they are implemented using types.py.
      tr.cwmptypes.AddNotifier(type(self.root.Device.Ethernet),
                               'InterfaceNumberOfEntries', self.AlertNotifiers)
    self.ioloop = tornado.ioloop.IOLoop.instance()
    self.wm = tr.pyinotify.WatchManager()
    self.mask = tr.pyinotify.IN_CLOSE_WRITE
    self.callbacklist = []
    self.notifier = tr.pyinotify.TornadoAsyncNotifier(
        self.wm, self.ioloop, callback=self.AlertNotifiers)
    self.wdd = self.wm.add_watch(
        os.path.join(self.pathname, 'Testdata'), self.mask)

  def AlertNotifiers(self, unused_obj):
    self.UpdateDiagUIDict()
    for i in self.callbacklist[:]:
      i()

  def UpdateCheckSum(self):
    newchecksum = hashlib.sha1(unicode(
        sorted(list(self.data.items()))).encode('utf-8')).hexdigest()
    self.data['checksum'] = newchecksum

  def UpdateDiagUIDict(self):
    """Updates the dictionary and checksum value."""

    if not self.root:
      return

    self.data = {}
    self.data['subnetmask'] = ''

    deviceinfo = self.root.Device.DeviceInfo
    tempstatus = deviceinfo.TemperatureStatus
    landevlist = self.root.InternetGatewayDevice.LANDeviceList
    etherlist = self.root.Device.Ethernet.InterfaceList

    if self.cpemach and self.cpemach.last_success_response:
      self.data['acs'] = 'OK (%s)' % self.cpemach.last_success_response
    else:
      self.data['acs'] = 'Never contacted'
    self.data['softversion'] = deviceinfo.SoftwareVersion
    self.data['uptime'] = deviceinfo.UpTime
    self.data['username'] = self.root.Device.ManagementServer.Username

    t = dict()
    try:
      for unused_i, sensor in tempstatus.TemperatureSensorList.iteritems():
        t[sensor.Name] = sensor.Value
      self.data['temperature'] = t
    except AttributeError:
      pass

    wan_addrs = dict()
    lan_addrs = dict()
    for unused_i, inter in self.root.Device.IP.InterfaceList.iteritems():
      t = wan_addrs if inter.Name in ['wan0', 'wan0.2'] else lan_addrs
      for unused_j, ip4 in inter.IPv4AddressList.iteritems():
        # Static IPs show up even if there is no address.
        if ip4.IPAddress is not None:
          t[ip4.IPAddress] = '(%s)' % ip4.Status
          self.data['subnetmask'] = ip4.SubnetMask
      for unused_i, ip6 in inter.IPv6AddressList.iteritems():
        if ip6.IPAddress[:4] != 'fe80':
          t[ip6.IPAddress] = '(%s)' % ip6.Status
    self.data['lanip'] = lan_addrs
    self.data['wanip'] = wan_addrs

    wan_mac = dict()
    lan_mac = dict()
    t = dict()
    for unused_i, interface in etherlist.iteritems():
      if interface.Name in ['wan0', 'wan0.2']:
        wan_mac[interface.MACAddress] = '(%s)' % interface.Status
      else:
        lan_mac[interface.MACAddress] = '(%s)' % interface.Status
    self.data['lanmac'] = lan_mac
    self.data['wanmac'] = wan_mac

    t = dict()
    for unused_i, inter in self.root.Device.MoCA.InterfaceList.iteritems():
      for unused_j, dev in inter.AssociatedDeviceList.iteritems():
        t[dev.NodeID] = dev.MACAddress
    self.data['wireddevices'] = t

    wlan = dict()
    devices = dict()
    wpa = dict()
    self.data['ssid5'] = ''

    for unused_i, dev in landevlist.iteritems():
      for unused_j, wlconf in dev.WLANConfigurationList.iteritems():
        # Convert the channel to an int here.  It is returned as a string.
        try:
          ch = int(wlconf.Channel)
        except ValueError:
          print ('wlconf.Channel returned a non-integer value: %s' %
                 (wlconf.Channel,))
          continue

        if ch in range(1, 12):
          self.data['ssid24'] = wlconf.SSID
          if wlconf.WPAAuthenticationMode == 'PSKAuthentication':
            wpa['2.4 GHz'] = '(Configured)'
          wlan[wlconf.BSSID] = '(2.4 GHz) (%s)' % wlconf.Status
          for unused_k, assoc in wlconf.AssociatedDeviceList.iteritems():
            devices[assoc.AssociatedDeviceMACAddress] = (
                '(2.4 GHz) (Authentication state: %s)'
                % assoc.AssociatedDeviceAuthenticationState)
        else:
          self.data['ssid5'] = wlconf.SSID
          if wlconf.WPAAuthenticationMode == 'PSKAuthentication':
            wpa['5 GHz'] = '(Configured)'
          wlan[wlconf.BSSID] = '(5 GHz) (%s)' % wlconf.Status
          for unused_k, assoc in wlconf.AssociatedDeviceList.iteritems():
            devices[assoc.AssociatedDeviceMACAddress] = (
                '(5 GHz) (Authentication state: %s)'
                % assoc.AssociatedDeviceAuthenticationState)

    self.data['wirelesslan'] = wlan
    self.data['wirelessdevices'] = devices
    self.data['wpa2'] = wpa

    if 'ssid24' in self.data and 'ssid5' in self.data:
      if self.data['ssid5'] == self.data['ssid24']:
        self.data['ssid5'] = '(same)'

    try:
      self.data['upnp'] = self.root.UPnP.Device.Enable
    except AttributeError:
      self.data['upnp'] = 'Off'

    try:
      dns = self.root.DNS.SD.ServiceList
      for unused_i, serv in dns.iteritems():
        self.data['dyndns'] = serv.InstanceName
        self.data['domain'] = serv.Domain
    except AttributeError:
      pass

    # We want the 'connected' field to be a boolean, but Activewan
    # returns either the empty string, or the name of the active wan
    # interface.
    self.data['connected'] = not not tr.helpers.Activewan(ACTIVEWAN)

    self.ReadOnuStats()
    self.UpdateCheckSum()

  def ReadOnuStats(self):
    """Read the ONU stat file and store into self.data."""
    try:
      with open(ONU_STAT_FILE) as f:
        stats = f.read()
    except IOError:
      return

    try:
      json_stats = json.loads(stats)
    except ValueError:
      print 'Failed to decode onu stat file.'
      return

    self.data.update(json_stats)


class MainApplication(tornado.web.Application):
  """Defines settings for the server and notifier."""

  def __init__(self, root, cpemach, run_techui=False):
    self.diagui = DiagUI(root, cpemach)
    self.run_techui = run_techui
    self.techui = TechUI(root)
    self.pathname = os.path.dirname(__file__)
    staticpath = os.path.join(self.pathname, 'static')
    self.settings = {
        'static_path': staticpath,
        'template_path': self.pathname,
        'xsrf_cookies': True,
    }

    handlers = [
        (r'/', DiagnosticsHandler),
        (r'/content.json', DiagUIJsonHandler),
        (r'/restart', DiagUIRestartHandler),
    ]

    if run_techui:
      handlers += [
          (r'/tech/?', tornado.web.RedirectHandler,
           {'url': '/tech/index.html'}),
          (r'/tech/(.*)', tornado.web.StaticFileHandler,
           {'path': os.path.join(self.pathname, 'techui_static')}),
          (r'/techui.json', TechUIJsonHandler),
      ]

    super(MainApplication, self).__init__(handlers, **self.settings)
    mimetypes.add_type('font/ttf', '.ttf')
