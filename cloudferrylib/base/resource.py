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

import time
from cloudferrylib.utils import proxy_client
from cloudferrylib.utils import timeout_exception
from cloudferrylib.utils import utils

LOG = utils.get_log(__name__)


class Resource(object):
    def __init__(self):
        pass

    def proxy(self, client, cfg):
        retry = cfg.migrate.retry
        time_wait = cfg.migrate.time_wait
        return proxy_client.Proxy(client, retry, time_wait)

    def read_info(self, opts={}):
        pass

    def deploy(self, *args):
        pass

    def save(self):
        pass

    def restore(self):
        pass

    def required_tenants(self):
        """Returns list of tenants required by resource. Important for the
        filtering feature."""
        return []

    def wait_for_status(self, res_id, get_status, wait_status, timeout=60):
        delay = 1
        while delay < timeout:
            if get_status(res_id).lower() == wait_status.lower():
                break
            time.sleep(delay)
            delay *= 2
        else:
            raise timeout_exception.TimeoutException(
                get_status(res_id).lower(),
                wait_status, "Timeout exp")

    def try_wait_for_status(self, res_id, get_status, wait_status, timeout=60):
        try:
            self.wait_for_status(res_id, get_status, wait_status, timeout)
        except timeout_exception.TimeoutException as e:
            LOG.warning("Resource '%s' has not changed status to '%s'(%s)",
                        res_id, wait_status, e)

    def get_status(self, resource_id):
        pass

    def __deepcopy__(self, memo):
        return self
