from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name='slappy',
    description='Slack bot framework',
    long_description=long_description,
    long_description_content_type="text/markdown",
    version='0.4.0',
    url='https://github.com/berekuk/slappy',
    python_requires='>=3.6',
    author='Vyacheslav Matyukhin',
    author_email='me@berekuk.ru',
    packages=find_packages(),
    install_requires=[
        'flask', 'apscheduler', 'slackclient', 'slackeventsapi>=2.0.0',
    ],
    license='MIT',
)
