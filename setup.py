from setuptools import setup  # type: ignore

setup(
    name='data_collector',
    version='0.1',
    py_modules=['data_collector', 'sari', 'nb_easy'],
    install_requires=[
        'click', 'click_log', 'pyserial', 'filelock', 'hashids', 'pyyaml',
        'py-zabbix', 'bitvector', 'schedule'
    ],
    entry_points='''
        [console_scripts]
        data_collector=data_collector:cli
    ''',
)
