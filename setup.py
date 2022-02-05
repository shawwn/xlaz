# -*- coding: utf-8 -*-
from setuptools import setup
import os

def path(to):
  return os.path.join(os.path.dirname(__file__), to)

exec(compile(open(path("setup_info.py")).read(), path("setup_info.py"), "exec"))

package_dir = \
{'': 'src'}

packages = \
['xlaz']

package_data = \
{'': ['*']}

install_requires = \
['tensorflow-checkpoint-reader>=0.1.0']

setup_kwargs = {
    'package_dir': package_dir,
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.8,<4.0',
}


setup(**setup_kwargs, **base_kwargs)
