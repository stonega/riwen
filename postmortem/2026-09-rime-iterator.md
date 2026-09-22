# Fixture hid a Rime iterator mismatch

## Symptom and cause

The Lua filter passed fixture tests but failed with actual librime candidates.
The fixture returned a zero-argument closure from `translation:iter()`. Rime
returns a generic-for iterator with state and control values. Calling only its
first return value discarded the required iterator state.

## Correction

The filter now retains and passes the iterator triple while buffering the first
eight candidates. The fixture requires state too. `test:rime` loads real librime,
the matching Lua plugin, LuaSocket, and the user's static 小鹤 dictionary assets
inside a disposable profile. It verifies ranking, stale-response rejection,
navigation freeze, normal Space commit, and absent-service fallback. `test:ibus`
adds actual D-Bus lookup-table updates and focus/private-field checks.

This run also exposed Lua 5.5's const generic-for variables in the user's old
`aux_code.lua`. Preparation adapts only the isolated copy; it does not repair or
replace the active profile. Fixture tests remain useful but are insufficient
evidence for the native boundary.
