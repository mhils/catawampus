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
# pylint:disable=invalid-name
#
"""Device.IP.Diagnostics.X_CATAWAMPUS-ORG.Speedtest.

Supports the Ookla speedtest and the Fiber-developed speedtest.
"""

__author__ = 'dgentry@google.com (Denton Gentry)'

import calendar
import datetime
import os
import shutil
import subprocess
import google3
import tornado.ioloop
import tr.cwmptypes
import tr.handle
import tr.mainloop
import tr.x_catawampus_tr181_2_0


CATA181DEVICE = tr.x_catawampus_tr181_2_0.X_CATAWAMPUS_ORG_Device_v2_0.Device
CATA181SPEED = CATA181DEVICE.X_CATAWAMPUS_ORG.Speedtest
FIBERSPEEDTEST = 'speedtest'
OOKLACLIENT = 'OoklaClient'
OOKLACLIENTDIR = '/tmp/ookla'
TIMENOW = datetime.datetime.now


class Speedtest(CATA181SPEED):
  """Implementation of the Speedtest vendor extension for TR-181."""
  Arguments = tr.cwmptypes.String('')
  License = tr.cwmptypes.String('')
  Output = tr.cwmptypes.ReadOnlyString('')
  LastResultTime = tr.cwmptypes.ReadOnlyDate()

  def __init__(self, ioloop=None):
    super(Speedtest, self).__init__()
    self.ioloop = ioloop or tornado.ioloop.IOLoop.instance()
    self.buffer = ''
    self.error = None
    self.requested = False
    self.subproc = None

  def _GetState(self):
    if self.requested or self.subproc:
      return 'Requested'
    elif self.error:
      return self.error
    elif self.Output:
      return 'Complete'
    else:
      return 'Error_Internal'  # Should not happen

  def _SetState(self, value):
    if value != 'Requested':
      raise ValueError('DiagnosticsState can only be set to "Requested"')
    self.requested = True
    self._StartProc()

  DiagnosticsState = property(_GetState, _SetState, None,
                              'X_CATAWAMPUS-ORG.Speedtest.DiagnosticsState')

  def _WriteLicense(self):
    if self.License:
      licensefile = os.path.join(OOKLACLIENTDIR, 'settings.xml')
      with open(licensefile, 'w') as f:
        f.write(self.License)
      print 'Wrote %d bytes to %s' % (len(self.License), licensefile)

  def _EndProc(self):
    print 'speedtest finished.'
    type(self).Output.Set(self, self.buffer)
    type(self).LastResultTime.Set(self, calendar.timegm(TIMENOW().timetuple()))
    self.buffer = ''
    if self.subproc:
      self.ioloop.remove_handler(self.subproc.stdout.fileno())
      if self.subproc.poll() is None:
        self.subproc.kill()
      exit_code = self.subproc.poll()
      if exit_code:
        self.error = 'Error_Internal'
      self.subproc = None

  def MaybeRunOoklaClient(self):
    """Try to run the OoklaClient, return true if successful."""
    try:
      shutil.rmtree(path=OOKLACLIENTDIR, ignore_errors=True)
      os.mkdir(OOKLACLIENTDIR)
      self._WriteLicense()
    except (IOError, OSError):
      print 'OoklaClient license dir creation failed'
      self.error = 'Error_Internal'
      return False
    argv = [OOKLACLIENT] + self.Arguments.split()
    print 'Trying:  %r : %s' % (argv, OOKLACLIENTDIR)
    try:
      self.subproc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                      cwd=OOKLACLIENTDIR)
    except OSError:
      print 'OoklaClient failed to start'
      return False
    return True

  def MaybeRunFiberspeedtest(self):
    """Try to run the Fiber speedtest, return true if successful."""
    cmd = [FIBERSPEEDTEST, '--verbose', '--ping_timeout=10000']
    argv = cmd + self.Arguments.split()
    print 'Trying:  %r' % (argv)
    try:
      self.subproc = subprocess.Popen(argv, stdout=subprocess.PIPE)
    except OSError:
      return False
    return True

  @tr.mainloop.WaitUntilIdle
  def _StartProc(self):
    self._EndProc()
    self.error = ''
    self.buffer = ''
    self.requested = False
    success = False
    print 'speedtest starting.'
    if self.MaybeRunFiberspeedtest():
      print 'started Fiber speedtest'
      success = True
    elif self.MaybeRunOoklaClient():
      print 'started Ookla speedtest'
      success = True
    else:
      print 'Unable to start speedtest'
      self.error = 'Error_Internal'

    if success:
      self.ioloop.add_handler(self.subproc.stdout.fileno(),
                              self._GotData, self.ioloop.READ)

  # pylint:disable=unused-argument
  def _GotData(self, fd, events):
    data = os.read(fd, 4096)
    if not data:
      self._EndProc()
    else:
      self.buffer += data

if __name__ == '__main__':
  print tr.handle.DumpSchema(Speedtest(None))
