from setuptools import setup


setup(
    name='semshi',
    description='Semantic Syntax Highlighting for Python',
    packages=['semshi'],
    author='numirias',
    author_email='numirias@users.noreply.github.com',
    version='0.1.0',
    url='TODO',
    license='MIT',
    python_requires='>=3',
    install_requires=[
        'pytest>=3.3.2',
        'neovim',
    ],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Text Editors',
    ],
)
