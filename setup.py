from setuptools import setup

setup(
    name='data_collector',
    version='0.1',
    py_modules=['data_collector', 'SarI'],
    install_requires=[
        'Click', 'pyserial', 'filelock', 'struct', 'hashids'
    ],
    entry_points='''
        [console_scripts]
        data_collector=data_collector:cli
    ''',
)
