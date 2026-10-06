from setuptools import find_packages, setup

package_name = 'py_hello'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='What410802',
    maintainer_email='what410802@126.com',
    description='ROS 2 入门包（Python）：hello_node',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'hello_node = py_hello.hello_node:main',
        ],
    },
)
