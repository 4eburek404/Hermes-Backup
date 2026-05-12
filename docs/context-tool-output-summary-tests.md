# Synthetic Tests for Tool Output Summarization Policy

This document defines test scenarios for the future summarization policy. The goal is to ensure compact, safe, and reversible summarization of tool outputs while preserving critical information and enabling on-demand restoration of raw artifacts.

---

## Test Scenarios

### 1. Terminal Output
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `long_stdout`                 | 1000+ lines of mixed log output (debug, info, warnings)                     | Command, exit code, status, last 20 lines, artifact ref                                | Full stdout written to artifact              | No truncation of critical tail                  |
| `stderr_present`              | Command with non-zero exit code and 50 lines of stderr                      | Command, exit code, status, last error block, artifact ref                             | Full stderr + stdout written to artifact      | Stderr preserved despite exit code              |
| `non_zero_exit`              | Command with exit code 1 and minimal output                                  | Command, exit code, status, artifact ref                                               | Full output written to artifact               | Exit code and status always visible             |
| `last_error_block_preserved`  | Multi-page log with error block at line 800                                  | Command, exit code, status, last error block, artifact ref                             | Full output written to artifact               | Critical errors not truncated                   |
| `command_metadata_in_summary` | Any command output                                                          | Command string, exit code, status, and artifact ref always present                     | Full output written to artifact               | Traceability of origin                          |
| `raw_artifact_pointer`        | Any command output                                                          | Artifact ref (sha256, size, line count) always present                                  | Artifact written and ref valid                | Reversibility guaranteed                        |

---

### 2. File Read
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `large_file`                  | 10,000-line file with relevant lines at 5000-5020                            | File path, line range (5000-5020), artifact ref                                         | Full file written to artifact                 | No truncation of relevant range                 |
| `relevant_line_range_preserved`| File with critical lines at 100-120                                         | File path, line range (100-120), artifact ref                                           | Full file written to artifact                 | Relevant context not lost                       |
| `full_raw_in_artifact`        | Any file read                                                                | Artifact ref (sha256, size, line count) always present                                  | Full file written to artifact                 | Reversibility guaranteed                        |
| `file_metadata_in_summary`    | Any file read                                                                | File path, size, line count, and artifact ref always present                            | Artifact written and ref valid                | Traceability of origin                          |

---

### 3. Repeated Output Deduplication
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `identical_output_dedup`      | Two identical terminal outputs in the same session                           | Second output replaced with: `repeated_from: <sha256 of first output>`                  | First artifact retained, second omitted       | No duplicate artifacts                          |
| `first_artifact_accessible`   | Two identical outputs                                                       | First output: full summary + artifact ref. Second: repeated_from + hash                | First artifact retained and accessible         | Reversibility preserved                         |

---

### 4. Protected Tail
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `critical_tail_not_truncated` | 5000-line log with critical observation at line 4999                        | Last 20 lines (including critical observation), artifact ref                           | Full output written to artifact               | Critical observations not lost                 |
| `truncation_with_restore`     | 5000-line log with no critical tail                                         | First 20 lines, `... (truncated, restore via artifact_ref)`, artifact ref              | Full output written to artifact               | Truncation reversible                           |

---

### 5. Secret Scanning
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `clean_output`               | Output with no secrets                                                     | Full summary, artifact ref                                                                 | Artifact written                               | No false positives                              |
| `1_to_5_matches`             | Output with 3 API keys                                                     | Summary with redacted secrets, artifact ref                                            | Artifact written (secrets redacted)           | Secrets not exposed in summary                  |
| `6_plus_matches`             | Output with 10 database passwords                                          | Summary: `BLOCKED: excessive secret matches (6+)`, artifact_ref: null                   | No artifact written                            | High-risk outputs blocked                       |
| `artifact_ref_null_on_block`  | Output with 6+ secrets                                                     | Summary: `BLOCKED: excessive secret matches (6+)`, artifact_ref: null                   | No artifact written                            | No accidental leakage                           |

---

### 6. Restore-on-Demand
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `artifact_ref_valid`          | Any artifact written                                                        | Artifact ref (sha256, size) always valid                                                | Artifact exists and matches ref               | Reversibility guaranteed                        |
| `sha256_matches`             | Any artifact written                                                        | Artifact sha256 matches ref                                                             | Artifact content matches hash                 | Integrity guaranteed                            |
| `partial_restore_works`       | 10,000-line artifact                                                        | Partial restore (e.g., lines 5000-5020) works                                           | Artifact supports partial restore             | Usability preserved                             |
| `full_restore_explicit`       | 10,000-line artifact                                                        | Full restore only on explicit request                                                    | Artifact supports full restore                | No accidental bandwidth waste                   |

---

### 7. Regression Metrics
| Test Name                     | Input Fixture                                                                 | Expected Compact Summary                                                                 | Expected Artifact Behavior                     | Expected Risk Coverage                          |
|-------------------------------|------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|-----------------------------------------------|-------------------------------------------------|
| `provider_input_reduction`    | 100 tool outputs                                                            | Estimated provider input tokens reduced by ≥30%                                         | All artifacts preserved                        | Efficiency gain                                 |
| `raw_output_not_lost`         | 100 tool outputs                                                            | All raw outputs preserved in artifacts                                                   | All artifacts exist                            | No data loss                                    |
| `pytest_passes`              | Test suite for analyzer                                                     | All tests pass                                                                          | N/A                                           | Correctness guaranteed                          |
| `no_secrets_in_artifacts`     | 100 tool outputs with 5 secrets                                            | All artifacts scanned and redacted if needed                                            | No secrets in artifacts                       | No leakage in artifacts                         |

---

## Fixture Design Notes
- **Terminal Output**: Use `subprocess.Popen` to generate synthetic logs with controlled exit codes, stdout/stderr, and error blocks.
- **File Read**: Use `tempfile.NamedTemporaryFile` to create files with known line ranges and content.
- **Repeated Output**: Duplicate terminal outputs in the same session and verify deduplication.
- **Secret Scanning**: Use `python-dotenv` patterns for API keys, database URLs, and passwords.
- **Artifacts**: Store raw outputs in a temporary directory with sha256 filenames.
- **Restore**: Implement a helper function to fetch partial/full artifacts by ref.

---

## Validation Commands
```bash
# Syntax check
python -m py_compile scripts/analyze_context_overhead.py

# Test suite
pytest tests/test_analyze_context_overhead.py -q

# Diff
git diff --stat
git diff -- docs/context-tool-output-summary-tests.md
```