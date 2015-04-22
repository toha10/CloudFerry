# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.


import copy
import time
from sqlalchemy import exc

from novaclient.v1_1 import client as nova_client

from cloudferrylib.base import compute
from cloudferrylib.utils import mysql_connector
from cloudferrylib.utils import timeout_exception
from cloudferrylib.utils import utils as utl


LOG = utl.get_log(__name__)


DISK = "disk"
LOCAL = ".local"
LEN_UUID_INSTANCE = 36
INTERFACES = "interfaces"
DEFAULT_QUOTA_VALUE = -1
SNAPSHOT = 'snapshot'


class NovaCompute(compute.Compute):
    """The main class for working with Openstack Nova Compute Service. """

    def __init__(self, config, cloud):
        super(NovaCompute, self).__init__()
        self.config = config
        self.cloud = cloud
        self.identity = cloud.resources['identity']
        self.mysql_connector = mysql_connector.MysqlConnector(config.mysql,
                                                              'nova')
        self.nova_client = self.proxy(self.get_client(), config)

    def get_client(self, params=None):
        """Getting nova client. """

        params = self.config if not params else params

        return nova_client.Client(params.cloud.user,
                                  params.cloud.password,
                                  params.cloud.tenant,
                                  params.cloud.auth_url)

    def _read_info_quotas(self, info):
        user_quotas_cmd = ("SELECT user_id, project_id, resource, "
                           "hard_limit FROM project_user_quotas WHERE "
                           "deleted = 0")
        for quota in self.mysql_connector.execute(user_quotas_cmd):
            info['user_quotas'].append(
                {'quota': {'user_id': quota[0],
                           'project_id': quota[1],
                           'resource': quota[2],
                           'hard_limit': quota[3]},
                 'meta': {}})

        project_quotas_cmd = ("SELECT project_id, resource, hard_limit "
                              "FROM quotas WHERE deleted = 0")
        for quota in self.mysql_connector.execute(project_quotas_cmd):
            info['project_quotas'].append(
                {'quota': {'project_id': quota[0],
                           'resource': quota[1],
                           'hard_limit': quota[2]},
                 'meta': {}})

    def _read_info_keypairs(self):
        keypairs_cmd = ("SELECT name, user_id, fingerprint, "
                        "public_key FROM key_pairs WHERE "
                        "deleted = 0")
        keypairs_info = []

        for keypair in self.mysql_connector.execute(keypairs_cmd):
            keypairs_info.append(
                {'keypair': {'name': keypair[0],
                             'user_id': keypair[1],
                             'fingerprint': keypair[2],
                             'public_key': keypair[3]},
                 'meta': {}})

        return keypairs_info

    def _read_info_resources(self, **kwargs):
        """
        Read info about compute resources except instances from the cloud.
        """
        info = {'keypairs': [],
                'flavors': {},
                'user_quotas': [],
                'project_quotas': []}

        info['keypairs'] = self._read_info_keypairs()

        for flavor in self.get_flavor_list(is_public=None):
            info['flavors'][flavor.id] = self.convert(self.nova_client,
                                                      flavor, cloud=self.cloud)

        if self.config.migrate.migrate_quotas:
            info['project_quotas'], info['user_quotas'] = \
                self._read_info_quotas_api()

        return info

    def _read_info_quotas_api(self):
        service_tenant_id = \
            self.identity.get_tenant_id_by_name(self.config.cloud.service_tenant)
        tenant_ids = [tenant.id for tenant in self.identity.get_tenants_list()
                      if tenant.id != service_tenant_id]
        user_ids = [user.id for user in self.identity.get_users_list()
                    if user.tenantId != service_tenant_id]
        project_quotas = list()
        user_quotas = list()

        for tenant_id in tenant_ids:
            project_quota = self.get_quotas(tenant_id=tenant_id)
            project_quota_info = self.convert(self.nova_client, project_quota)
            project_quota_info['tenant_id'] = tenant_id
            project_quotas.append(project_quota_info)
            for user_id in user_ids:
                user_quota = self.get_quotas(tenant_id=tenant_id, user_id=user_id)
                user_quota_info = self.convert(self.nova_client, user_quota)
                user_quota_info['tenant_id'] = tenant_id
                user_quota_info['user_id'] = user_id
                user_quotas.append(user_quota_info)

        return project_quotas, user_quotas

    def read_info(self, target='instances', **kwargs):
        """
        Read info from cloud.

        :param target: Target objects to get info about. Possible values:
                       "instances" or "resources",
        :param search_opts: Search options to filter out servers (optional).
        """

        if target == 'resources':
            return self._read_info_resources(**kwargs)

        if target != 'instances':
            raise ValueError('Only "resources" or "instances" values allowed')

        search_opts = kwargs.get('search_opts')
        info = {'instances': {}}

        for instance in self.get_instances_list(search_opts=search_opts):
            info['instances'][instance.id] = self.convert(self.nova_client,
                                                          instance,
                                                          self.config,
                                                          self.cloud)

        return info

    @staticmethod
    def convert_instance(client, instance, cfg, cloud):
        identity_res = cloud.resources[utl.IDENTITY_RESOURCE]
        compute_res = cloud.resources[utl.COMPUTE_RESOURCE]

        instance_name = getattr(instance, "OS-EXT-SRV-ATTR:instance_name")
        instance_host = getattr(instance, 'OS-EXT-SRV-ATTR:host')

        get_tenant_name = identity_res.get_tenants_func()

        security_groups = []
        for security_group in instance.security_groups:
            security_groups.append(security_group['name'])

        interfaces = compute_res.get_networks(instance)

        volumes = [{'id': v.id,
                    'num_device': i,
                    'device': v.device} for i, v in enumerate(
                        compute_res.nova_client.volumes.get_server_volumes(
                            instance.id))]

        is_ephemeral = compute_res.get_flavor_from_id(
            instance.flavor['id']).ephemeral > 0

        is_ceph = cfg.compute.backend.lower() == utl.CEPH
        direct_transfer = cfg.migrate.direct_compute_transfer

        if direct_transfer:
            ext_cidr = cfg.cloud.ext_cidr
            host = utl.get_ext_ip(ext_cidr,
                                  cloud.getIpSsh(),
                                  instance_host)
        elif is_ceph:
            host = cfg.compute.host_eph_drv
        else:
            host = instance_host

        instance_block_info = utl.get_libvirt_block_info(
            instance_name,
            cloud.getIpSsh(),
            instance_host)

        ephemeral_path = {
            'path_src': None,
            'path_dst': None,
            'host_src': host,
            'host_dst': None
        }

        if is_ephemeral:
            ephemeral_path['path_src'] = utl.get_disk_path(
                instance,
                instance_block_info,
                is_ceph_ephemeral=is_ceph,
                disk=DISK+LOCAL)

        diff = {
            'path_src': None,
            'path_dst': None,
            'host_src': host,
            'host_dst': None
        }

        if instance.image:
            diff['path_src'] = utl.get_disk_path(
                instance,
                instance_block_info,
                is_ceph_ephemeral=is_ceph)

        disk_size = client.flavors.get(instance.flavor['id']).disk

        inst = {'instance': {'name': instance.name,
                             'instance_name': instance_name,
                             'id': instance.id,
                             'tenant_id': instance.tenant_id,
                             'tenant_name': get_tenant_name(
                                 instance.tenant_id),
                             'status': instance.status,
                             'flavor_id': instance.flavor['id'],
                             'image_id': instance.image[
                                 'id'] if instance.image else None,
                             'boot_mode': (utl.BOOT_FROM_IMAGE
                                           if instance.image
                                           else utl.BOOT_FROM_VOLUME),
                             'key_name': instance.key_name,
                             'availability_zone': getattr(
                                 instance,
                                 'OS-EXT-AZ:availability_zone'),
                             'security_groups': security_groups,
                             'boot_volume': copy.deepcopy(
                                 volumes[0]) if volumes else None,
                             'interfaces': interfaces,
                             'host': instance_host,
                             'is_ephemeral': is_ephemeral,
                             'volumes': volumes,
                             'disk_size': disk_size
                             },
                'ephemeral': ephemeral_path,
                'diff': diff,
                'meta': {},
                }

        return inst

    @staticmethod
    def convert_resources(compute_obj, cloud):

        if isinstance(compute_obj, nova_client.flavors.Flavor):

            compute_res = cloud.resources[utl.COMPUTE_RESOURCE]
            tenants = None

            if not compute_obj.is_public:
                flavor_access_list = compute_res.get_flavor_access_list(compute_obj.id)
                tenants = [flv_acc.tenant_id for flv_acc in flavor_access_list]

            return {'flavor': {'name': compute_obj.name,
                               'ram': compute_obj.ram,
                               'vcpus': compute_obj.vcpus,
                               'disk': compute_obj.disk,
                               'ephemeral': compute_obj.ephemeral,
                               'swap': compute_obj.swap,
                               'rxtx_factor': compute_obj.rxtx_factor,
                               'is_public': compute_obj.is_public,
                               'tenants': tenants},
                    'meta': {}}
        elif isinstance(compute_obj, nova_client.quotas.QuotaSet):
            return {'quota': {'cores': compute_obj.cores,
                              'fixed_ips': compute_obj.fixed_ips,
                              'floating_ips': compute_obj.floating_ips,
                              'instances': compute_obj.instances,
                              'key_pairs': compute_obj.key_pairs,
                              'ram': compute_obj.ram,
                              'security_group_rules': compute_obj.security_group_rules,
                              'security_groups': compute_obj.security_groups,
                              'injected_file_content_bytes': compute_obj.injected_file_content_bytes,
                              'injected_file_path_bytes': compute_obj.injected_file_path_bytes,
                              'injected_files': compute_obj.injected_files,
                              'metadata_items': compute_obj.metadata_items},
                    'meta': {}}

    @staticmethod
    def convert(client, obj, cfg=None, cloud=None):
        res_tuple = (nova_client.flavors.Flavor,
                     nova_client.quotas.QuotaSet)

        if isinstance(obj, nova_client.servers.Server):
            return NovaCompute.convert_instance(client, obj, cfg, cloud)
        elif isinstance(obj, res_tuple):
            return NovaCompute.convert_resources(obj, cloud)

        LOG.error('NovaCompute converter has received incorrect value. Please '
                  'pass to it only instance, flavor or quota objects.')
        return None

    def _deploy_resources(self, info, **kwargs):
        """
        Deploy compute resources except instances to the cloud.

        :param info: Info about compute resources to deploy,
        :param identity_info: Identity info.
        """

        identity_info = kwargs.get('identity_info')

        tenant_map = {tenant['tenant']['id']: tenant['meta']['new_id'] for
                      tenant in identity_info['tenants']}
        user_map = {user['user']['id']: user['meta']['new_id'] for user in
                    identity_info['users']}

        self._deploy_key_pairs(info['keypairs'], user_map)
        self._deploy_flavors(info['flavors'], tenant_map)
        if self.config['migrate']['migrate_quotas']:
            self._deploy_quotas_api(info['project_quotas'], tenant_map)
            self._deploy_quotas_api(info['user_quotas'], tenant_map, user_map)

        new_info = self.read_info(target='resources')

        return new_info

    def deploy(self, info, target='instances', **kwargs):
        """
        Deploy compute resources to the cloud.

        :param target: Target objects to deploy. Possible values:
                       "instances" or "resources",
        :param identity_info: Identity info.
        """

        info = copy.deepcopy(info)

        if target == 'resources':
            info = self._deploy_resources(info, **kwargs)
        elif target == 'instances':
            info = self._deploy_instances(info)
        else:
            raise ValueError('Only "resources" or "instances" values allowed')

        return info

    def _deploy_user_quotas(self, quotas, tenant_map, user_map):
        insert_cmd = ("INSERT INTO project_user_quotas (user_id, project_id, "
                      "resource, hard_limit, deleted) VALUES ('%s', '%s', '%s'"
                      ", %s, 0)")

        update_cmd = ("UPDATE project_user_quotas SET hard_limit=%s WHERE "
                      "user_id='%s' AND project_id='%s' AND resource='%s' AND "
                      "deleted=0")

        for _quota in quotas:
            quota = _quota['quota']
            try:
                self.mysql_connector.execute(insert_cmd % (
                    user_map[quota['user_id']],
                    tenant_map[quota['project_id']],
                    quota['resource'],
                    quota['hard_limit']))
            except exc.IntegrityError as e:
                if 'Duplicate entry' in e.message:
                    self.mysql_connector.execute(update_cmd % (
                        quota['hard_limit'],
                        user_map[quota['user_id']],
                        tenant_map[quota['project_id']],
                        quota['resource'],
                    ))
                else:
                    raise

    def _deploy_project_quotas(self, quotas, tenant_map):
        insert_cmd = ("INSERT INTO quotas (project_id, resource, "
                      "hard_limit, deleted) VALUES ('%s', '%s', %s, 0)")

        update_cmd = ("UPDATE quotas SET hard_limit=%s WHERE project_id='%s' "
                      "AND resource='%s' AND deleted=0")

        for _quota in quotas:
            quota = _quota['quota']
            try:
                self.mysql_connector.execute(insert_cmd % (
                    tenant_map[quota['project_id']],
                    quota['resource'],
                    quota['hard_limit']))
            except exc.IntegrityError as e:
                if 'Duplicate entry' in e.message:
                    self.mysql_connector.execute(update_cmd % (
                        quota['hard_limit'],
                        tenant_map[quota['project_id']],
                        quota['resource'],
                    ))
                else:
                    raise

    def _deploy_key_pairs(self, key_pairs, user_map):
        insert_cmd = ("INSERT INTO key_pairs (name, user_id, "
                      "fingerprint, public_key, deleted) "
                      "VALUES ('%s', '%s', '%s', '%s', 0)")

        update_cmd = ("UPDATE key_pairs SET fingerprint='%s', "
                      "public_key='%s' WHERE name='%s' "
                      "AND user_id='%s' AND deleted=0")

        for _key_pair in key_pairs:
            key_pair = _key_pair['keypair']
            try:
                self.mysql_connector.execute(insert_cmd % (
                    key_pair['name'],
                    user_map[key_pair['user_id']],
                    key_pair['fingerprint'],
                    key_pair['public_key']))
            except exc.IntegrityError as e:
                if 'Duplicate entry' in e.message:
                    self.mysql_connector.execute(update_cmd % (
                        key_pair['fingerprint'],
                        key_pair['public_key'],
                        key_pair['name'],
                        user_map[key_pair['user_id']]
                    ))
                else:
                    raise

    def _deploy_quotas_api(self, quotas, tenant_map, user_map=None):
        for _quota in quotas:
            old_tenant_id = _quota['tenant_id']
            tenant_id = tenant_map[old_tenant_id]
            user_id = None
            if user_map:
                old_user_id = _quota['user_id']
                user_id = user_map[old_user_id]
            quota = _quota['quota']
            quota_info = dict()

            for quota_name, quota_value in quota.iteritems():
                if quota_value != DEFAULT_QUOTA_VALUE:
                    quota_info[quota_name] = quota_value

            self.update_quota(tenant_id=tenant_id, user_id=user_id, **quota_info)

    def _deploy_flavors(self, flavors, tenant_map):
        dest_flavors = {flavor.name: flavor.id for flavor in
                        self.get_flavor_list(is_public=None)}
        for flavor_id, _flavor in flavors.iteritems():
            flavor = _flavor['flavor']
            if flavor['name'] in dest_flavors:
                # _flavor['meta']['dest_id'] = dest_flavors[flavor['name']]
                _flavor['meta']['id'] = dest_flavors[flavor['name']]
                continue
            _flavor['meta']['id'] = self.create_flavor(
                name=flavor['name'],
                flavorid=flavor_id,
                ram=flavor['ram'],
                vcpus=flavor['vcpus'],
                disk=flavor['disk'],
                ephemeral=flavor['ephemeral'],
                swap=int(flavor['swap']) if flavor['swap'] else 0,
                rxtx_factor=flavor['rxtx_factor'],
                is_public=flavor['is_public']).id
            if not flavor['is_public']:
                for tenant in flavor['tenants']:
                    self.add_flavor_access(_flavor['meta']['id'],
                                           tenant_map[tenant])

    def _deploy_instances(self, info_compute):
        new_ids = {}
        nova_tenants_clients = {
            self.config['cloud']['tenant']: self.nova_client}

        params = {'user': self.config['cloud']['user'],
                  'password': self.config['cloud']['password'],
                  'tenant': self.config['cloud']['tenant'],
                  'host': self.config['cloud']['host']}

        for _instance in info_compute['instances'].itervalues():
            tenant_name = _instance['instance']['tenant_name']
            if tenant_name not in nova_tenants_clients:
                params['tenant'] = tenant_name
                nova_tenants_clients[tenant_name] = self.get_nova_client(
                    params)

        for _instance in info_compute['instances'].itervalues():
            instance = _instance['instance']
            meta = _instance['meta']
            self.nova_client = nova_tenants_clients[instance['tenant_name']]
            create_params = {'name': instance['name'],
                             'flavor': instance['flavor_id'],
                             'key_name': instance['key_name'],
                             'nics': instance['nics'],
                             'image': instance['image_id']}
            if instance['boot_mode'] == utl.BOOT_FROM_VOLUME:
                volume_id = instance['volumes'][0]['id']
                create_params["block_device_mapping_v2"] = [{
                    "source_type": "volume",
                    "uuid": volume_id,
                    "destination_type": "volume",
                    "delete_on_termination": True,
                    "boot_index": 0
                }]
                create_params['image'] = None
            if self.config.migrate.instance_convert_to_bfv:
                if instance['boot_mode'] == utl.BOOT_FROM_IMAGE:
                    create_params["block_device_mapping_v2"] = [{
                        "source_type": "image",
                        "uuid": instance['image_id'],
                        "destination_type": "volume",
                        "volume_size": instance['disk_size'],
                        "delete_on_termination": False,
                        "boot_index": 0
                    }]
                    create_params['image'] = None
            new_id = self.create_instance(**create_params)
            new_ids[new_id] = instance['id']
        self.nova_client = nova_tenants_clients[self.config['cloud']['tenant']]
        return new_ids

    def create_instance(self, **kwargs):
        return self.nova_client.servers.create(**kwargs).id

    def get_instances_list(self, detailed=True, search_opts=None,
                           marker=None,
                           limit=None):
        ids = search_opts.get('id', None) if search_opts else None
        if not ids:
            return self.nova_client.servers.list(detailed=detailed,
                                                 search_opts=search_opts,
                                                 marker=marker, limit=limit)
        else:
            if type(ids) is list:
                return [self.nova_client.servers.get(i) for i in ids]
            else:
                return [self.nova_client.servers.get(ids)]

    def get_instance(self, instance_id):
        return self.get_instances_list(search_opts={'id': instance_id})[0]

    def change_status(self, status, instance=None, instance_id=None):
        if instance_id:
            instance = self.nova_client.servers.get(instance_id)
        curr = self.get_status(self.nova_client.servers, instance.id).lower()
        will = status.lower()
        func_restore = {
            'start': lambda instance: instance.start(),
            'stop': lambda instance: instance.stop(),
            'resume': lambda instance: instance.resume(),
            'paused': lambda instance: instance.pause(),
            'unpaused': lambda instance: instance.unpause(),
            'suspend': lambda instance: instance.suspend(),
            'status': lambda status: lambda instance: self.wait_for_status(
                instance_id,
                status)
        }
        map_status = {
            'paused': {
                'active': (func_restore['unpaused'],
                           func_restore['status']('active')),
                'shutoff': (func_restore['stop'],
                            func_restore['status']('shutoff')),
                'suspend': (func_restore['unpaused'],
                            func_restore['status']('active'),
                            func_restore['suspend'],
                            func_restore['status']('suspend'))
            },
            'suspend': {
                'active': (func_restore['resume'],
                           func_restore['status']('active')),
                'shutoff': (func_restore['stop'],
                            func_restore['status']('shutoff')),
                'paused': (func_restore['resume'],
                           func_restore['status']('active'),
                           func_restore['paused'],
                           func_restore['status']('paused'))
            },
            'active': {
                'paused': (func_restore['paused'],
                           func_restore['status']('paused')),
                'suspend': (func_restore['suspend'],
                            func_restore['status']('suspend')),
                'shutoff': (func_restore['stop'],
                            func_restore['status']('shutoff'))
            },
            'shutoff': {
                'active': (func_restore['start'],
                           func_restore['status']('active')),
                'paused': (func_restore['start'],
                           func_restore['status']('active'),
                           func_restore['paused'],
                           func_restore['status']('paused')),
                'suspend': (func_restore['start'],
                            func_restore['status']('active'),
                            func_restore['suspend'],
                            func_restore['status']('suspend'))
            }
        }
        if curr != will:
            try:
                reduce(lambda res, f: f(instance), map_status[curr][will],
                       None)
            except timeout_exception.TimeoutException as e:
                return e
        else:
            return True

    def wait_for_status(self, id_obj, status):
        limit_retry = self.config.compute.wait_for_status_retries
        retry_interval = self.config.compute.wait_for_status_interval
        if limit_retry <= 0:
            LOG.warn("Treating negative or zero config value %s "
                     "for 'wait_for_status_retries' of compute service."
                     % limit_retry)
            limit_retry = 60
        if retry_interval <= 0:
            LOG.warn("Treating negative or zero config value %s "
                     "for 'wait_for_status_interval' of compute service."
                     % retry_interval)
            retry_interval = 3
        count = 0
        getter = self.nova_client.servers
        while getter.get(id_obj).status.lower() != status.lower():
            time.sleep(retry_interval)
            count += 1
            if count > limit_retry:
                raise timeout_exception.TimeoutException(
                    getter.get(id_obj).status.lower(), status, "Timeout exp")

    def get_flavor_from_id(self, flavor_id):
        return self.nova_client.flavors.get(flavor_id)

    def get_flavor_list(self, **kwargs):
        return self.nova_client.flavors.list(**kwargs)

    def create_flavor(self, **kwargs):
        return self.nova_client.flavors.create(**kwargs)

    def delete_flavor(self, flavor_id):
        self.nova_client.flavors.delete(flavor_id)

    def get_flavor_access_list(self, flavor_id):
        return self.nova_client.flavor_access.list(flavor=flavor_id)

    def add_flavor_access(self, flavor_id, tenant_id):
        self.nova_client.flavor_access.add_tenant_access(flavor_id, tenant_id)

    def get_keypair_list(self):
        return self.nova_client.keypairs.list()

    def get_keypair(self, name):
        return self.nova_client.keypairs.get(name)

    def create_keypair(self, name, public_key=None):
        return self.nova_client.keypairs.create(name, public_key)

    def get_quotas(self, tenant_id, user_id=None):
        return self.nova_client.quotas.get(tenant_id, user_id)

    def update_quota(self, tenant_id, user_id=None, **quota_items):
        return self.nova_client.quotas.update(tenant_id=tenant_id, user_id=user_id, **quota_items)

    def get_interface_list(self, server_id):
        return self.nova_client.servers.interface_list(server_id)

    def interface_attach(self, server_id, port_id, net_id, fixed_ip):
        return self.nova_client.servers.interface_attach(server_id, port_id,
                                                         net_id, fixed_ip)

    def get_status(self, getter, res_id):
        return getter.get(res_id).status

    def get_networks(self, instance):
        networks = []
        func_mac_address = self.get_func_mac_address(instance)
        for network in instance.networks.items():
            networks_info = dict(name=network[0],
                                 ip=network[1][0],
                                 mac=func_mac_address(network[1][0]))
            networks_info['floatingip'] = network[1][1] if len(
                network[1]) > 1 else None
            networks.append(networks_info)
        return networks

    def get_func_mac_address(self, instance):
        resources = self.cloud.resources
        if 'network' in resources:
            network = resources['network']
            if 'get_func_mac_address' in dir(network):
                return network.get_func_mac_address(instance)
        return self.default_detect_mac(instance)

    def default_detect_mac(self, arg):
        raise NotImplemented(
            "Not implemented yet function for detect mac address")

    def attach_volume_to_instance(self, instance, volume):
        self.nova_client.volumes.create_server_volume(
            instance['instance']['id'],
            volume['volume']['id'],
            volume['volume']['device'])

    def dissociate_floatingip(self, instance_id, floatingip):
        self.nova_client.servers.remove_floating_ip(instance_id, floatingip)

    def create_snapshot(self, instance_id, snapshot_name, metadata=None):
        return self.nova_client.servers.create_image(instance_id, snapshot_name, metadata)
