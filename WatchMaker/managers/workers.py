import os
import json
import logging

from watchmaker.workers.base import Salt, Yum
from watchmaker.managers.base import WorkersManagerBase, LinuxManager, WindowsManager

class LinuxWorkersManager(WorkersManagerBase):
    """

    """

    def __init__(self, s3, system_params, execution_scripts):
        super(LinuxWorkersManager, self).__init__()
        self.execution_scripts = execution_scripts
        self.manager = LinuxManager()
        self.s3 = s3
        self.system_params = system_params

    def _worker_execution(self):
        pass

    def _worker_validation(self):
        pass

    def worker_cadence(self):
        
        # Loop through each 'script' in scripts
        for script in self.execution_scripts:
            url = self.execution_scripts[script]['ScriptSource']
            logging.info(url)

            filename = url.split('/')[-1]
            logging.info(filename)

            fullfilepath = os.path.join(self.system_params['workingdir'], filename)
            logging.info(fullfilepath)

            # Download each script, script['ScriptSource']
            self.manager.download_file(url, fullfilepath, self.s3)

            # Execute each script, passing it the parameters in script['Parameters']
            logging.info('Running script -- {0}'.format(self.execution_scripts[script]['ScriptSource']))
            logging.info('Sending parameters --')

            configuration = json.dumps(self.execution_scripts[script]['Parameters'])

            if 'Yum' in script:
                yum = Yum()
                yum.repo_install(configuration)
            elif 'Salt' in script:
                salt = Salt()
                salt.install(configuration)

    def cleanup(self):
        self.manager.cleanup()


class WindowsWorkersManager(WorkersManagerBase):
    """

    """

    def __init__(self, s3, system_params, execution_scripts):
        super(WindowsWorkersManager, self).__init__()
        self.execution_scripts = execution_scripts
        self.manager = WindowsManager()
        self.s3 = s3
        self.system_params = system_params

    def _worker_execution(self):
        pass

    def _worker_validation(self):
        pass

    def worker_cadence(self):
        pass

    def cleanup(self):
        self.manager.cleanup()