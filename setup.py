from setuptools import setup

setup(
    name='data_collector',
    version='0.1',
    py_modules=['data_collector', 'SarI', 'NbEasy'],
    install_requires=[
        'Click', 'pyserial', 'filelock', 'hashids', 'pyyaml', 'py-zabbix', \
        'bitvector'
    ],
    entry_points='''
        [console_scripts]
        data_collector=data_collector:cli
    ''',
)
