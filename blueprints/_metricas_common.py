"""Helpers compartidos para los blueprints de métricas."""
from flask import jsonify


def _ok(data):
    return jsonify({'ok': True, 'data': data})


def _err(msg, code=400):
    return jsonify({'ok': False, 'error': msg}), code
