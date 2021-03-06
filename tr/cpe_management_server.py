#!/usr/bin/python
# Copyright 2011 Google Inc. All Rights Reserved.
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
# pylint:disable=invalid-name
#
"""Implement the inner handling for tr-98/181 ManagementServer."""

__author__ = 'dgentry@google.com (Denton Gentry)'

import datetime
import math
import os
import random
import re
import sys
import time
import urlparse

import google3
import tornado.ioloop
import helpers
import cwmptypes


# Allow unit tests to override with a mock
PERIODIC_CALLBACK = tornado.ioloop.PeriodicCallback
SESSIONTIMEOUTFILE = '/tmp/cwmp/session_timeout'


class CpeManagementServer(object):
  """Inner class implementing tr-98 & 181 ManagementServer."""

  # The default password is trivial. In the initial Inform exchange
  # the ACS generally sets ConnectionRequest{Username,Password}
  # to values which only it knows. If something goes wrong, we want
  # the password to be well known so the ACS can wake us up and
  # try again.
  ConnectionRequestPassword = cwmptypes.TriggerString('cwmp')
  ConnectionRequestUsername = cwmptypes.TriggerString('catawampus')
  CWMPRetryMinimumWaitInterval = cwmptypes.TriggerUnsigned(5)
  CWMPRetryIntervalMultiplier = cwmptypes.TriggerUnsigned(2000)
  DefaultActiveNotificationThrottle = cwmptypes.TriggerUnsigned(0)
  EnableCWMP = cwmptypes.ReadOnlyBool(True)
  PeriodicInformEnable = cwmptypes.TriggerBool(True)
  PeriodicInformTime = cwmptypes.TriggerDate(0)
  Password = cwmptypes.TriggerString('')
  STUNEnable = cwmptypes.ReadOnlyBool(False)
  UpgradesManaged = cwmptypes.ReadOnlyBool(True)
  Username = cwmptypes.TriggerString('')

  def __init__(self, acs_config, port, ping_path,
               acs_url=None, get_parameter_key=None,
               start_periodic_session=None, ioloop=None,
               restrict_acs_hosts=None, conman_dir='/tmp/conman'):
    self._acs_config = acs_config
    self.acs_url = acs_url
    self.get_parameter_key = get_parameter_key
    self.ioloop = ioloop or tornado.ioloop.IOLoop.instance()
    self.my_ip = None
    self._periodic_callback = None
    self._periodic_interval = 0
    self._periodic_intervals_startup = 5
    self.ping_path = ping_path
    self.port = port
    self.restrict_acs_hosts = restrict_acs_hosts
    self.start_periodic_session = start_periodic_session
    self._start_periodic_timeout = None
    self._conman_dir = conman_dir
    self.ConfigurePeriodicInform()

  def Triggered(self):
    self.ConfigurePeriodicInform()

  def SuccessfulSession(self):
    """Called when we successfully terminate a CWMP session."""
    if self._periodic_intervals_startup > 0:
      self._periodic_intervals_startup -= 1

  def GetPeriodicInformInterval(self):
    if self._periodic_interval:
      return self._periodic_interval
    # checkin the first few times on a short interval, to give
    # the ACS several opportunities to set PeriodicInformInterval.
    return 60 if self._periodic_intervals_startup > 0 else (15 * 60)

  def SetPeriodicInformInterval(self, value):
    self._periodic_interval = int(value)

  PeriodicInformInterval = property(
      GetPeriodicInformInterval,
      SetPeriodicInformInterval, None,
      'tr-98/181 ManagementServer.PeriodicInformInterval')

  def ValidateAcsUrl(self, value):
    """Checks if the URL passed is acceptable.  If not raises an exception."""
    if not self.restrict_acs_hosts or not value:
      return

    # Require https for the url scheme.
    split_url = urlparse.urlsplit(value)
    if split_url.scheme != 'https':
      raise ValueError('The ACS Host must be https: %r' % (value,))

    # Iterate over the restrict domain name list and see if one of
    # the restricted domain names matches the supplied url host name.
    restrict_hosts = re.split(r'[\s,]+', self.restrict_acs_hosts)
    for host in restrict_hosts:
      # Check the full hostname.
      if split_url.hostname == host:
        return

      # Check against the restrict host of form '.foo.com'
      if not host.startswith('.'):
        dotted_host = '.' + host
      else:
        dotted_host = host
      if split_url.hostname.endswith(dotted_host):
        return

    # If we don't find a valid host, raise an exception.
    raise ValueError('The ACS Host is not permissible: %r' % (value,))

  def WantACSAutoprovisioning(self):
    """Whether to enable ACS autoprovisioning."""
    # Defaults to off, since that's the safest failure mode.  We'd rather
    # fail to autoprovision when there's a bug (easy to detect the bug)
    # rather than accidentally autoprovisioning when we don't want it (weird
    # edge cases that are hard to detect).
    return os.path.exists(os.path.join(self._conman_dir,
                                       'acs_autoprovisioning'))

  def _GetURL(self):
    """Return the ACS URL to use (internal only)."""
    if self.acs_url:
      try:
        self.ValidateAcsUrl(self.acs_url)
        return self.acs_url
      except ValueError as e:
        print 'Supplied acs_url %r is invalid (%s)' % (self.acs_url, e)

    url = self._acs_config.GetAcsUrl()
    max_attempts = 20
    while url and max_attempts:
      try:
        self.ValidateAcsUrl(url)
        self.MostRecentURL = url
        return url
      except ValueError as e:
        print 'Invalidating url %r (%s)' % (url, e)
        if not self._acs_config.InvalidateAcsUrl(url):
          print ('set-acs failed to invalidate url!'
                 'Something is extremely broken.')
          sys.exit(100)
        url = None
      url = self._acs_config.GetAcsUrl()
      max_attempts -= 1
    # If we get here, there is no valid platform url.
    return None

  def GetURL(self):
    """Return the ACS URL to use."""
    url = self._GetURL()
    # All assignments could trigger callbacks, so don't assign unless the
    # value has changed.
    if url and self.MostRecentURL != url:
      self.MostRecentURL = url
    return url

  def SetURL(self, value):
    self.ValidateAcsUrl(value)
    if self.acs_url:
      self.acs_url = value
    else:
      self._acs_config.SetAcsUrl(value)
    self.MostRecentURL = value

  URL = property(GetURL, SetURL, None, 'tr-98/181 ManagementServer.URL')

  # This is mainly to allow other code to register callbacks.
  # TODO(apenwarr): convert URL to use tr.cwmptypes someday.
  MostRecentURL = cwmptypes.String()

  def _formatIP(self, ip):
    return '[' + ip + ']' if helpers.IsIP6Addr(ip) else ip

  def GetConnectionRequestURL(self):
    if self.my_ip and self.port and self.ping_path:
      path = self.ping_path if self.ping_path[0] != '/' else self.ping_path[1:]
      ip = self._formatIP(self.my_ip)
      return 'http://%s:%d/%s' % (ip, self.port, path)
    else:
      return ''
  ConnectionRequestURL = property(
      GetConnectionRequestURL, None, None,
      'tr-98/181 ManagementServer.ConnectionRequestURL')

  def GetParameterKey(self):
    if self.get_parameter_key is not None:
      return self.get_parameter_key()
    else:
      return ''
  ParameterKey = property(GetParameterKey, None, None,
                          'tr-98/181 ManagementServer.ParameterKey')

  def ConfigurePeriodicInform(self):
    """Commit changes to PeriodicInform parameters."""
    if self._periodic_callback:
      self._periodic_callback.stop()
      self._periodic_callback = None
    if self._start_periodic_timeout:
      self.ioloop.remove_timeout(self._start_periodic_timeout)
      self._start_periodic_timeout = None

    # Delete the old periodic callback.
    if self._periodic_callback:
      self._periodic_callback.stop()
      self._periodic_callback = None

    if self.PeriodicInformEnable and self.PeriodicInformInterval > 0:
      msec = self.PeriodicInformInterval * 1000
      self._periodic_callback = PERIODIC_CALLBACK(self.start_periodic_session,
                                                  msec, self.ioloop)
      if self.PeriodicInformTime:
        # PeriodicInformTime is just meant as an offset, not an actual time.
        # So if it's 25.5 hours in the future and the interval is 1 hour, then
        # the interesting part is the 0.5 hours, not the 25.
        #
        # timetuple might be in the past, but that's okay; the modulus
        # makes sure it's never negative.  (ie. (-3 % 5) == 2, in python)
        timetuple = self.PeriodicInformTime.timetuple()
        offset = ((time.mktime(timetuple) - time.time())
                  % float(self.PeriodicInformInterval))
      else:
        offset = 0.0
      self._start_periodic_timeout = self.ioloop.add_timeout(
          datetime.timedelta(seconds=offset), self.StartPeriodicInform)

  def StartPeriodicInform(self):
    self._periodic_callback.start()

  def SessionRetryWait(self, retry_count):
    """Calculate wait time before next session retry.

    See $SPEC3 section 3.2.1 for a description of the algorithm.

    Args:
      retry_count: integer number of retries attempted so far.

    Returns:
      Number of seconds to wait before initiating next session.
    """
    if retry_count == 0:
      return 0
    periodic_interval = self.PeriodicInformInterval
    if self.PeriodicInformInterval <= 0:
      periodic_interval = 30
    c = 10 if retry_count >= 10 else retry_count
    m = float(self.CWMPRetryMinimumWaitInterval)
    k = float(self.CWMPRetryIntervalMultiplier) / 1000.0
    start = m * math.pow(k, c - 1)
    stop = start * k
    # pin start/stop to have a maximum value of PeriodicInformInterval
    start = int(min(start, periodic_interval / k))
    stop = int(min(stop, periodic_interval))
    randomwait = random.randrange(start, stop)
    return self.GetTimeout(SESSIONTIMEOUTFILE, randomwait)

  def GetTimeout(self, filename, default=60):
    """Get timeout value from file for testing."""
    try:
      return int(open(filename).readline().strip())
    except (IOError, ValueError):
      pass
    return default
