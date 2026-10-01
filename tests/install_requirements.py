"""Install the manifest's requirements the way Home Assistant does.

Home Assistant skips a requirement that already looks installed, comparing only
the package name and version. Using its own check here keeps the tests honest
about what ends up installed on a real system.
"""

import json
import sys

from homeassistant.util.package import install_package, is_installed

with open("/tmp/custom_components/matrix/manifest.json") as manifest_file:
    requirements = json.load(manifest_file)["requirements"]

for requirement in requirements:
    if is_installed(requirement):
        print(f"present   {requirement}")
    elif install_package(requirement):
        print(f"installed {requirement}")
    else:
        sys.exit(f"failed to install {requirement}")
