# PDF Rendering Stabilization Plan

This document outlines a focused plan to stabilize the PDF generation process in `pdf_generator.py` and prevent `FPDFException: Not enough horizontal space` errors.

## 1. Failure Scenario Analysis

The root cause of the error is attempting to render a string that is wider than the available horizontal space in a PDF cell. This can be caused by:

-   **Long, Unbreakable Strings:** A single word, URL, or token that is longer than the cell's width.
-   **Malformed Unicode:** Certain Unicode characters can have a surprisingly large width or cause calculation errors in the FPDF library.
-   **Incorrect Width Calculations:** The available width for the text is miscalculated, leading to an overflow.

## 2. Audit of `pdf_generator.py`

-   **Unsafe `multi_cell` Usage:** The code primarily uses `pdf.cell` within the `_write_lines` function. While `multi_cell` is not used directly, the underlying issue of text overflow is the same. The focus of the audit will be on the `_write_wrapped` function and its callers.
-   **Width/Margin Calculation Risks:** The use of hardcoded `width` values (e.g., 70, 95, 100) in calls to `_write_wrapped` is a major risk. These values do not account for the page margins and can easily lead to overflows.
-   **Unsafe Text Inputs:** All string data from the `Job` object (title, company, location, description, URL) is a potential source of unsafe input.
-   **URL Wrapping Risks:** URLs are the most likely cause of the issue, as they are often long and lack spaces. The `_break_long_tokens` function is a good first step, but it may not be aggressive enough.
-   **Unicode Normalization Risks:** The `clean_text` function provides a solid baseline for Unicode normalization, but it may not cover all edge cases.

## 3. Minimal Fix Strategy

The proposed strategy focuses on minimal, targeted changes to improve rendering resilience without major refactoring.

### 3.1. Safe Text Wrapping Strategy

1.  **Enhance `_break_long_tokens`:** Modify this function to be more aggressive, especially for URLs. It should break long strings at any character, not just on word boundaries, if necessary.
2.  **Dynamic Width Calculation:** Replace all hardcoded `width` values in `_write_wrapped` calls with a dynamic calculation of the available width, such as `pdf.w - pdf.l_margin - pdf.r_margin`.

### 3.2. Defensive Rendering Guards

1.  **Pre-render Width Check:** Before calling `pdf.cell`, check if the width of the string exceeds the available cell width. This can be done using `pdf.get_string_width()`. If the string is too wide, truncate it and append an ellipsis.
2.  **Granular Error Handling:** Wrap the code that renders each job entry in a `try...except FPDFException` block. This will allow the system to catch rendering errors for a single job, log the problematic job data, and continue processing the rest of the jobs.

### 3.3. Graceful Fallback Behavior

-   If a job entry fails to render, the error handling block will log the full job data for later inspection and then simply `continue` to the next job in the loop. This ensures that a single bad job entry does not terminate the entire PDF generation process.
-   The existing `_write_fallback_pdf` function will be kept as a top-level fallback in case of catastrophic failures.

## 4. Implementation Steps

1.  Update the `_break_long_tokens` function to be more aggressive.
2.  Refactor all calls to `_write_wrapped` to use dynamic width calculation.
3.  Implement a pre-render width check and truncation mechanism.
4.  Add granular `try...except` blocks around the job rendering loop.

This strategy will significantly improve the resilience of the PDF generation process with minimal changes to the existing code.
