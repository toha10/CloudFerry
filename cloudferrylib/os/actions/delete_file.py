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

from fabric.api import run, settings, env
from cloudferrylib.base.action import action
from cloudferrylib.utils import forward_agent
from cloudferrylib.utils import utils as utl
import copy


class DeleteFile(action.Action):
    def __init__(self, init, filetype = utl.DIFF_BODY):
        super(DeleteFile, self).__init__(init)
        self.filetype = filetype

    def run(self, info=None, **kwargs):
        info = copy.deepcopy(info)

        if self.filetype not in (utl.DIFF_BODY, utl.EPHEMERAL_BODY):
            raise TypeError("You need to pass only diff or ephemeral disk type")

        for instance in info[utl.INSTANCES_TYPE].values():
            host = instance[self.filetype]['host_src']
            path = instance[self.filetype]['path_src']
            self.delete_file(host=host, filepath=path)

        return {}

    @staticmethod
    def delete_file(host, filepath):
        with settings(host_string=host):
            with forward_agent(env.key_filename):
                run("rm -f %s" % filepath)
