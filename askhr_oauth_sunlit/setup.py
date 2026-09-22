from setuptools import setup
from pathlib import Path

pkg = Path(__file__).resolve().parent.name
setup(
    name=pkg,
    version="0.1.0",
    packages=[pkg, "askhr_oauth"],
    package_dir={pkg: ".", "askhr_oauth": "."},
    include_package_data=True,
)
