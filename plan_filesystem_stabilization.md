# Filesystem Stabilization Plan

This document outlines a focused plan to stabilize the filesystem operations in the JobAgent247 project and prevent `FileNotFoundError` errors during file saving.

## 1. Audit of File Save Operations

-   **`designer.py`**: Saves carousel images to `assets/carousels/<timestamp>/slide_XX.png`. The timestamped directory is not being created before the save operation.
-   **`pdf_generator.py`**: Saves PDFs to the `docs/` directory. The `safe_path` utility is used here, which correctly creates the `docs/` directory if it doesn't exist.
-   **`video_maker.py`**: Saves videos and thumbnails to `assets/videos/<timestamp>/`. This is likely to have the same issue as `designer.py`.

## 2. Root Cause Analysis

The `FileNotFoundError` in `designer.py` is caused by an incorrect use of the `safe_path` utility. The `safe_path(out_dir)` call only ensures that the parent directory (`assets/carousels/`) exists, not the final timestamped directory (`assets/carousels/<timestamp>/`).

## 3. Minimal Safe Fix Strategy

The proposed strategy focuses on a minimal, safe fix to ensure that all output directories are created before any file-saving operations.

### 3.1. Centralized Directory Creation

We will introduce a new utility function in `file_utils.py` specifically for creating directories:

```python
def ensure_dir_exists(path: str | Path) -> None:
    """
    Ensures that a directory exists, creating it if necessary.
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise FileSystemError(f"Failed to create directory {path}: {exc}") from exc
```

This function will be used to explicitly create the output directories in `designer.py` and `video_maker.py`.

### 3.2. Implementation Steps

1.  **Add `ensure_dir_exists` to `file_utils.py`**: Implement the new function as described above.
2.  **Update `designer.py`**: In the `build_carousel` function, replace the `safe_path(out_dir)` call with `ensure_dir_exists(out_dir)`.
3.  **Update `video_maker.py`**: In the `main` function and any other relevant places, add a call to `ensure_dir_exists(out_dir)` before any files are saved.

This approach is:

-   **Safe and Minimal:** It directly addresses the root cause of the problem with a small, targeted change.
-   **Robust:** It centralizes the directory creation logic in a reusable utility function.
-   **Compatible:** It maintains the existing pipeline behavior and does not introduce any new dependencies.

This strategy will resolve the `FileNotFoundError` and improve the overall reliability of the filesystem operations.
