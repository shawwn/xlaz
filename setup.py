# -*- coding: utf-8 -*-
from setuptools import setup
import re
import os
import ast
import configparser

def openfile(path):
  return open(os.path.join(os.path.dirname(__file__), path))

def ev(x):
  x = re.sub(r'^(.+?)\s*[#].*$', r'\1', x) # strip inline comments
  return False if x == 'false' else True if x == 'true' else ast.literal_eval(x)

config = configparser.ConfigParser()
config.read(os.path.join(os.path.dirname(__file__), 'pyproject.toml'))
config = {k.lower(): {k1.lower(): ev(v1) for k1, v1 in v.items()} for k, v in config.items()}

info = config['tool.poetry']
author, author_email = re.findall(r"^(.+?)\s*(?:[<](.+?)[>])?$", info['authors'][0])[0]

base_kwargs = {
    'name': info['name'],
    'version': info['version'],
    'description': info.get('description'),
    'long_description': openfile(info.get('readme', 'README.md')).read(),
    'author': author,
    'author_email': author_email,
    'url': info.get('homepage'),
    'license': info.get('license'),
}

# prune blank strings or None values
base_kwargs = {k: v for k, v in base_kwargs.items() if v}


package_dir = \
{'': 'src'}

packages = \
['xla']

package_data = \
{'': ['*']}

setup_kwargs = {
    'package_dir': package_dir,
    'packages': packages,
    'package_data': package_data,
    'python_requires': '>=3.8,<4.0',
}


setup(**setup_kwargs, **base_kwargs)
