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

SNAPSHOT_PREFIX = 'snapshot_'
ACTIVE_STATE = 'active'
ID = 'id'
NAME = 'name'

class CreateSnapshot(action.Action):

    def run(self, info=None, **kwargs):

        info = copy.deepcopy(info)
        compute_resource = self.cloud.resources[utl.COMPUTE_RESOURCE]
        image_resource = self.cloud.resources[utl.IMAGE_RESOURCE]

        for instance_id, instance in info[utl.INSTANCES_TYPE].iteritems():
            snapshot_name = SNAPSHOT_PREFIX + instance[utl.INSTANCE_BODY][NAME]
            snapshot_id = compute_resource.create_snapshot(instance_id,
                                                           snapshot_name)
            image_resource.wait_for_status(snapshot_id, ACTIVE_STATE)
            info[utl.INSTANCES_TYPE][instance_id][SNAPSHOT_PREFIX + ID] = snapshot_id


        return {
            'info': info
        }
