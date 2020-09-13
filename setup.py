from setuptools import setup, find_packages, Extension

setup(
    name = 'web_dwc2',
    version = '0.0.0+git',
    description = 'Duet3D Web Control Interface Klipper Translator',
    packages=find_packages(),
    include_package_data = True,
    entry_points = { "console_scripts": [ "web_dwc2 = web_dwc2.web_dwc2:main" ] },
    url = "https://github.com/Stephan3/dwc2-for-klipper-socket",
)

