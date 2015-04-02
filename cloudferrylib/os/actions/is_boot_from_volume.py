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
from cloudferrylib.base.action import action
from cloudferrylib.utils import utils as utl


DEFAULT = 0
DIRECT_FLOW = 1
BOOT_MODE = 'boot_mode'


class IsBootFromVolume(action.Action):

    def run(self, info=None, **kwargs):
        self.set_next_path(DEFAULT)
        info = copy.deepcopy(info)
        instance_boot = info[utl.INSTANCES_TYPE].values()[0][utl.INSTANCE_BODY][BOOT_MODE]
        if instance_boot == utl.BOOT_FROM_VOLUME:
            self.set_next_path(DIRECT_FLOW)
        return {
        }
