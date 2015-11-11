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


from cloudferrylib.base.action import action
from cloudferrylib.utils import utils as utl
import copy
INSTANCES = 'instances'
DIFF = 'diff'

PATH_DST = 'path_dst'
HOST_DST = 'host_dst'
CUSTOM = 'custom'


class MapComputeInfo(action.Action):

    def run(self, info=None, **kwargs):

        new_compute_info = copy.deepcopy(info)

        src_compute = self.src_cloud.resources[utl.COMPUTE_RESOURCE]
        dst_compute = self.dst_cloud.resources[utl.COMPUTE_RESOURCE]

        src_flavors_dict = \
            {flavor.id: flavor.name for flavor in src_compute.get_flavor_list(is_public=None)}

        dst_flavors_dict = \
            {flavor.name: flavor.id for flavor in dst_compute.get_flavor_list(is_public=None)}

        for instance_id, instance in new_compute_info[utl.INSTANCES_TYPE].iteritems():
            _instance = instance['instance']
            flavor_name = src_flavors_dict[_instance['flavor_id']]
            flavors_map = self.src_cloud.cloud_config.migrate.instances_flavor_map
            if flavors_map:
                if flavor_name in flavors_map:
                    flavor_name = flavors_map[flavor_name]
            if self.src_cloud.cloud_config.migrate.custom_flavors:
                flavor_name = CUSTOM + "-" + flavor_name
            _instance['flavor_id'] = dst_flavors_dict[flavor_name]
            path_dst = "%s/%s" % (self.dst_cloud.cloud_config.cloud.temp, "temp%s_base" % instance_id)
            instance[DIFF][PATH_DST] = path_dst
            instance[DIFF][HOST_DST] = self.dst_cloud.getIpSsh()
        return {
            'info': new_compute_info
        }
