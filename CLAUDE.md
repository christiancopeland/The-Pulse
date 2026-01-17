# The-Pulse

## Project Overview

A comprehensive research and news monitoring platform that empowers journalists, investigators, and private citizens to conduct deep research while staying informed about relevant current events through automated tracking and analysis. This project is quickly developing into a more rich intelligence discovery, ingestion, and analysis platform that Christian is using to replace all other forms of media consumption. The point of this system is to sift thru the noise in the world, extract as much signal as possible to dramatically increase the ROI of time invested in learning/consuming.  

---

## Environment Setup

*Add environment setup instructions here*

---

## Key Commands

```bash
# Add project-specific commands here
```

---

## Useful Context Files

- `HANDOFF.md` - Last session's state (read first!)
- `LLM_CONTEXT.md` - Architecture reference
- `CHANGELOG.md` - Session history for debugging
- `LEARNED_PREFERENCES.md` - Evolved rules from corrections

# Session Management

## Session Start
Always begin by reading these files in order:
1. `HANDOFF.md` - Last session's state and immediate context
2. `LLM_CONTEXT.md` - Architecture and design decisions
3. `LEARNED_PREFERENCES.md` - Evolved rules from past corrections
4. Active `PLAN_*.md` - Current implementation plan (if one exists)

## Session End
Before ending any session, you MUST:
1. Generate/update `HANDOFF.md` with current state
2. Append entry to `CHANGELOG.md`
3. Update `LLM_CONTEXT.md` if architecture changed
4. Update active plan with progress
5. Propose learned preferences if patterns detected (show diff, wait for approval)

This is NOT optional. Do not end a session without these artifacts.

## Context Monitoring
Monitor context utilization throughout the session:
- At ~75% utilization (40+ turns or 90+ minutes of active work)
- Proactively trigger handoff workflow
- Alert user: "Approaching context limits, generating handoff..."

---

# New Feature Workflow

## Mandatory Interview
When user requests a new feature, ALWAYS conduct interview first:

1. **Clarify** (2-3 questions max):
   - What does success look like?
   - What are the constraints?
   - What have you tried?

2. **Confirm**: Paraphrase understanding back to user

3. **Determine scope**:
   - Quick fix: Proceed directly
   - Medium: Create implementation checklist
   - Large: Create full spec + plan

4. **Get confirmation** before implementing

Skip ONLY if user explicitly says "skip interview" or "just do it".

## Bug Fixes
Bug fixes do NOT require interview. Proceed directly to:
1. Understand the bug (read relevant code)
2. Identify root cause
3. Implement fix
4. Verify fix works

---

# Documentation Standards

## HANDOFF.md (Hot Context)
- Overwritten each session
- Contains: what was done, current state, next steps, files to read
- Target length: 300-500 words

## LLM_CONTEXT.md (Warm Context)
- Updated only when architecture changes
- Contains: system architecture, data flows, design decisions
- Should NOT contain changelog entries

## CHANGELOG.md (Cold Context)
- Append-only (new entries at top)
- Contains: session history, decisions, files modified
- Searchable for debugging

## LEARNED_PREFERENCES.md (Evolving)
- System proposes additions based on corrections/patterns
- Human approves via diff review before any modification
- Never auto-modify - always show diff and wait for approval

---

# Learned Preferences System

This project uses a two-layer instruction system:
- `CLAUDE.md` (this file): Stable rules, human-authored
- `LEARNED_PREFERENCES.md`: Evolved rules, human-approved

## Rules for Learning:
1. NEVER modify CLAUDE.md - only humans edit the constitution
2. NEVER auto-append to LEARNED_PREFERENCES.md - always show diff first
3. Propose preferences when:
   - User explicitly corrects behavior
   - Same pattern observed 3+ times
   - User states "from now on" or similar
4. Always include:
   - The proposed rule text
   - A diff showing exactly what will be added
   - The source (correction, pattern, explicit instruction)
   - Options to Approve/Modify/Reject/Defer

## Preference Proposal Format:
```
PREFERENCE PROPOSAL

I noticed a pattern that might be worth codifying:

Observation: {what triggered this}

Proposed addition to LEARNED_PREFERENCES.md:

```diff
## {Section}

### {Subsection}
+ - {New preference text}
+ - Added: {date}, Source: {source}
```

Options:
[A] Approve - Add this preference
[M] Modify - Edit before adding
[R] Reject - Don't add, this was situational
[D] Defer - Remind me later
```
