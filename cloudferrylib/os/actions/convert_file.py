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


IMAGE = 'image'
EPHEMERAL = 'ephemeral'
DIFF = 'diff'


class ConvertFile(action.Action):
    def __init__(self, init, filetype = IMAGE, cloud=None):
        super(ConvertFile, self).__init__(init, cloud)
        self.filetype = filetype

    def run(self, info=None, **kwargs):
        info = copy.deepcopy(info)

        if self.filetype == IMAGE:
            self.convert_image(info=info)
        elif self.filetype == utl.DISK:
            self.convert_disk(info=info, disk_type=DIFF)
        elif self.filetype == utl.DISK_EPHEM:
            self.convert_disk(info=info, disk_type=utl.DISK_EPHEM)

        return {
            'info': info
        }

    def convert_disk(self, info, disk_type=DIFF):
        if disk_type not in (DIFF, EPHEMERAL):
            raise TypeError("You need to pass only diff or ephemeral disk types")
        for instance_id, instance in info[utl.INSTANCES_TYPE].iteritems():
            host = instance[disk_type]['host_src']
            path = instance[disk_type]['path_src']
            new_path = self.convert_file_to_raw(host, path)
            instance[disk_type]['path_src'] = new_path

    def convert_image(self, info):
        cfg = self.cloud.cloud_config.cloud
        image_res = self.cloud.resources[utl.IMAGE_RESOURCE]
        if image_res.config.image.convert_to_raw:
            return {}
        for instance_id, instance in info[utl.INSTANCES_TYPE].iteritems():
            image_id = info[utl.INSTANCES_TYPE][instance_id][utl.INSTANCE_BODY]['image_id']
            images = image_res.read_info(image_id=image_id)
            image = images[utl.IMAGES_TYPE][image_id]
            disk_format = image[utl.IMAGE_BODY]['disk_format']
            base_file = "%s/%s" % (cfg.temp, "temp%s_base" % instance_id)
            if disk_format.lower() != utl.RAW:
                self.convert_file_to_raw(cfg.host, base_file, move_to_orig=True)


    @staticmethod
    def convert_file_to_raw(host, filepath, move_to_orig=False):
        with settings(host_string=host):
            with forward_agent(env.key_filename):
                run("qemu-img convert -O raw %s %s.tmp" %
                    (filepath, filepath))
                dest_filepath = filepath + ".tmp"
                if move_to_orig:
                    run("mv -f %s.tmp %s" % (filepath, filepath))
                    dest_filepath = filepath
        return dest_filepath
