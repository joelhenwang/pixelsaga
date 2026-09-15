import sys


def test_package_importable():
    import worldsim

    assert worldsim.__version__ == "0.1.0"


def test_layer_packages_importable():
    import importlib

    for layer in ("domain", "application", "agents", "infrastructure", "interfaces"):
        assert importlib.import_module(f"worldsim.{layer}")


def test_python_version_is_312():
    assert sys.version_info[:2] == (3, 12)
