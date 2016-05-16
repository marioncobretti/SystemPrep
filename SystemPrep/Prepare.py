#!/usr/bin/env python
import argparse
import datetime
import json
import logging
import os
import platform
import subprocess

import yaml

from SystemPrep.Manager.base import LinuxContentManager, WindowsContentManager
from SystemPrep.SystemPrepExceptions import SystemFatal as exceptionhandler


class Prepare(object):
    def __init__(self, noreboot, s3, config_path, stream, log_path):
        """
        Class constructor
        """
        self.kwargs = {}
        self.noreboot = noreboot
        self.s3 = s3
        self.system = platform.system()
        self.config_path = config_path
        # TODO create a config path and add this in so it can be automagically obtained.
        # This will remove the hardcoded local path.
        self.default_config = './static/config.yaml'
        self.log_path = log_path
        self.config = None
        self.system_params = None
        self.system_drive = None
        self.execution_scripts = None

        if stream and os.path.exists(log_path):
            logging.basicConfig(filename=os.path.join(self.log_path,
                                                      'SystemPrep-{0}.log'.format(str(datetime.date.today()))),
                                format='%(levelname)s:\t%(message)s',
                                level=logging.DEBUG)
            self.logger = logging.getLogger()
            self.logger.info('\n\n\n{0}'.format(datetime.datetime.now()))
        elif stream:
            logging.error('{0} does not exist'.format(log_path))
        else:
            logging.error('Stream logger is not enabled!')

        self.logger.info('Parameters:  {0}'.format(self.kwargs))
        self.logger.info('System Type: {0}'.format(self.system))

    def _get_config_data(self):

        if not os.path.exists(self.config_path):
            self.logger.warning('{0} does not exist.  using the default config.'.format(self.config_path))
            self.config_path = self.default_config

        data = None
        with open(self.config_path) as f:
            data = f.read()

        if data:
            self.config = yaml.load(data)

    def _linux_paths(self):
        params = {}
        params['prepdir'] = os.path.join('{0}'.format(self.system_drive), 'usr', 'tmp', 'systemprep')
        params['readyfile'] = os.path.join('{0}'.format(self.system_drive), 'var', 'run', 'system-is-ready')
        params['logdir'] = os.path.join('{0}'.format(self.system_drive), 'var', 'log')
        params['workingdir'] = os.path.join('{0}'.format(params['prepdir']), 'workingfiles')
        params['restart'] = 'shutdown -r +1 &'
        self.system_params = params

    def _windows_paths(self):
        params = {}
        params['prepdir'] = os.path.join('{0}'.format(self.system_drive), 'SystemPrep')
        params['readyfile'] = os.path.join('{0}'.format(params['prepdir']), 'system-is-ready')
        params['logdir'] = os.path.join('{0}'.format(params['prepdir']), 'Logs')
        params['workingdir'] = os.path.join('{0}'.format(params['prepdir']), 'WorkingFiles')
        params['shutdown_path'] = os.path.join('{0}'.format(os.environ['SYSTEMROOT']), 'system32', 'shutdown.exe')
        params['restart'] = params["shutdown_path"] + " /r /t 30 /d p:2:4 /c " + \
                            "\"SystemPrep complete. Rebooting computer.\""
        self.system_params = params

    def _get_system_params(self):
        """
        Returns a dictionary of OS platform-specific parameters.
            :rtype : dict
        """

        if 'Linux' in self.system:
            self.system_drive = '/'
            self._linux_paths()
        elif 'Windows' in self.system:
            self.system_drive = os.environ['SYSTEMDRIVE']
            self._windows_paths()
        else:
            self.logger.fatal('System, {0}, is not recognized?'.format(self.system))
            exceptionhandler('The scripts do not recognize this system type: {0}'.format(self.system))

        # Create SystemPrep directories
        try:
            if not os.path.exists(self.system_params['logdir']):
                os.makedirs(self.system_params['logdir'])
            if not os.path.exists(self.system_params['workingdir']):
                os.makedirs(self.system_params['workingdir'])
        except Exception as exc:
            self.logger.fatal('Could not create a directory in {0}.\n'
                              'Exception: {0}'.format(self.system_params['prepdir'], exc))
            exceptionhandler(exc)

    def _get_scripts_to_execute(self):
        """
        Returns an array of hashtables. Each hashtable has two keys: 'ScriptSource' and 'Parameters'.
        'ScriptSource' is the path to the script to be executed. Only supports http/s sources currently.
        'Parameters' is a hashtable of parameters to pass to the script.
        Use `merge_dicts({yourdict}, scriptparams)` to merge command line parameters with a set of default parameters.

        """
        self._get_config_data()

        scriptstoexecute = self.config[self.system]
        for item in self.config[self.system]:
            try:
                self.config[self.system][item]['Parameters'].update(self.kwargs)
            except Exception as exc:
                self.logger.fatal('For {0} in {1} the parameters could not be merged'.format(
                    item,
                    self.config_path
                ))
                exceptionhandler(exc)

        self.execution_scripts = scriptstoexecute

    def execute_scripts(self):
        """
        Master Script that calls content scripts to be deployed when provisioning systems.
        """
        self.logger.info('+' * 80)

        self._get_system_params()
        self.logger.info(self.system_params)

        self._get_scripts_to_execute()
        self.logger.info('Got scripts to execute.')

        if 'Linux' in self.system:
            content_manager = LinuxContentManager()
        elif 'Windows' in self.system:
            content_manager = WindowsContentManager()
        else:
            exceptionhandler('There is no known System!')

        # Loop through each 'script' in scripts
        for script in self.execution_scripts:
            url = self.execution_scripts[script]['ScriptSource']
            self.logger.info(url)

            filename = url.split('/')[-1]
            self.logger.info(filename)

            fullfilepath = os.path.join(self.system_params['workingdir'], filename)
            self.logger.info(fullfilepath)

            # Download each script, script['ScriptSource']
            content_manager.download_file(url, fullfilepath, self.s3)

            # Execute each script, passing it the parameters in script['Parameters']
            self.logger.info('Running script -- {0}'.format(self.execution_scripts[script]['ScriptSource']))
            self.logger.info('Sending parameters --')

            configuration = json.dumps(self.execution_scripts[script]['Parameters'])

            if 'Yum' in script:
                content_manager.yum_repo_install(configuration)
            elif 'Salt' in script:
                content_manager.salt_install(configuration)

        content_manager.cleanup()

        if self.kwargs['noreboot']:
            self.logger.info('Detected `noreboot` switch. System will not be rebooted.')
        else:
            self.logger.info('Reboot scheduled. System will reboot after the script exits.')
            subprocess.call(self.system_params['restart'], shell=True)

        self.logger.info('-' * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--noreboot', dest='noreboot', action='store_true')
    parser.add_argument('--sourceiss3bucket', dest='sourceiss3bucket', action='store_true')
    parser.add_argument('--config', dest='config', default='config.yaml')
    parser.add_argument('--logger', dest='logger', action='store_true')
    parser.add_argument('--log-path', dest='log_path', default='.')

    systemprep = SystemPrep(parser.parse_args().noreboot,
                            parser.parse_args().sourceiss3bucket,
                            parser.parse_args().config,
                            parser.parse_args().logger,
                            parser.parse_args().log_path)
    systemprep.execute_scripts()





