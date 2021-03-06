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

# unittest requires method names starting in 'test'
# pylint:disable=invalid-name

"""Unit tests for cwmpd."""

__author__ = 'apenwarr@google.com (Avery Pennarun)'

import os
import select
import subprocess
import google3
import tr.helpers
from tr.wvtest import unittest


class RunserverTest(unittest.TestCase):
  """Tests for cwmpd and cwmp."""

  sockname = '/tmp/cwmpd_test.sock.%d' % os.getpid()

  def _StartClient(self, extra_args=None, stdout=None, stderr=None):
    if extra_args is None:
      extra_args = []
    client = subprocess.Popen(['./cwmp', '--unix-path', self.sockname] +
                              extra_args,
                              stdin=subprocess.PIPE, stdout=stdout,
                              stderr=stderr)
    client.stdin.close()
    return client

  def _DoTest(self, args, extra_args=None, expect_result=0):
    out = []
    if extra_args is None:
      extra_args = []
    print
    print 'Testing with args=%r extra=%r' % (args, extra_args)
    tr.helpers.Unlink(self.sockname)
    server = subprocess.Popen(['./cwmpd',
                               '--platform', 'fakecpe',
                               '--rcmd-port', '0',
                               '--unix-path', self.sockname,
                               '--ext-dir', 'ext_test',
                               '--close-stdio'] + args,
                              stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    try:
      print 'waiting for server to start...'
      while server.stdout.read():
        pass
      client = self._StartClient(extra_args=extra_args,
                                 stderr=subprocess.PIPE)
      out = client.stderr.read()
      print 'client stderr was %r' % out
      self.assertEqual(client.wait(), expect_result)
      server.stdin.close()
      self.assertEqual(server.wait(), 0)
    finally:
      try:
        server.kill()
      except OSError:
        pass
      tr.helpers.Unlink(self.sockname)
    return out

  def testExitOnError(self):
    print 'testing client exit when server not running'
    client = self._StartClient(stdout=subprocess.PIPE)
    r, _, _ = select.select([client.stdout], [], [], 5)
    try:
      self.assertNotEqual(r, [])
      self.assertNotEqual(client.wait(), 0)
    finally:
      if client.poll() is None:
        client.kill()

  def testRunserver(self):
    self._DoTest([])
    self._DoTest(['--port=0'])
    self._DoTest(['--no-cpe'])
    self._DoTest(['--no-cpe', '--diagui', '--diagui-port=0'])
    self._DoTest(['--no-cpe',
                  '--platform', 'fakecpe'])
    self._DoTest(['--fake-acs',
                  '--platform', 'fakecpe'], extra_args=['validate'])
    out = self._DoTest(
        ['--fake-acs', '--platform', 'fakecpe'],
        expect_result=1,
        extra_args=['get', 'Device.DHCPv4.Server.Pool.1.Client.999.Active'])
    print 'out is %r' % out
    self.assertFalse('Device.DHCPv4.Server.Pool.1.Client.999.Active' in out)
    self.assertTrue('Device.DHCPv4.Server.Pool.1.Client.999' in out)


if __name__ == '__main__':
  unittest.main()
