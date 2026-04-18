from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version('QAcousticCamera')
except PackageNotFoundError:
    __version__ = None
