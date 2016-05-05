#!/usr/bin/env python
import logging
import sys
import argparse
import boto
import urllib2
import os
import platform
import shutil
import subprocess
import yaml
import json
import datetime

def ExceptionHandler(msg):
    print(msg)
    sys.exit()


class SystemPrep(object):

    def __init__(self, params, scriptpath, config_path, stream=False):
        """
        Class constructor
        """
        self.kwargs = params
        self.script_path = scriptpath
        self.system = platform.system()
        self.config_path = config_path
        # TODO create a config path and add this in so it can be automagically obtained. This will remove the hardcoded local path.
        self.default_config = 'default.yaml'
        self.config = None
        self.system_params = None
        self.system_drive = None
        self.execution_scripts = None

        logging.info('Parameters:\n{}'.format(self.kwargs))
        logging.info('System Type:\t{}'.format(self.system))


        if stream and os.path.exists('logs'):
            logging.basicConfig(filename=os.path.join('.', 'SystemPrep-{}.log'.format(str(datetime.date.today()))),
                                format='%(levelname)s:\t%(message)s',
                                level=logging.DEBUG)
            logging.info('\n\n\n{}'.format(datetime.datetime.now()))
        else:
            logging.warning('Stream logging is not enabled!')

    def _get_config_data(self):

        if not os.path.exists(self.config_path):
            logging.warning('{} does not exist.  using the default config.'.format(self.config_path))
            self.config_path = self.default_config

        data = None
        with open(self.config_path) as f:
            data = f.read()

        self.config = yaml.dump(data)

    def execute_scripts(self):
        """
        Master Script that calls content scripts to be deployed when provisioning systems.
        """
        logging.info('+' * 80)
        logging.info('Entering script -- {0}'.format(self.script_path))

        self._get_system_params()
        logging.info(self.system_params)

        self._get_scripts_to_execute()
        logging.info('Got scripts to execute.')

        # Loop through each 'script' in scripts
        for script in self.execution_scripts[self.system]:
            url = script['ScriptSource']
            logging.info(url)

            filename = url.split('/')[-1]
            logging.info(filename)

            fullfilepath = os.path.join(self.system_params['workingdir'], filename)
            logging.info(fullfilepath)

            # Download each script, script['ScriptSource']
            self.download_file(url, fullfilepath, self.kwargs['sourceiss3bucket'])

            # Execute each script, passing it the parameters in script['Parameters']
            logging.info('Running script -- {}'.format(script['ScriptSource']))
            logging.info('Sending parameters --')

            if 'Linux' in self.system:
                result = subprocess.call(['python',
                                          fullfilepath,
                                          json.dumps(script['Parameters'])])
            else:
                paramstring = ' '.join("%s='%s'" % (key, val) for (key, val) in script['Parameters'].iteritems())
                powershell = 'C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe '
                fullcommand = powershell + ' {} {}'.format(fullfilepath, paramstring)
                # We need to do the same for Windows that we do for Linux, but need to test it out ....
                result = subprocess.call(fullcommand, shell=True)

            if result is not 0:
                message = 'Encountered an unrecoverable error executing a ' \
                          'content script. Exiting with failure.\n' \
                          'Command executed: {}' \
                    .format(script['Parameters'])
                ExceptionHandler(message)

        self.cleanup()

        if self.kwargs['noreboot']:
            logging.info('Detected `noreboot` switch. System will not be rebooted.')
        else:
            logging.info('Reboot scheduled. System will reboot after the script exits.')
            subprocess.call(self.system_params['restart'], shell=True)

        logging.info('{} complete!'.format(self.script_path))
        logging.info('-' * 80)

    def _linux_paths(self):
        params = {}
        params['prepdir'] = os.path.join('{}'.format(self.system_drive), 'usr', 'tmp', 'systemprep')
        params['readyfile'] = os.path.join('{}'.format(self.system_drive), 'var', 'run', 'system-is-ready')
        params['logdir'] = os.path.join('{}'.format(self.system_drive), 'var', 'log')
        params['workingdir'] = os.path.join('{}'.format(params['prepdir'], 'workingfiles'))
        params['restart'] = 'shutdown -r +1 &'
        self.system_params = params

    def _windows_paths(self):
        params = {}
        params['prepdir'] = os.path.join('{}'.format(self.system_drive), 'SystemPrep')
        params['readyfile'] = os.path.join('{}'.format(params['prepdir']), 'system-is-ready')
        params['logdir'] = os.path.join('{}'.format(params['prepdir']), 'Logs')
        params['workingdir'] = os.path.join('{}'.format(params['prepdir']), 'WorkingFiles')
        params['shutdown_path'] = os.path.join('{}'.format(os.environ['SYSTEMROOT']),'system32', 'shutdown.exe')
        params['restart'] = params['shutdown_path']  + ' /r /t 30 /d p:2:4 /c ' + \
                            '"SystemPrep complete. Rebooting computer."'
        self.system_params = params

    def _get_system_params(self):
        """
        Returns a dictionary of OS platform-specific parameters.
            :rtype : dict
        """

        if 'Linux' in self.system:
            self.systemdrive = '/'
            self._linux_paths()
        elif 'Windows' in self.system:
            self.systemdrive = os.environ['SYSTEMDRIVE']
            self._windows_paths()
        else:
            logging.fatal('System, {}, is not recognized?'.format(self.system))
            ExceptionHandler('The scripts do not recognize this system type: {}'.format(self.system))

        # Create SystemPrep directories
        try:
            if not os.path.exists(self.system_params['logdir']):
                os.makedirs(self.system_params['logdir'])
            if not os.path.exists(self.system_params['workingdir']):
                os.makedirs(self.system_params['workingdir'])
        except Exception as exc:
            logging.fatal('Could not create a directory in {}.\n'
                          'Exception: {}'.format(self.system_params['prepdir'], exc))
            ExceptionHandler(exc)


    def _get_scripts_to_execute(self):
        """
        Returns an array of hashtables. Each hashtable has two keys: 'ScriptSource' and 'Parameters'.
        'ScriptSource' is the path to the script to be executed. Only supports http/s sources currently.
        'Parameters' is a hashtable of parameters to pass to the script.
        Use `merge_dicts({yourdict}, scriptparams)` to merge command line parameters with a set of default parameters.
            :param workingdir: str, the working directory where content should be saved
            :rtype : dict
        """
        self._get_config_data()

        scriptstoexecute = self.config[self.system]
        for item in self.config[self.system]:
            try:
                self.config[self.system][item]['Parameters'].update(self.kwargs)
            except Exception as exc:
                logging.fatal('For {} in {} the parameters could not be merged'.format(
                    item,
                    self.config_path
                ))
                ExceptionHandler(exc)

        self.execution_scripts = scriptstoexecute

    def download_file(self, url, filename, sourceiss3bucket = False):
        """
        Download the file from `url` and save it locally under `filename`.
            :rtype : bool
            :param url:
            :param filename:
            :param sourceiss3bucket:
        """
        conn = None

        if sourceiss3bucket:
            bucket_name = url.split('/')[3]
            key_name = '/'.join(url.split('/')[4:])
            try:
                conn = boto.connect_s3()
                bucket = conn.get_bucket(bucket_name)
                key = bucket.get_key(key_name)
                key.get_contents_to_filename(filename=filename)
            except (NameError, boto.exception.BotoClientError):
                try:
                    bucket_name = url.split('/')[2].split('.')[0]
                    key_name = '/'.join(url.split('/')[3:])
                    bucket = conn.get_bucket(bucket_name)
                    key = bucket.get_key(key_name)
                    key.get_contents_to_filename(filename=filename)
                except Exception as exc:
                    raise SystemError('Unable to download file from S3 bucket.\n'
                                      'url = {0}\n'
                                      'bucket = {1}\n'
                                      'key = {2}\n'
                                      'file = {3}\n'
                                      'Exception: {4}'
                                      .format(url, bucket_name, key_name,
                                              filename, exc))
            except Exception as exc:
                raise SystemError('Unable to download file from S3 bucket.\n'
                                  'url = {0}\n'
                                  'bucket = {1}\n'
                                  'key = {2}\n'
                                  'file = {3}\n'
                                  'Exception: {4}'
                                  .format(url, bucket_name, key_name,
                                          filename, exc))
            print('Downloaded file from S3 bucket -- \n'
                  '    url      = {0}\n'
                  '    filename = {1}'.format(url, filename))
        else:
            try:
                response = urllib2.urlopen(url)
                with open(filename, 'wb') as outfile:
                    shutil.copyfileobj(response, outfile)
            except Exception as exc:
                # TODO: Update `except` logic
                raise SystemError('Unable to download file from web server.\n'
                                  'url = {0}\n'
                                  'filename = {1}\n'
                                  'Exception: {2}'
                                  .format(url, filename, exc))
            print('Downloaded file from web server -- \n'
                  '    url      = {0}\n'
                  '    filename = {1}'.format(url, filename))
        return True

    def cleanup(self):
        """
        Removes temporary files loaded to the system.
            :return: bool
        """
        logging.info('+-' * 40)
        logging.info('Cleanup Time...')
        try:
            shutil.rmtree(self.system_params['workingdir'])
        except Exception as exc:
            # TODO: Update `except` logic
            logging.fatal('Cleanup Failed!\n'
                              'Exception: {0}'.format(exc))
            ExceptionHandler('Cleanup Failed.\nAborting.')

        logging.info('Removed temporary data in working directory -- {}'.format(self.system_params['workingdir']))
        logging.info('Exiting cleanup routine...')
        logging.info('-+' * 40)
        return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--noreboot', type=bool, default=False, choices=[True, False])
    parser.add_argument('--sourceiss3bucket', type=bool, default=False, choices=[True, False])
    params = parser.parse_known_args()

    kwargs = vars(params[0])



    # Loop through extra parameters and put into dictionary.
    for param in params[1]:
        if '=' in param:
            [key, value] = param.split('=', 1)
            if key.lower() in ['noreboot', 'sourceiss3bucket']:
                kwargs[key.lower()] = True if value.lower() == 'true' else False
            else:
                kwargs[key.lower()] = value
        else:
            message = 'Encountered an invalid parameter: {0}'.format(param)
            raise ValueError(message)

    systemprep = SystemPrep(kwargs, os.path.abspath(parser.prog), 'config.yaml', stream=True)
    systemprep.execute_scripts()
