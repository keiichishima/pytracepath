import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='pytracepath-keiichishima',
    version='0.0.1',
    author='Keiichi SHIMA',
    author_email='keiichi@iijlab.net',
    description='Tracepath implemented in Python3',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/keiichishima/pytracepath',
    packages=setuptools.find_packages(),
    py_modules=['pytracepath'],
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python :: 3',
        'Topic :: Internet',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Networking',
        'Topic :: System :: Systems Administration',
    ],
    python_requires='>=3.7',
    scripts=['bin/pytracepath'],
)
