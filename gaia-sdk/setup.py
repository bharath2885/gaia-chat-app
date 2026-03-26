from setuptools import setup, find_packages

setup(
    name="gaia-sdk",
    version="0.1.0",
    description="Python SDK for the Cohesity Gaia RAG API",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Cohesity",
    license="Apache-2.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.27",
        "pydantic>=2.0",
        "python-dotenv>=1.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0",
            "pytest-asyncio>=0.23",
            "ruff>=0.4",
            "mypy>=1.10",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
