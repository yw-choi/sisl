#!/usr/bin/env python
"""
sids: Library to create/mingle/handle geometries and tight-binding sets in python.
"""

from __future__ import print_function

DOCLINES = __doc__.split("\n")

import sys, subprocess
import os, os.path as osp

CLASSIFIERS = """\
Development Status :: 5 - Production
Intended Audience :: Science/Research
License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)
Programming Language :: Python :: 2
Programming Language :: Python :: 3
Topic :: Software Development
Topic :: Scientific/Engineering
Topic :: Scientific/Engineering :: Physics
Topic :: Utilities
Operating System :: Microsoft :: Windows
Operating System :: POSIX
Operating System :: Unix
Operating System :: MacOS
"""

MAJOR               = 0
MINOR               = 4
MICRO               = 1
ISRELEASED          = True
VERSION             = '%d.%d.%d' % (MAJOR, MINOR, MICRO)

def generate_cython():
    cwd = osp.abspath(osp.dirname(__file__))
    print("Cythonizing sources")
    p = subprocess.call([sys.executable,
                          osp.join(cwd, 'tools', 'cythonize.py'),
                          'sids'],
                         cwd=cwd)
    if p != 0:
        raise RuntimeError("Running cythonize failed!")

scripts = ['sgeom','sgrid']

scripts = [osp.join('scripts', script) for script in scripts]

metadata = dict(
    name = 'sids',
    maintainer = "Nick R. Papior",
    maintainer_email = "nickpapior@gmail.com",
    description = DOCLINES[0],
    long_description = "\n".join(DOCLINES[2:]),
    download_url = "https://github.com/zerothi/sids/releases",
    license = 'LGPLv3',
    classifiers=[_f for _f in CLASSIFIERS.split('\n') if _f],
    platforms = ["Windows", "Linux", "Solaris", "Mac OS-X", "Unix"],
    test_suite='nose.collector',
    scripts = scripts,
    )

from numpy.distutils.core import setup

cwd = osp.abspath(osp.dirname(__file__))
if not osp.exists(osp.join(cwd, 'PKG-INFO')):
    # Generate Cython sources, unless building from source release
    #generate_cython()
    pass

# Generate configuration
def configuration(parent_package='',top_path=None):
    from numpy.distutils.misc_util import Configuration
    config = Configuration(None, parent_package, top_path)
    config.set_options(ignore_setup_xxx_py=True,
                       assume_default_configuration=True,
                       delegate_options_to_subpackages=True,
                       quiet=True)
    
    config.add_subpackage('sids')
    
    return config

metadata['version'] = VERSION
metadata['configuration'] = configuration
if not ISRELEASED:
    metadata['version'] = VERSION + '-dev'

# With credits from NUMPY developers we use this
# routine to get the git-tag
def git_version():
    def _minimal_ext_cmd(cmd):
        # construct minimal environment
        env = {}
        for k in ['SYSTEMROOT', 'PATH']:
            v = os.environ.get(k)
            if v is not None:
                env[k] = v
        # LANGUAGE is used on win32
        env['LANGUAGE'] = 'C'
        env['LANG'] = 'C'
        env['LC_ALL'] = 'C'
        out = subprocess.Popen(cmd, stdout = subprocess.PIPE, env=env).communicate()[0]
        return out

    try:
        out = _minimal_ext_cmd(['git', 'rev-parse', 'HEAD'])
        GIT_REVISION = out.strip().decode('ascii')
    except OSError:
        GIT_REVISION = "Unknown"

    return GIT_REVISION


def write_version_py(filename='sids/version.py'):
    version_str = """
# This file is automatically generated from sids setup.py
major   = {vrs[0]}
minor   = {vrs[1]}
micro   = {vrs[2]}
version = '.'.join(map(str,{vrs}))
release = {release}
# Git information
git_rev = '{git}'
git_rev_short = git_rev[:7]

if not release:
    version = version + '-' + git_rev_short
"""
    # If we are in git we try and fetch the
    # git version as well
    GIT_REV = git_version()

    with open(filename,'w') as fh:
        fh.write(version_str.format(vrs=[MAJOR,MINOR,MICRO],
                                    release=str(ISRELEASED),
                                    git=GIT_REV))
    
if __name__ == '__main__':

    # Create version file
    write_version_py()
    
    # Main setup of python modules
    setup(**metadata)
