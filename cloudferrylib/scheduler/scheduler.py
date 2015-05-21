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


import multiprocessing
import traceback

from cloudferrylib.scheduler.namespace import Namespace, CHILDREN
from cloudferrylib.utils import utils
from cursor import Cursor
from task import BaseTask
from thread_tasks import WrapThreadTask


LOG = utils.get_log(__name__)


NO_ERROR = 0
ERROR = 255


class BaseScheduler(object):
    def __init__(self, namespace=None, cursor=None):
        self.namespace = namespace if namespace else Namespace()
        self.status_error = NO_ERROR
        self.cursor = cursor
        self.map_func_task = dict() if not hasattr(
            self,
            'map_func_task') else self.map_func_task
        self.map_func_task[BaseTask()] = self.task_run

    def event_start_task(self, task):
        LOG.info('%s Start task: %s', '-' * 8, task)
        return True

    def event_end_task(self, task):
        LOG.info('%s End task: %s', '-' * 8, task)
        return True

    def event_error_task(self, task, e):
        return True

    def error_task(self, task, e):
        LOG.exception("%s TASK FAILED", task)
        return self.event_error_task(task, e)

    def run_task(self, task):
        if self.event_start_task(task):
            self.map_func_task[task](task)
        self.event_end_task(task)

    def start(self):
        for task in self.cursor:
            try:
                self.run_task(task)
            except Exception as e:
                self.status_error = ERROR
                self.exception = e
                self.error_task(task, e)
                break

    def task_run(self, task):
        task(namespace=self.namespace)

    def addCursor(self, cursor):
        self.cursor = cursor


class SchedulerThread(BaseScheduler):
    def __init__(self, namespace=None, thread_task=None, cursor=None,
                 scheduler_parent=None):
        super(SchedulerThread, self).__init__(namespace, cursor)
        self.map_func_task[WrapThreadTask()] = self.task_run_thread
        self.child_threads = dict()
        self.thread_task = thread_task
        self.scheduler_parent = scheduler_parent

    def event_start_children(self, thread_task):
        self.child_threads[thread_task] = True
        return True

    def event_stop_children(self, thread_task):
        del self.child_threads[thread_task]
        return True

    def trigger_start_scheduler(self):
        if self.scheduler_parent:
            self.scheduler_parent.event_start_children(self.thread_task)

    def trigger_stop_scheduler(self):
        if self.scheduler_parent:
            self.scheduler_parent.event_stop_children(self.thread_task)

    def start(self):
        if not self.thread_task:
            self.start_current_thread()
        else:
            self.start_separate_thread()

    def start_separate_thread(self):
        p = multiprocessing.Process(target=self.start_current_thread)
        self.namespace.vars[CHILDREN][self.thread_task]['process'] = p
        p.start()

    def start_current_thread(self):
        self.trigger_start_scheduler()
        super(SchedulerThread, self).start()
        self.trigger_stop_scheduler()

    def fork(self, thread_task, is_deep_copy=False):
        namespace = self.namespace.fork(is_deep_copy)
        scheduler = self.__class__(namespace=namespace,
                                   thread_task=thread_task,
                                   cursor=Cursor(thread_task.getNet()),
                                   scheduler_parent=self)
        self.namespace.vars[CHILDREN][thread_task] = {
            'namespace': namespace,
            'scheduler': scheduler,
            'process': None
        }
        return scheduler

    def task_run_thread(self, task):
        scheduler_fork = self.fork(task)
        scheduler_fork.start()


class Scheduler(SchedulerThread):
    def __init__(self, namespace=None, thread_task=False, cursor=None,
                 scheduler_parent=None):
        super(Scheduler, self).__init__(namespace, thread_task, cursor,
                                        scheduler_parent)
