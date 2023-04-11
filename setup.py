from setuptools import find_packages, setup


def read(path):
    # type: (str) -> str
    with open(path, "rt", encoding="utf8") as f:
        return f.read().strip()


setup(
    name="easterobot",
    version="1.0.0",
    author="Dashstrom",
    author_email="dashstrom.pro@gmail.com",
    url="https://github.com/Dashstrom/easterobot",
    license="GPL-3.0 License",
    packages=find_packages(exclude=("tests", "images", "tools")),
    description="Discord bot for Easter.",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    python_requires=">=3.6.0",
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    keywords=["discord", "bot", "easter", "eggs", "hunt"],
    install_requires=read("requirements.txt").split("\n"),
    platforms="any",
    include_package_data=True,
    package_data={
        "easterobot": ["py.typed", "data/config.yml.exemple"],
    },
    entry_points={
        "console_scripts": [
            "easterobot=easterobot.bot:Easterobot",
        ]
    },
)
