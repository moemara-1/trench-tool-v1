# Topic Delivery Recovery Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task.

**Goal:** Restore confirmed, retryable delivery for the Telegram topics identified in the screenshot.

**Architecture:** Isolate V2 topic-send failures so one bad thread cannot abort a polling cycle; route wallet candidates to their period topic; reconcile stale topic IDs and preserve Feedback; only mark V1 DEV Held candidates after a confirmed send; deploy V1 and V2 together.

**Verification:** Add regression coverage for each failure mode, run focused tests, compile changed Python, and validate Compose syntax where Docker is available.
