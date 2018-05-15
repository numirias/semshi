from setuptools import setup

# The setup is currently only used for tests. See the README for installation
# instructions in Neovim.
setup(
    name='semshi',
    description='Semantic Highlighting for Python in Neovim',
    packages=['semshi'],
    author='numirias',
    author_email='numirias@users.noreply.github.com',
    version='0.1.0',
    url='https://github.com/numirias/semshi',
    license='MIT',
    python_requires='>=3',
    install_requires=[
        'pytest>=3.3.2',
        'neovim',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Text Editors',
    ],
)
