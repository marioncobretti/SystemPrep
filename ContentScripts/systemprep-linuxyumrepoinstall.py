#!/usr/bin/env python
import json
import re
import shutil
import sys
import urllib2
import json
import logging

from boto.exception import BotoClientError


def download_file(url, filename):
    """
Download the file from `url` and save it locally under `filename`.
    :rtype : bool
    :param url:
    :param filename:
    """
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


def _validate_distro():
    supported_dists = ('amazon', 'centos', 'red hat')

    match_supported_dist = re.compile(r'^({0})'
                                    '(?:[^0-9]+)'
                                    '([\d]+[.][\d]+)'
                                    '(?:.*)'
                                    .format('|'.join(supported_dists)))
    amazon_epel_versions = {
        '2014.03' : '6',
        '2014.09' : '6',
        '2015.03' : '6',
        '2015.09' : '6',
    }

    # Read first line from /etc/system-release
    release = None
    try:
        with open(name='/etc/system-release', mode='rb') as f:
            release = f.readline().strip()
    except Exception as exc:
        raise SystemError('Could not read /etc/system-release. '
                          'Error: {0}'.format(exc))

    # Search the release file for a match against _supported_dists
    matched = match_supported_dist.search(release.lower())
    if matched is None:
        # Release not supported, exit with error
        raise SystemError('Unsupported OS distribution. OS must be one of: '
                          '{0}.'.format(', '.join(supported_dists)))

    # Assign dist,version from the match groups tuple, removing any spaces
    dist, version = (x.translate(None, ' ') for x in matched.groups())

    # Determine epel_version
    epel_version = None
    if 'amazon' == dist:
        epel_version = amazon_epel_versions.get(version, None)
    else:
        epel_version = version.split('.')[0]

    if epel_version is None:
        raise SystemError('Unsupported OS version! dist = {}, version = {}.'
                          .format(dist, version))

    return dist, version, epel_version

def _yum_repo(config):

    if not isinstance(config['yumrepolist'], list):
        raise SystemError('`yumrepomap` must be a list!')

def main(configuration):
    """
    Checks the distribution version and installs yum repo definition files
    that are specific to that distribution.
    :param yumrepomap: list of dicts, each dict contains two or three keys.
                       'url': the url to the yum repo definition file
                       'dist': the linux distribution to which the repo should
                               be installed. one of 'amazon', 'redhat',
                               'centos', or 'all'. 'all' is a special keyword
                               that maps to all distributions.
                       'epel_version': optional. match the major version of the
                                       epel-release that applies to the
                                       system. one of '6' or '7'. if not
                                       specified, the repo is installed to all
                                       systems.
        Example: [ { 
                     'url' : 'url/to/the/yum/repo/definition.repo',
                     'dist' : 'amazon' or 'redhat' or 'centos' or 'all',
                     'epel_version' : '6' or '7',
                   },
                 ]
    """
    try:
        config = json.loads(configuration)
    except ValueError:
        logging.fatal('The configuration passed was not properly formed JSON.  Execution Halted.')
        sys.exit(1)

    scriptname = __file__
    logging.info('+' * 80)
    logging.info('Entering script -- {0}'.format(scriptname))
    logging.info('Printing parameters...')

    if 'yumrepomap' in config and config['yumrepomap']:
        dist, version, epel_version = _yum_repo(config)
    else:
        logging.info('yumrepomap did not exist or was empty.')

    # TODO This block is weird.  Correct and done.
    for repo in config['yumrepomap']:
        # Test whether this repo should be installed to this system
        if repo['dist'] in [dist, 'all'] and repo.get('epel_version', 'all') \
                                                in [epel_version, 'all']:
            # Download the yum repo definition to /etc/yum.repos.d/
            url = repo['url']
            repofile = '/etc/yum.repos.d/{0}'.format(url.split('/')[-1])
            download_file(url, repofile)

    logging.info('{0} complete!'.format(scriptname))
    logging.info('-' * 80)


# def _convert_string_to_list_of_dicts(fixme):
#     # First, remove any parentheses or brackets
#     fixed = fixme.translate(None, '()[]')
#     # Then, split the string to form groups around {}
#     fixed = re.split('({.*?})', fixed)
#     # Now remove empty/bad strings
#     fixed = [v for v in filter(None, fixed) if not v == ', ']
#     # Remove braces and split on commas. it's now a list of lists
#     fixed = [v.translate(None, '{}').split(',') for v in fixed]
#     # Convert to a list of dicts
#     fixed = [dict(x.split(':', 1) for x in y) for y in fixed]
#     # Finally, strip whitespace around the keys and values
#     fixed = [dict((k.strip(), v.strip()) for k, v in x.items()) for x in fixed]
#     return fixed


if __name__ == "__main__":
    # # Convert command line parameters of the form `param=value` to a dict
    # kwargs = dict(x.split('=', 1) for x in sys.argv[1:])
    # # Convert parameter keys to lowercase, parameter values are unmodified
    # kwargs = dict((k.lower(), v) for k, v in kwargs.items())
    #
    # # Need to convert a formatted string to a list of dicts,
    # kwargs['yumrepomap'] = json.loads(kwargs.get('yumrepomap', ''))

    main(sys.argv[1])
