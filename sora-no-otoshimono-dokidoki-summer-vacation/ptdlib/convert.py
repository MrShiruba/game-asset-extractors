"""Dispatch game-specific formats to their converter, by file extension.

Standard formats (ADX, GIM, PNG) are never converted.
"""
import os
import sys

from . import fab, sos, tfp, vgp


def convert(path, data, lower=True):
    """Convert one extracted file. Returns the number of files written."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in ('.fab', '.fsb'):
            return fab.convert(path, data, lower)
        if ext == '.vgp':
            return vgp.convert(path, data)
        if ext == '.tfp':
            return tfp.convert(path, data)
        if ext == '.sos':
            return sos.convert(path, data)
    except Exception as e:
        print('  ! %s: conversion failed (%s)' % (path, e), file=sys.stderr)
    return 0
