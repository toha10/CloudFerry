# Copyright 2014: Mirantis Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import mock

from novaclient.v1_1 import client as nova_client
from oslotest import mockpatch
import cfglib

from cloudferrylib.os.compute import nova_compute
from cloudferrylib.utils import utils
from tests import test


FAKE_CONFIG = utils.ext_dict(
    cloud=utils.ext_dict({'user': 'fake_user',
                          'password': 'fake_password',
                          'tenant': 'fake_tenant',
                          'auth_url': 'http://1.1.1.1:35357/v2.0/'}),
    mysql=utils.ext_dict({'host': '1.1.1.1'}),
    migrate=utils.ext_dict({'speed_limit': '10MB',
                            'retry': '7',
                            'time_wait': 5}))


class NovaComputeTestCase(test.TestCase):
    def setUp(self):
        super(NovaComputeTestCase, self).setUp()

        self.mock_client = mock.MagicMock()
        self.nc_patch = mockpatch.PatchObject(nova_client, 'Client',
                                              new=self.mock_client)
        self.useFixture(self.nc_patch)

        self.identity_mock = mock.Mock()

        self.fake_cloud = mock.Mock()
        self.fake_cloud.resources = dict(identity=self.identity_mock)

        with mock.patch(
                'cloudferrylib.os.compute.nova_compute.mysql_connector'):
            self.nova_client = nova_compute.NovaCompute(FAKE_CONFIG,
                                                        self.fake_cloud)

        self.fake_instance_0 = mock.Mock()
        self.fake_instance_1 = mock.Mock()
        self.fake_instance_0.id = 'fake_instance_id'

        self.fake_getter = mock.Mock()

        self.fake_flavor_0 = mock.Mock()
        self.fake_flavor_1 = mock.Mock()

    def test_get_nova_client(self):
        # To check self.mock_client call only from this test method
        self.mock_client.reset_mock()

        client = self.nova_client.get_client()

        self.mock_client.assert_called_once_with('fake_user', 'fake_password',
                                                 'fake_tenant',
                                                 'http://1.1.1.1:35357/v2.0/')
        self.assertEqual(self.mock_client(), client)

    def test_create_instance(self):
        self.mock_client().servers.create.return_value = self.fake_instance_0

        instance_id = self.nova_client.create_instance(name='fake_instance',
                                                       image='fake_image',
                                                       flavor='fake_flavor')

        self.assertEqual('fake_instance_id', instance_id)

    def test_get_instances_list(self):
        fake_instances_list = [self.fake_instance_0, self.fake_instance_1]
        self.mock_client().servers.list.return_value = fake_instances_list

        instances_list = self.nova_client.get_instances_list()

        test_args = {'marker': None,
                     'detailed': True,
                     'limit': None,
                     'search_opts': None}

        cfglib.init_config()
        instances_list = self.nova_client.get_instances_list(**test_args)

        self.mock_client().servers.list.assert_called_once_with(**test_args)
        self.assertEqual(fake_instances_list, instances_list)

    def test_get_status(self):
        self.fake_getter.get('fake_id').status = 'start'

        status = self.nova_client.get_status(self.fake_getter, 'fake_id')

        self.assertEqual('start', status)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_active(self, mock_get, mock_sleep):
        mock_get.return_value = 'shutoff'
        self.nova_client.change_status('active', instance=self.fake_instance_0)
        self.fake_instance_0.start.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_shutoff(self, mock_get, mock_sleep):
        mock_get.return_value = 'active'
        self.nova_client.change_status('shutoff',
                                       instance=self.fake_instance_0)
        self.fake_instance_0.stop.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_resume(self, mock_get, mock_sleep):
        mock_get.return_value = 'suspend'
        self.nova_client.change_status('active', instance=self.fake_instance_0)
        self.fake_instance_0.resume.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_paused(self, mock_get, mock_sleep):
        mock_get.return_value = 'active'
        self.nova_client.change_status('paused', instance=self.fake_instance_0)
        self.fake_instance_0.pause.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_unpaused(self, mock_get, mock_sleep):
        mock_get.return_value = 'paused'
        self.nova_client.change_status('active',
                                       instance=self.fake_instance_0)
        self.fake_instance_0.unpause.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    @mock.patch('cloudferrylib.os.compute.nova_compute.time.sleep')
    @mock.patch('cloudferrylib.os.compute.nova_compute.NovaCompute.get_status')
    def test_change_status_suspend(self, mock_get, mock_sleep):
        mock_get.return_value = 'active'
        self.nova_client.change_status('suspend',
                                       instance=self.fake_instance_0)
        self.fake_instance_0.suspend.assert_called_once_with()
        mock_sleep.assert_called_with(2)

    def test_change_status_same(self):
        self.mock_client().servers.get('fake_instance_id').status = 'stop'

        self.nova_client.change_status('stop', instance=self.fake_instance_0)
        self.assertFalse(self.fake_instance_0.stop.called)

    def test_get_flavor_from_id(self):
        self.mock_client().flavors.get.return_value = self.fake_flavor_0

        flavor = self.nova_client.get_flavor_from_id('fake_flavor_id')

        self.assertEqual(self.fake_flavor_0, flavor)

    def test_get_flavor_list(self):
        fake_flavor_list = [self.fake_flavor_0, self.fake_flavor_1]
        self.mock_client().flavors.list.return_value = fake_flavor_list

        flavor_list = self.nova_client.get_flavor_list()

        self.assertEqual(fake_flavor_list, flavor_list)

    def test_create_flavor(self):
        self.mock_client().flavors.create.return_value = self.fake_flavor_0

        flavor = self.nova_client.create_flavor()

        self.assertEqual(self.fake_flavor_0, flavor)

    def test_delete_flavor(self):
        self.nova_client.delete_flavor('fake_fl_id')

        self.mock_client().flavors.delete.assert_called_once_with('fake_fl_id')

    def test_nothing_is_filtered_if_skip_down_hosts_option_not_set(self):
        cfglib.init_config()
        cfglib.CONF.migrate.skip_down_hosts = False
        self.fake_instance_0.host = 'host1'
        self.fake_instance_1.host = 'host2'

        hosts_down = ['host1', 'host2', 'host3']
        instances = [self.fake_instance_0, self.fake_instance_1]

        filtered = nova_compute.filter_down_hosts(hosts_down, instances)

        self.assertEqual(filtered, instances)

    def test_down_hosts_has_no_hosts_in_up_state(self):
        def service(hostname, state):
            s = mock.Mock()
            s.host = hostname
            s.state = state
            return s

        num_up_services = 5
        num_down_services = 10
        services = [service('uphost%d' % i, 'up')
                    for i in xrange(num_up_services)]
        services.extend([service('downhost%d' % i, 'down')
                         for i in xrange(num_down_services)])
        client = mock.Mock()
        client.services.list.return_value = services

        hosts = nova_compute.down_hosts(client)

        self.assertEqual(len(hosts), num_down_services)

    def test_down_hosts_are_filtered_if_config_option_is_set(self):
        def instance(hostname):
            inst = mock.Mock()
            setattr(inst, nova_compute.INSTANCE_HOST_ATTRIBUTE, hostname)
            return inst

        num_instances_up = 5
        num_hosts_down = 10
        hosts_down = ['downhost%d' % i for i in xrange(num_hosts_down)]
        instances = [instance('host%d' % i) for i in xrange(num_instances_up)]
        instances.extend([instance(host_down) for host_down in hosts_down])
        cfglib.init_config()
        cfglib.CONF.migrate.skip_down_hosts = True

        filtered = nova_compute.filter_down_hosts(
            hosts_down=hosts_down, elements=instances,
            hostname_attribute=nova_compute.INSTANCE_HOST_ATTRIBUTE)

        self.assertEqual(len(filtered), num_instances_up)
