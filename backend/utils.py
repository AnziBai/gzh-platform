from flask import jsonify


def success_response(data=None, message=""):
    return jsonify({"status": 0, "data": data, "message": message})


def error_response(message="", status_code=500):
    return jsonify({"status": -1, "data": None, "message": message}), status_code
