from setuptools import setup, find_packages

setup(
    name="bitwill",
    version="1.0.0",
    description="BITWILL - Blockchain Inheritance & Will Security System",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "pycryptodome>=3.19.0",
        "base58>=2.1.1",
    ],
    extras_require={
        "cli": ["click>=8.1.0", "rich>=13.0.0", "qrcode>=7.4.0"],
        "web": ["flask>=3.0.0"],
        "full": ["mnemonic>=0.20", "ecdsa>=0.18.0", "flask>=3.0.0"],
    },
    entry_points={
        "console_scripts": [
            "bitwill=bitwill.cli.interface:main",
            "bitwill-web=bitwill.web.server:main",
        ],
    },
    package_data={
        "bitwill": ["web/templates/*.html", "web/static/*"],
    },
)
