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


DIFF = 'diff'
HOST = 'host'
PATH = 'path'
BOOT_VOLUME = 'boot_volume'
ID = 'id'


class MapBootVolToDiff(action.Action):

    def run(self, info=None, **kwargs):
        info = copy.deepcopy(info)
        dst_storage = self.dst_cloud.resources[utl.STORAGE_RESOURCE]

        for instance_id, _instance in info[utl.INSTANCES_TYPE].iteritems():
            instance = _instance[utl.INSTANCE_BODY]
            boot_volume_id = instance[BOOT_VOLUME][ID]
            boot_volume_info = dst_storage.read_info(id=boot_volume_id)[utl.VOLUMES_TYPE][boot_volume_id]
            boot_volume = boot_volume_info[utl.VOLUME_BODY]
            boot_volume_host = boot_volume[HOST]
            boot_volume_path = boot_volume[PATH]
            _instance[DIFF][utl.HOST_DST] = boot_volume_host
            _instance[DIFF][utl.PATH_DST] = boot_volume_path

        return {
            'info': info
        }
