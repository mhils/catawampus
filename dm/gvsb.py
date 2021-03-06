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
"""Implement the X_GOOGLE-COM_GVSB vendor data model."""

__author__ = 'dgentry@google.com (Denton Gentry)'

import os
import google3
import tr.cwmptypes
import tr.x_catawampus_tr181_2_0

BASE = tr.x_catawampus_tr181_2_0.X_CATAWAMPUS_ORG_Device_v2_0
CATABASE = BASE.Device.X_CATAWAMPUS_ORG

# Unit tests can override these.
EPGPRIMARYFILE = ['/tmp/epgprimary']
EPGSECONDARYFILE = ['/tmp/epgsecondary']
EPGURLFILE = ['/tmp/epgurl']
GVSBCHANNELFILE = ['/tmp/gvsbchannel']
GVSBKICKFILE = ['/tmp/gvsbkick']
GVSBSERVERFILE = ['/tmp/gvsbhost']


class Gvsb(CATABASE.GVSB):
  """Implementation of x-gvsb.xml."""
  EpgPrimary = tr.cwmptypes.FileBacked(
      EPGPRIMARYFILE, tr.cwmptypes.String(), delete_if_empty=False)
  EpgSecondary = tr.cwmptypes.FileBacked(
      EPGSECONDARYFILE, tr.cwmptypes.String(), delete_if_empty=False)
  EpgUrl = tr.cwmptypes.FileBacked(
      EPGURLFILE, tr.cwmptypes.String(), delete_if_empty=False)
  GvsbChannelLineup = tr.cwmptypes.FileBacked(
      GVSBCHANNELFILE, tr.cwmptypes.String(), delete_if_empty=False)
  GvsbKick = tr.cwmptypes.FileBacked(
      GVSBKICKFILE, tr.cwmptypes.String(), delete_if_empty=False,
      file_owner='video', file_group='video')
  GvsbServer = tr.cwmptypes.FileBacked(
      GVSBSERVERFILE, tr.cwmptypes.String(), delete_if_empty=False)

  def __init__(self):
    super(Gvsb, self).__init__()
    if not os.path.exists(EPGPRIMARYFILE[0]): self.EpgPrimary = ''
    if not os.path.exists(EPGSECONDARYFILE[0]): self.EpgSecondary = ''
    if not os.path.exists(EPGURLFILE[0]): self.EpgUrl = ''
    if not os.path.exists(GVSBCHANNELFILE[0]): self.GvsbChannelLineup = '0'
    if not os.path.exists(GVSBKICKFILE[0]): self.GvsbKick = ''
    if not os.path.exists(GVSBSERVERFILE[0]): self.GvsbServer = ''
