
from cloudferrylib.base.action import action
from fabric.api import run, settings


class ConvertFileToImage(action.Action):

    def run(self, file_path=None, image_format=None, image_name=None, **kwargs):

        cfg = self.cloud.cloud_config.cloud
        with settings(host_string=cfg.host):
            out = run(("glance --os-username=%s --os-password=%s --os-tenant-name=%s " +
                       "--os-auth-url=%s " +
                       "image-create --name %s --disk-format=%s --container-format=bare --file %s| " +
                       "grep id") %
                      (cfg.user,
                       cfg.password,
                       cfg.tenant,
                       cfg.auth_url,
                       image_name,
                       image_format,
                       file_path))
            image_id = out.split("|")[2].replace(' ', '')
            return image_id
