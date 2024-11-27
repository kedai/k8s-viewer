from setuptools import setup, find_packages

setup(
    name="k8s-resource-viewer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        'windows-curses;platform_system=="Windows"',  # only needed for Windows
    ],
    entry_points={
        'console_scripts': [
            'k8s-viewer=k8s_resource_viewer.main:main',
        ],
    },
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'black>=22.0.0',
            'isort>=5.0.0',
            'flake8>=4.0.0',
        ],
    },
    author="Bakhtiar Hamid",
    description="Interactive terminal-based Kubernetes cluster resource viewer",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    keywords="kubernetes, resources, monitoring, terminal, curses",
    url="https://github.com/yourusername/k8s-resource-viewer",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console :: Curses",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.8",
)
