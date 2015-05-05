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

from cloudferrylib.base import objstorage
from swiftclient import client as swift_client
from cloudferrylib.utils import utils as utl


class SwiftStorage(objstorage.ObjStorage):
    """The main class for working with Object Storage Service. """

    def __init__(self, config, cloud):
        super(SwiftStorage, self).__init__()
        self.config = config
        self.cloud = cloud
        self.swift_conn = self.get_swift_conn()

    def get_swift_conn(self, params=None):
        """Getting nova client. """
        if params is None:
            params = self.config.cloud

        return swift_client.Connection(user=params.user,
                                       key=params.password,
                                       tenant_name=params.tenant,
                                       authurl=params.auth_url,
                                       auth_version="2",
                                       insecure=params.insecure_ssl)

    def read_info(self, **kwargs):
        info = {utl.OBJSTORAGE_RESOURCE:
                    {utl.CONTAINERS: {}}}
        account_info = self.get_account_info()
        info[utl.OBJSTORAGE_RESOURCE][utl.CONTAINERS] = account_info[1]
        for container_info in info[utl.OBJSTORAGE_RESOURCE][utl.CONTAINERS]:
            container_info['objects'] = self.get_container(container_info['name'])[1]
            for object_info in container_info['objects']:
                resp, object_info['data'] = self.get_object(container_info['name'],
                                                            object_info['name'])
        return info

    def deploy(self, info, **kwargs):
        for container_info in info[utl.OBJSTORAGE_RESOURCE][utl.CONTAINERS]:
            self.put_container(container_info['name'])
            for object_info in container_info['objects']:
                self.put_object(container=container_info['name'],
                                obj_name=object_info['name'],
                                content=object_info['data'],
                                content_type=object_info['content_type'])
        return info

    def get_account_info(self):
        return self.swift_conn.get_account()

    def get_container(self, container, *args):
        return self.swift_conn.get_container(container, *args)

    def get_object(self, container, obj_name, *args):
        return self.swift_conn.get_object(container, obj_name, *args)

    def put_object(self, container, obj_name, content=None, content_type=None, *args):
        return self.swift_conn.put_object(container, obj_name, content, content_type, *args)

    def put_container(self, container, *args):
        return self.swift_conn.put_container(container, *args)

    def delete_container(self, container, *args):
        return self.swift_conn.delete_container(container, *args)
