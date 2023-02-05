import setuptools

setuptools.setup(
    name="pywattbox",
    version="0.5.0a",
    author="Erik Seglem",
    author_email="erik.seglem@gmail.com",
    description="A python wrapper for the WattBox API.",
    url="https://github.com/eseglem/pywattbox",
    license="MIT",
    packages=setuptools.find_packages(),
    python_requires=">=3.7",
    install_requires=["httpx", "beautifulsoup4", "lxml", "h11>=0.14.0", "scrapli"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Home Automation",
    ],
    zip_safe=True,
)
