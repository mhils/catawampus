#!/usr/bin/python
#
# Copyright 2012 Google Inc. All Rights Reserved.
#
# unittest requires method names starting in 'test'
#pylint: disable-msg=C6409

"""Unit tests for storage.py implementation."""

__author__ = 'dgentry@google.com (Denton Gentry)'

import collections
import unittest

import google3
import storage
import tr.cwmpbool


statvfsstruct = collections.namedtuple(
    'statvfs', ('f_bsize f_frsize f_blocks f_bfree f_bavail f_files f_ffree '
                'f_favail f_flag f_namemax'))


def OsStatVfs(rootpath):
  teststatvfs = dict()
  teststatvfs['/fakepath'] = statvfsstruct(
      f_bsize=4096, f_frsize=512, f_blocks=1024, f_bfree=512, f_bavail=498,
      f_files=1099, f_ffree=1092, f_favail=1050, f_flag=0, f_namemax=256)
  teststatvfs['/'] = statvfsstruct(
      f_bsize=4096, f_frsize=512, f_blocks=2048, f_bfree=100, f_bavail=120,
      f_files=2000, f_ffree=1000, f_favail=850, f_flag=0, f_namemax=256)
  teststatvfs['/tmp'] = statvfsstruct(
      f_bsize=8192, f_frsize=512, f_blocks=4096, f_bfree=1002, f_bavail=1202,
      f_files=9000, f_ffree=5000, f_favail=4000, f_flag=0, f_namemax=256)
  teststatvfs['/foo'] = statvfsstruct(
      f_bsize=2048, f_frsize=256, f_blocks=8192, f_bfree=5017, f_bavail=3766,
      f_files=6000, f_ffree=4000, f_favail=3000, f_flag=0, f_namemax=256)
  return teststatvfs[rootpath]


class StorageTest(unittest.TestCase):
  def setUp(self):
    storage.STATVFS = OsStatVfs
    self.old_PROC_FILESYSTEMS = storage.PROC_FILESYSTEMS
    self.old_PROC_MOUNTS = storage.PROC_MOUNTS
    self.old_SMARTCTL = storage.SMARTCTL
    self.old_SYS_BLOCK = storage.SYS_BLOCK

  def tearDown(self):
    storage.PROC_FILESYSTEMS = self.old_PROC_FILESYSTEMS
    storage.PROC_MOUNTS = self.old_PROC_MOUNTS
    storage.SMARTCTL = self.old_SMARTCTL
    storage.SYS_BLOCK = self.old_SYS_BLOCK

  def testValidateExports(self):
    storage.PROC_FILESYSTEMS = 'testdata/storage/proc.filesystems'
    storage.PROC_MOUNTS = 'testdata/storage/proc.mounts'
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    service = storage.StorageServiceLinux26()
    service.ValidateExports()
    stor = storage.LogicalVolumeLinux26('/fakepath', 'fstype')
    stor.ValidateExports()
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')

  def testCapacity(self):
    stor = storage.LogicalVolumeLinux26('/fakepath', 'fstype')
    teststatvfs = OsStatVfs('/fakepath')
    expected = teststatvfs.f_bsize * teststatvfs.f_blocks
    self.assertEqual(stor.Capacity, expected)

  def testUsedSpace(self):
    stor = storage.LogicalVolumeLinux26('/fakepath', 'fstype')
    teststatvfs = OsStatVfs('/fakepath')
    used = (teststatvfs.f_blocks - teststatvfs.f_bavail) * teststatvfs.f_bsize
    self.assertEqual(stor.UsedSpace, used)

  def testLogicalVolumeList(self):
    storage.PROC_MOUNTS = 'testdata/storage/proc.mounts'
    service = storage.StorageServiceLinux26()
    volumes = service.LogicalVolumeList
    self.assertEqual(len(volumes), 3)
    expectedFs = {'/': 'X_GOOGLE-COM_squashfs',
                  '/foo': 'X_GOOGLE-COM_ubifs',
                  '/tmp': 'X_GOOGLE-COM_tmpfs'}
    for vol in volumes.values():
      t = OsStatVfs(vol.Name)
      self.assertEqual(vol.Status, 'Online')
      self.assertTrue(vol.Enable)
      self.assertEqual(vol.FileSystem, expectedFs[vol.Name])
      self.assertEqual(vol.Capacity, t.f_bsize * t.f_blocks)
      self.assertEqual(vol.UsedSpace, t.f_bsize * (t.f_blocks - t.f_bavail))

  def testCapabilitiesNone(self):
    storage.PROC_FILESYSTEMS = 'testdata/storage/proc.filesystems'
    cap = storage.CapabilitiesNoneLinux26()
    cap.ValidateExports()
    self.assertFalse(cap.FTPCapable)
    self.assertFalse(cap.HTTPCapable)
    self.assertFalse(cap.HTTPSCapable)
    self.assertFalse(cap.HTTPWritable)
    self.assertFalse(cap.SFTPCapable)
    self.assertEqual(cap.SupportedNetworkProtocols, '')
    self.assertEqual(cap.SupportedRaidTypes, '')
    self.assertFalse(cap.VolumeEncryptionCapable)

  def testCapabilitiesNoneFsTypes(self):
    storage.PROC_FILESYSTEMS = 'testdata/storage/proc.filesystems'
    cap = storage.CapabilitiesNoneLinux26()
    self.assertEqual(cap.SupportedFileSystemTypes,
                     'ext2,ext3,ext4,FAT32,X_GOOGLE-COM_iso9660,'
                     'X_GOOGLE-COM_squashfs,X_GOOGLE-COM_udf')

  def testPhysicalMediumName(self):
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertEqual(pm.Name, 'sda')
    pm.Name = 'sdb'
    self.assertEqual(pm.Name, 'sdb')

  def testPhysicalMediumFields(self):
    storage.SMARTCTL = 'testdata/storage/smartctl'
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertEqual(pm.Vendor, 'vendor_name')
    self.assertEqual(pm.Model, 'model_name')
    self.assertEqual(pm.SerialNumber, 'serial_number')
    self.assertEqual(pm.FirmwareVersion, 'firmware_version')
    self.assertTrue(tr.cwmpbool.parse(pm.SMARTCapable))
    self.assertEqual(pm.Health, 'OK')
    self.assertFalse(pm.Removable)

  def testNotSmartCapable(self):
    storage.SMARTCTL = 'testdata/storage/smartctl_disabled'
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertFalse(tr.cwmpbool.parse(pm.SMARTCapable))

  def testHealthFailing(self):
    storage.SMARTCTL = 'testdata/storage/smartctl_healthfail'
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertEqual(pm.Health, 'Failing')

  def testHealthError(self):
    storage.SMARTCTL = 'testdata/storage/smartctl_healtherr'
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertEqual(pm.Health, 'Error')

  def testPhysicalMediumVendorATA(self):
    storage.SYS_BLOCK = 'testdata/storage/sys/block_ATA'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    # vendor 'ATA' is suppressed, as it is useless
    self.assertEqual(pm.Vendor, '')

  def testCapacity(self):
    storage.SYS_BLOCK = 'testdata/storage/sys/block'
    pm = storage.PhysicalMediumFixedDiskLinux26('sda')
    self.assertEqual(pm.Capacity, 512)


if __name__ == '__main__':
  unittest.main()
