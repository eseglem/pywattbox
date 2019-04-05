import setuptools

setuptools.setup(
    name="pywattbox",
    version="0.2.0",
    author="Erik Seglem",
    author_email="erik.seglem@gmail.com",
    description="A python wrapper for the WattBox API.",
    url="https://github.com/eseglem/pywattbox",
    license='MIT',
    packages=setuptools.find_packages(),
    install_requires=['requests', 'beautifulsoup4', 'lxml'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    zip_safe=True,
)
