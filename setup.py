from setuptools import setup, find_packages

setup(
    name='facebook-birthdays-importer',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Flask', 'Flask-Session',
        'google-auth-oauthlib', 'google-api-python-client', 'icalendar'
    ],
    entry_points={
        'console_scripts': [
            'fb-bdays-web=app:main',  # if you add a main() in app.py
        ],
    },
)
