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
import json
import time

from fabric.api import run
from fabric.api import settings

from glanceclient.v1 import client as glance_client

from cloudferrylib.base import image
from cloudferrylib.utils import file_like_proxy
from cloudferrylib.utils import utils as utl
from cloudferrylib.utils import timeout_exception


LOG = utl.get_log(__name__)


class GlanceImage(image.Image):

    """
    The main class for working with Openstack Glance Image Service.

    """
    def __init__(self, config, cloud):
        self.config = config
        self.host = config.cloud.host
        self.cloud = cloud
        self.identity_client = cloud.resources['identity']
        self.glance_client = self.proxy(self.get_client(), config)
        super(GlanceImage, self).__init__(config)

    def get_client(self):

        """ Getting glance client """

        endpoint_glance = self.identity_client.get_endpoint_by_service_name(
            'glance')
        return glance_client.Client(
            endpoint=endpoint_glance,
            token=self.identity_client.get_auth_token_from_user(),
            insecure=self.config.cloud.insecure_ssl)

    def get_image_list(self):
        return self.glance_client.images.list()

    def create_image(self, **kwargs):
        return self.glance_client.images.create(**kwargs)

    def delete_image(self, image_id):
        self.glance_client.images.delete(image_id)

    def get_image_by_id(self, image_id):
        for glance_image in self.get_image_list():
            if glance_image.id == image_id:
                return glance_image

    def get_image_by_name(self, image_name):
        for glance_image in self.get_image_list():
            if glance_image.name == image_name:
                return glance_image

    def get_img_id_list_by_checksum(self, checksum):
        l = []
        for glance_image in self.get_image_list():
            if glance_image.checksum == checksum:
                l.append(glance_image.id)
        return l

    def get_image(self, im):
        """ Get image by id or name. """

        for glance_image in self.get_image_list():
            if im in (glance_image.name, glance_image.id):
                return glance_image

    def get_image_status(self, image_id):
        return self.get_image_by_id(image_id).status

    def get_ref_image(self, image_id):
        return self.glance_client.images.data(image_id)._resp

    def get_image_checksum(self, image_id):
        return self.get_image_by_id(image_id).checksum

    @staticmethod
    def convert(glance_image, cloud):
        """Convert OpenStack Glance image object to CloudFerry object.

        :param glance_image:    Direct OS Glance image object to convert,
        :param cloud:           Cloud object.
        """
        identity_res = cloud.resources[utl.IDENTITY_RESOURCE]
        get_tenant_name = identity_res.get_tenants_func()

        resource = cloud.resources[utl.IMAGE_RESOURCE]
        gl_image = {
            'id': glance_image.id,
            'size': glance_image.size,
            'name': glance_image.name,
            'checksum': glance_image.checksum,
            'container_format': glance_image.container_format,
            'disk_format': glance_image.disk_format,
            'is_public': glance_image.is_public,
            'owner_name': get_tenant_name(glance_image.owner),
            'min_ram': glance_image.min_ram,
            'protected': glance_image.protected,
            'resource': resource,
            'properties': ({
                'image_type': glance_image.properties['image_type']}
                if 'image_type' in glance_image.properties
                else glance_image.properties)
        }

        return gl_image

    def read_info(self, **kwargs):
        """Get info about images or specified image.

        :param image_id: Id of specified image
        :param image_name: Name of specified image
        :param images_list: List of specified images
        :param images_list_meta: Tuple of specified images with metadata in
                                 format [(image, meta)]
        :rtype: Dictionary with all necessary images info
        """

        info = {'images': {}}

        if kwargs.get('image_id'):
            glance_image = self.get_image_by_id(kwargs['image_id'])
            info = self.make_image_info(glance_image, info)

        elif kwargs.get('image_name'):
            glance_image = self.get_image_by_name(kwargs['image_name'])
            info = self.make_image_info(glance_image, info)

        elif kwargs.get('images_list'):
            for im in kwargs['images_list']:
                glance_image = self.get_image(im)
                info = self.make_image_info(glance_image, info)

        elif kwargs.get('images_list_meta'):
            for (im, meta) in kwargs['images_list_meta']:
                glance_image = self.get_image(im)
                info = self.make_image_info(glance_image, info)
                info['images'][glance_image.id]['meta'] = meta

        else:
            for glance_image in self.get_image_list():
                info = self.make_image_info(glance_image, info)

        return info

    def make_image_info(self, glance_image, info):
        if glance_image:
            gl_image = self.convert(glance_image, self.cloud)

            info['images'][glance_image.id] = {'image': gl_image,
                                               'meta': {},
                                               }
        else:
            LOG.error('Image has not been found')

        return info

    def deploy(self, info, callback=None):
        info = copy.deepcopy(info)
        new_info = {'images': {}}
        migrate_images_list = []
        empty_image_list = {}
        for image_id_src, gl_image in info['images'].iteritems():
            if gl_image['image']:
                dst_img_checksums = {x.checksum: x for x in
                                     self.get_image_list()}
                dst_img_names = [x.name for x in self.get_image_list()]
                checksum_current = gl_image['image']['checksum']
                name_current = gl_image['image']['name']
                meta = gl_image['meta']
                if checksum_current in dst_img_checksums and (
                        name_current) in dst_img_names:
                    migrate_images_list.append(
                        (dst_img_checksums[checksum_current], meta))
                    continue
                tenant_id = \
                    self.identity_client.get_tenant_id_by_name(gl_image['image']['owner_name'])
                migrate_image = self.create_image(
                    name=gl_image['image']['name'],
                    container_format=gl_image['image']['container_format'],
                    disk_format=gl_image['image']['disk_format'],
                    is_public=gl_image['image']['is_public'],
                    owner=tenant_id,
                    min_ram=gl_image['image']['min_ram'],
                    protected=gl_image['image']['protected'],
                    size=gl_image['image']['size'],
                    properties=gl_image['image']['properties'],
                    data=file_like_proxy.FileLikeProxy(
                        gl_image['image'],
                        callback,
                        self.config['migrate']['speed_limit']))
                migrate_images_list.append((migrate_image, meta))
            else:
                empty_image_list[image_id_src] = gl_image
        if migrate_images_list:
            im_name_list = [(im.name, meta) for (im, meta) in
                            migrate_images_list]
            new_info = self.read_info(images_list_meta=im_name_list)
        new_info['images'].update(empty_image_list)
        return new_info

    def wait_for_status(self, id_res, status):
        limit_retry = self.config.image.wait_for_status_retries
        retry_interval = self.config.image.wait_for_status_interval
        if limit_retry <= 0:
            LOG.warn("Treating negative or zero config value %s "
                     "for 'wait_for_status_retries' of image service."
                     % limit_retry)
            limit_retry = 60
        if retry_interval <= 0:
            LOG.warn("Treating negative or zero config value %s "
                     "for 'wait_for_status_interval' of image service."
                     % retry_interval)
            retry_interval = 3
        count = 0
        getter = self.glance_client.images
        while getter.get(id_res).status.lower() != status.lower():
            time.sleep(retry_interval)
            count += 1
            if count > limit_retry:
                raise timeout_exception.TimeoutException(
                    getter.get(id_res).status.lower(), status, "Timeout exp")

    def patch_image(self, backend_storage, image_id):
        if backend_storage == 'ceph':
            image_from_glance = self.get_image_by_id(image_id)
            with settings(host_string=self.cloud.getIpSsh()):
                out = json.loads(
                    run("rbd -p images info %s --format json" % image_id))
                image_from_glance.update(size=out["size"])
