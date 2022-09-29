"""setup.py file."""

import uuid

from setuptools import setup, find_packages

__author__ = 'David Barroso <dbarrosop@dravetech.com>'

with open("requirements.txt", "r") as fs:
    reqs = [r for r in fs.read().splitlines() if (len(r) > 0 and not r.startswith("#"))]

setup(
    name="napalm-fsos",
    version="0.1.0",
    packages=find_packages(),
    author="Maximiliano Estudies",
    author_email="maxiestudies@gmail.com",
    description="Napalm driver for FS switches",
    classifiers=[
        'Topic :: Utilities',
         'Programming Language :: Python :: 3',
         'Programming Language :: Python :: 3.8',
        'Operating System :: POSIX :: Linux',
    ],
    url="https://github.com/napalm-automation-community/napalm-fsos",
    include_package_data=True,
    install_requires=reqs,
)
