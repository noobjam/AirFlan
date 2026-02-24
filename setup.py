from setuptools import setup, find_packages

setup(
    name="airflan",
    version="2.0.0",
    packages=find_packages(),
    install_requires=[
        "streamlit",
        "streamlit-agraph",
        "loguru",
        "dask[distributed]",
        "sqlalchemy",
        "croniter",
        "click"
    ],
    entry_points={
        "console_scripts": [
            "airflan=airflan.cli:cli",
        ],
    },
)
