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


SNAPSHOT_ID = 'snapshot_id'


class GetSnapshotsIfo(action.Action):
    def __init__(self, init, cloud=None):
        super(GetSnapshotsIfo, self).__init__(init, cloud)

    def run(self, info=None, **kwargs):

        info = copy.deepcopy(info)
        image_resource = self.cloud.resources[utl.IMAGE_RESOURCE]

        images_info = {}
        for instance_id in info[utl.INSTANCES_TYPE]:
            snapshot_id = info[utl.INSTANCES_TYPE][instance_id][SNAPSHOT_ID]
            images_info = image_resource.read_info(image_id=snapshot_id)

        return {
            'images_info': images_info
        }
