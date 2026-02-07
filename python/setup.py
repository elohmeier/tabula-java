from setuptools import Distribution, setup
from setuptools.command.install import install as _install

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except Exception:  # pragma: no cover
    _bdist_wheel = None


if _bdist_wheel is not None:
    class BinaryDistribution(Distribution):
        def has_ext_modules(self):
            # Force platlib wheel layout for bundled native runtime files.
            return True


    class install(_install):
        def finalize_options(self):
            super().finalize_options()
            self.install_lib = self.install_platlib


    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            super().finalize_options()
            self.root_is_pure = False


    setup(distclass=BinaryDistribution, cmdclass={"bdist_wheel": bdist_wheel, "install": install})
else:
    setup()
