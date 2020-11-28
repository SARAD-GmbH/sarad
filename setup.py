import setuptools               # type: ignore

with open("README.org", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='data_collector',
    version='0.2',
    author="Michael Strey",
    author_email="strey@sarad.de",
    description=("Libraries and sample application to collect data from SARAD"
                 " instruments."),
    long_description=long_description,
    long_description_content_type="text/x-org",
    url="https://github.com/SARAD-GmbH/data_collector",
    packages=setuptools.find_packages(),
    install_requires=[
        'click', 'click_log', 'pyserial', 'filelock', 'hashids', 'pyyaml',
        'py-zabbix', 'bitvector', 'schedule', 'appdirs'
    ],
    entry_points='''
        [console_scripts]
        data_collector=sarad.data_collector:cli
    ''',
    scripts=['sarad/data_collector.py'],
    data_files=[('config', ['data_collector.conf', 'sarad/instruments.yaml'])],
    classifiers=[
        "Programming Language :: Python :: 3",
        ("License :: OSI Approved :: GNU Lesser General Public License v3 "
         "(LGPLv3)"),
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
    ],
    python_requires='>=3.6'
)
