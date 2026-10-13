# PERMANENT PROJECT RULES FOR AUTONOMOUS AGENTS

This document defines the operational rules for all autonomous software engineering agents working on the Football Intelligence platform.

---

## 1. PROJECT_SPEC.md is the master product specification.

All product requirements, architectural decisions, technology choices, and implementation priorities are defined in PROJECT_SPEC.md. Agents must read and follow this specification.

---

## 2. Always inspect existing files before editing them.

Never modify a file without first reading its current content. Do not assume the structure or content of a file.

---

## 3. Never delete or overwrite working code without a clear reason.

If code exists and functions correctly, preserve it. Only modify or remove code when there is a specific technical justification.

---

## 4. Work in small, verifiable steps.

Break implementation work into discrete, testable units. Complete one step before moving to the next.

---

## 5. Do not attempt to implement the entire project in one task.

The project is large and complex. Focus on completing one vertical slice or feature area at a time, as defined by the PHASE structure in PROJECT_SPEC.md.

---

## 6. After every meaningful implementation step, run the relevant tests/build/verification.

Do not accumulate unverified changes. After implementing functionality, immediately verify it works by running appropriate commands (tests, build, linting, type checking, etc.).

---

## 7. Never claim "implemented", "tested", or "working" unless it was actually verified.

If you did not execute a verification command and observe its successful output, do not claim the work is complete or functional.

---

## 8. Keep development/mock data explicitly labeled as mock/development data.

When creating test data, sample data, or mock providers, clearly mark them as such in code comments, variable names, class names, and UI labels.

---

## 9. Never present mock data as real football data.

Mock data must never be displayed to users as if it were live or historical football information. Label mock data appropriately in the interface.

---

## 10. Never invent statistics, probabilities, odds, injuries, lineups, player information, match events, or model results.

Numerical values must come from actual calculations or real data sources. Do not generate placeholder statistics that appear to be meaningful.

---

## 11. Numerical prediction engines are the source of truth.

All predictions must be derived from mathematical models, statistical calculations, or data analysis. Predictions are not opinions or estimates.

---

## 12. AI Analyst is only an explanation layer over structured AnalysisContext.

The AI Analyst component receives a structured AnalysisContext object containing all relevant data and model outputs. It explains this context in natural language. It does not generate new predictions or statistics.

---

## 13. AI Analyst must never modify supplied numerical values.

When the AnalysisContext contains a probability of 0.67, the AI Analyst must not round it, adjust it, or present it as a different value. Report numerical values exactly as supplied.

---

## 14. Missing information must be explicitly represented as unavailable/insufficient data.

When a piece of information does not exist (e.g., player injury data, xG values, historical head-to-head), the system must explicitly indicate this absence. Do not substitute null values with zeros or empty strings that could be misinterpreted.

---

## 15. Backend must use Python + FastAPI + Pydantic + SQLAlchemy.

These are the mandated backend technologies. Do not introduce alternative web frameworks, validation libraries, or ORMs.

---

## 16. Database architecture must remain PostgreSQL-ready.

The database models and migrations should be designed for PostgreSQL. Development environments may use SQLite or mock data, but the architecture must not be compromised.

---

## 17. Frontend must use React + TypeScript + Vite.

These are the mandated frontend technologies. Do not introduce alternative frameworks or build tools.

---

## 18. AI integration must use the provider abstraction defined by PROJECT_SPEC.md.

The AI integration architecture must support Ollama as specified (model: qwen3-coder:30b, endpoint: http://127.0.0.1:11434). The implementation must use a provider abstraction layer even though only Ollama is currently supported.

---

## 19. Do not add OpenAI, Gemini, Claude, or other external AI APIs to the application.

This project uses only local Ollama. Do not add dependencies or code for external AI services.

---

## 20. Keep technical identifiers in English and user-facing UI primarily Turkish.

Code (variable names, function names, class names, file names, API endpoints) should be in English. User-facing text in the interface should be Turkish as specified in PROJECT_SPEC.md section 27.

---

## 21. Maintain modular architecture and avoid unnecessary monolithic files.

Organize code into appropriate modules, packages, and components. Do not place the entire backend or frontend into single files.

---

## 22. Add tests progressively as functionality is implemented.

Write tests for new functionality as it is developed. Tests should cover the critical mathematical and logical components specified in PROJECT_SPEC.md section 30.

---

## 23. Fix errors found during verification instead of merely reporting them.

When a build fails, a test fails, or a linter reports errors, diagnose the problem and fix it. Do not simply report the error to the user and stop.

---

## 24. Do not move to the next major phase until the current phase is verified.

Follow the phase structure in PROJECT_SPEC.md sections 31-36. Complete and verify each phase before beginning the next.

---

## 25. Update docs/PROGRESS.md after each completed implementation step.

After completing and verifying a meaningful unit of work, append an entry to docs/PROGRESS.md documenting what was done, how it was verified, and what comes next.

---

## SUMMARY

These rules exist to ensure:

- The product is built according to specification
- Work is verified continuously
- Data integrity is maintained
- The numerical engine remains authoritative
- The codebase stays maintainable and extensible
- Progress is documented
- Agents act autonomously but responsibly

Read PROJECT_SPEC.md and follow these rules.
