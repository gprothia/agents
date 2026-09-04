from setuptools import setup

setup(
    name="ge_agent",
    version="0.1.0",
    packages=["ge_agent"],
    package_dir={"ge_agent": "."},
    package_data={"ge_agent": ["grounding/*.md"]},
)
