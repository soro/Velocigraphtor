#!/usr/bin/env python

import sys
from setuptools import setup

long_description="""
Slimmer server for graphite data
================================
more info here
"""


def main():
    install_requires=[]
    # install_requires=['carbon']
    setup(
        name='Graphite-Lite',
        description='Slimmer server for graphite data',
        long_description=long_description,
        url='',
        version='0.1',
        license='GPLv2 or later',
        platforms=['unix', 'linux', 'osx', 'cygwin', 'win32'],
        author='Soeren Roerden',
        author_email='',
        packages=['graphitelite', ],
        entry_points={'console_scripts': [ 'graphitelite=graphitelite.thinserver:main' ]},
        install_requires=install_requires,
        zip_safe=True,
        classifiers=[
            'Development Status :: 3 - Alpha',
            'Intended Audience :: Developers',
            'License :: OSI Approved :: GNU General Public License (GPL)',
             'Operating System :: POSIX',
             'Operating System :: Microsoft :: Windows',
             'Operating System :: MacOS :: MacOS X',
             'Topic :: RRD',
             'Topic :: Logging',
             'Topic :: Utilities',
             'Programming Language :: Python',
        ],
    )

if __name__ == '__main__':
    main()
