"""Pure state transitions for the legacy Flask AI1 enrollment endpoint."""


ENROLLMENT_POSES = ("frontal", "left", "right", "up", "down")
STABLE_FRAMES_REQUIRED = 8


def new_capture_state(employee_id, created):
    return {
        "MaNV": employee_id,
        "embeddings": [],
        "sample_images": [],
        "created": created,
        "current_pose_index": 0,
        "stable_frame_count": 0,
    }


def current_pose_index(state):
    index = state.get("current_pose_index", len(state.get("embeddings", ())))
    if type(index) is not int or index != len(state.get("embeddings", ())):
        raise ValueError("Enrollment pose index and captured sample count are inconsistent.")
    return index


def observe_frame(state, ready):
    """Advance only on a fully valid frame; any rejected frame breaks stability."""
    if not ready:
        state["stable_frame_count"] = 0
    else:
        count = max(0, int(state.get("stable_frame_count", 0)))
        state["stable_frame_count"] = min(STABLE_FRAMES_REQUIRED, count + 1)
    return {
        "ready": bool(ready),
        "stable_frame_count": state["stable_frame_count"],
        "stable_frames_required": STABLE_FRAMES_REQUIRED,
        "capture_due": state["stable_frame_count"] >= STABLE_FRAMES_REQUIRED,
    }


def reset_stability(state):
    state["stable_frame_count"] = 0


def record_sample(state, pose, vector_bytes, image_bytes):
    """Record a paired vector/image only after eight ready frames for its pose."""
    index = current_pose_index(state)
    if index >= len(ENROLLMENT_POSES):
        raise ValueError("All five enrollment poses have already been captured.")
    if state.get("stable_frame_count", 0) < STABLE_FRAMES_REQUIRED:
        raise ValueError("Eight consecutive ready frames are required before capture.")
    expected_pose = ENROLLMENT_POSES[index]
    if pose != expected_pose:
        raise ValueError(f"Expected pose {expected_pose}, received {pose}.")
    if not isinstance(vector_bytes, bytes) or not vector_bytes:
        raise ValueError("Enrollment embedding bytes are invalid.")
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("Enrollment image bytes are invalid.")

    state.setdefault("sample_images", []).append(image_bytes)
    state["embeddings"].append(vector_bytes)
    state["current_pose_index"] = index + 1
    state["stable_frame_count"] = 0
    return {
        "captured": index + 1,
        "total": len(ENROLLMENT_POSES),
        "next_pose": ENROLLMENT_POSES[index + 1] if index + 1 < len(ENROLLMENT_POSES) else None,
        "complete": index + 1 == len(ENROLLMENT_POSES),
    }
