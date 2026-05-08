from flask import Blueprint, Response, stream_with_context
from services.task_manager import task_manager
from utils import success_response, error_response

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("/tasks/<task_id>")
def get_task(task_id):
    task = task_manager.get(task_id)
    if not task:
        return error_response("Task not found", 404)
    return success_response(task)


@tasks_bp.route("/tasks/<task_id>/stream")
def stream_task(task_id):
    def generate():
        yield from task_manager.sse_stream(task_id)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )
