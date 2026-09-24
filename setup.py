from setuptools import setup, find_packages

setup(
    name="omnicode",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "openai>=1.50.0",
        "rich>=13.7.0",
        "prompt_toolkit>=3.0.40",
        "click>=8.1.0",
        "pydantic>=2.0.0",
        "httpx>=0.27.0",
        "tiktoken>=0.7.0",
        "pyyaml>=6.0",
        "pathspec>=0.12.0",
        "beautifulsoup4>=4.12.0",
    ],
    entry_points={
        "console_scripts": [
            "omnicode=omnicode.cli:main",
            "omni=omnicode.cli:main",
        ],
    },
)
