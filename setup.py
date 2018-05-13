from setuptools import setup, find_packages

setup(
    name='slappy',
    description='Slack bot framework',
    version='0.1.0',
    url='https://github.com/berekuk/slappy',
    author='Vyacheslav Matyukhin',
    author_email='me@berekuk.ru',
    packages=find_packages(),
    install_requires=[
        'flask', 'apscheduler', 'slackclient', 'slackeventsapi',
    ],
    license='MIT',
)
