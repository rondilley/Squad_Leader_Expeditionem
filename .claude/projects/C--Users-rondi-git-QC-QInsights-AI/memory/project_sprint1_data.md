---
name: Sprint 1 - Data Pull Analysis Complete
description: Comprehensive analysis of the 12-8-2025 data pull - 10 files, 90K+ cases, 1565 clients
type: project
---

Data pull from 2025-12-08 contains 10 files (CSVs + 1 XLSX). Key findings:

- Case Data: 90,008 support tickets across 233 clients, 16 months of data, 217 case types in 15 categories
- Client List: 1,344 active/under-contract clients across TX, SC, AZ, NC primarily
- CSR Mapping: 1,565 clients mapped to ~20 role columns across 8 departments (XLSX)
- Alert Data: 70 at-risk client records with termination forecasts
- Termination Data: 153 records for 147 terminated clients (zero overlap with active list)
- Visit Data: Two versions (v1: 401 clients, v2: 232 clients) with different schemas and minimal overlap
- Survey Data: 74 records, all from 2020-2021 (stale)
- LOA Data: Empty (failed export)
- Parent Relationships: 491 parent-child company mappings

**Why:** This is the foundation data for the QInsights POC. Understanding it completely is prerequisite to building anything.
**How to apply:** All analysis and dashboard generation must work against these data shapes. Data quality issues (string types, NULL literals, trailing spaces, stale surveys) must be handled in the extraction/cleaning layer.
