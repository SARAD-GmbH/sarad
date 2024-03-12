"""Setup configuration for deployment of datacollector"""
import setuptools  # type: ignore

with open("README.org", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="datacollector",
    version="0.2",
    author="Michael Strey",
    author_email="strey@sarad.de",
    description=(
        "Libraries and sample application to collect data from SARAD" " instruments."
    ),
    long_description=long_description,
    long_description_content_type="text/x-org",
    url="https://github.com/SARAD-GmbH/datacollector",
    package_data={"sarad": ["py.typed"]},
    packages=setuptools.find_packages(),
    install_requires=[
        "click",
        "click_log",
        "pyserial",
        "filelock",
        "hashids",
        "pyyaml",
        "py-zabbix",
        "bitvector",
        "schedule",
        "appdirs",
        "overrides",
    ],
    entry_points="""
        [console_scripts]
        datacollector=sarad.datacollector:cli
    """,
    scripts=["sarad/datacollector.py"],
    data_files=[("config", ["datacollector.conf", "sarad/instruments.yaml"])],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Operating System :: OS Independent",
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
    ],
    python_requires=">=3.6",
)
