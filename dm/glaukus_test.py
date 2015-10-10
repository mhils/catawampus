#!/usr/bin/python
# Copyright 2015 Google Inc. All Rights Reserved.
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

"""Unit tests for TR-181 Device.X_CATAWAMPUS_ORG.Glaukus."""

__author__ = 'cgibson@google.com (Chris Gibson)'

import google3

from tr.wvtest import unittest
import tr.handle
import glaukus


class GlaukusTest(unittest.TestCase):
  """Tests for glaukus.py."""

  def setUp(self):
    self.glaukus = glaukus.Glaukus()

  def testValidate(self):
    tr.handle.ValidateExports(self.glaukus)


if __name__ == '__main__':
  unittest.main()