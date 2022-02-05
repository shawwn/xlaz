# -*- coding: utf-8 -*-
from setuptools import setup
import re
import os

version = re.search(r'^version\s*=\s*"(.*?)"', open(os.path.join(os.path.dirname(__file__), 'pyproject.toml')).read(), flags=re.MULTILINE).group(1)
long_description = open(os.path.join(os.path.dirname(__file__), 'README.md')).read()

packages = \
['xla']

package_data = \
{'': ['*']}

setup_kwargs = {
    'name': 'xla',
    'version': version,
    'description': '',
    'long_description': long_description,
    'author': 'Shawn Presser',
    'author_email': 'shawnpresser@gmail.com',
    'maintainer': 'None',
    'maintainer_email': 'None',
    'url': 'None',
    'packages': packages,
    'package_data': package_data,
    'python_requires': '>=3.8,<4.0',
}


setup(**setup_kwargs)
