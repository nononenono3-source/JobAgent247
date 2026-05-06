# Phase 1 Detailed Implementation Plan

This document provides a detailed plan for the implementation of Phase 1 of the JobAgent247 modular monolith.

## 1. File Responsibilities

-   **`jobagent247/orchestrator.py`**: The main entry point of the application. It will be responsible for orchestrating the entire ingestion pipeline, from fetching to saving the data. It will also handle configuration management.
-   **`jobagent247/ingestion/adzuna.py`**: This file will contain the `AdzunaClient` class and the `fetch_jobs` function, responsible for interacting with the Adzuna API. It will include the retry-safe fetching logic.
-   **`jobagent247/ingestion/cleaning.py`**: This module will contain all the data cleaning and normalization functions, such as `categorize_job`, `estimate_years_experience`, etc.
-   **`jobagent247/state/db.py`**: This module will be responsible for all interactions with the state file (`data/jobs.json`). It will contain functions for saving and loading jobs, as well as the deduplication logic.
-   **`jobagent247/state/models.py`**: This file will contain the canonical `Job` data model.
-   **`jobagent247/utils/logging.py`**: A centralized logging utility for the entire application.

## 2. Ingestion Lifecycle

1.  The `orchestrator` is executed.
2.  It loads the configuration (e.g., from environment variables).
3.  It calls the `fetch_jobs` function from the `ingestion.adzuna` module.
4.  `fetch_jobs` makes API calls to Adzuna, with retry logic in case of failures.
5.  The raw job data is returned to the `orchestrator`.
6.  The `orchestrator` passes the raw data to the cleaning functions in the `ingestion.cleaning` module.
7.  The cleaned and normalized list of `Job` objects is returned to the `orchestrator`.
8.  The `orchestrator` passes the list of jobs to the `state.db` module to be saved.
9.  The `state.db` module loads the existing jobs, performs deduplication, and saves the new, unique jobs.

## 3. Retry Lifecycle

The retry logic will be implemented in the `fetch_jobs` function in `jobagent247/ingestion/adzuna.py`.

-   When an API call to Adzuna fails (e.g., due to a network error or a non-200 status code), the function will wait for a specified delay and then retry the request.
-   The number of retries and the delay between retries will be configurable.
-   If all retries fail, the function will log the error and gracefully continue to the next page of results, ensuring that a single failure does not stop the entire ingestion process.

## 4. Deduplication Strategy

The deduplication logic will be in the `state.db` module.

1.  Before saving new jobs, the existing jobs will be loaded from the state file.
2.  A set of unique identifiers for the existing jobs will be created. The unique identifier will be a hash of the job's title, company, and location.
3.  For each new job, a unique identifier will be calculated.
4.  If the identifier is not in the set of existing identifiers, the job will be added to the list of new jobs to be saved.
5.  The final list of new, unique jobs will be appended to the state file.

## 5. State Persistence Design

-   The state will be persisted in a single JSON file: `data/jobs.json`.
-   This file will contain a list of all the jobs that have been fetched and processed.
-   The `state.db` module will be the single point of access to this file, ensuring that all read and write operations are centralized and consistent.

## 6. Graceful Failure Handling

-   **Retry Mechanism:** The retry logic in the `ingestion` module will handle transient failures.
-   **Logging:** All errors and warnings will be logged using the centralized logging utility.
-   **Continue on Failure:** The ingestion process will be designed to continue even if some API calls fail, ensuring that the pipeline is as robust as possible.

## 7. Migration Risks

-   **Data Loss:** The main risk is data loss if the new implementation fails to correctly read the existing `data/jobs.json` file. To mitigate this, we will create a backup of the existing data before running the new implementation for the first time.
-   **Behavioral Changes:** There is a risk of subtle changes in behavior due to the refactoring. Thorough testing will be required to ensure that the new implementation is functionally equivalent to the old one.

## 8. Dangerous Refactors

-   The most dangerous refactor is the change in the data model. However, the user has already completed this step.
-   The other refactoring steps are relatively safe, as they involve moving code between files and modules without changing the core logic. We will proceed with small, incremental changes and test each step thoroughly.
