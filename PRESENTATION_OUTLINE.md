# Agentic Playbook Building — Presentation Outline

Working title: **Agent-Authored Playbooks for FortiSOAR — AI is the driver, but the deterministic cornerstones are why it works**

Audience: SOAR engineers, automation leads, and stakeholders who already know FortiSOAR but have not seen agent-driven authoring.
Length target: ~30 slides, 35-minute talk.

Last updated: 2026-05-09.

Re-build with `python scripts/build_presentation.py` (writes `fsrpb_presentation.pptx`).

📷 = screenshot to capture.  🎨 = built-in diagram (already rendered by the script).

---

## Section 1 — Framing (Slides 1-3)

**1. Title** — Agent-Authored Playbooks for FortiSOAR
- 📷 _Optional_: hero shot of the visual editor with a colorful playbook on canvas + diagnostics drawer open. Place behind a translucent panel so the title still reads.

**2. The pain we keep hitting**
- 📷 FortiSOAR Playbook Designer with a moderately complex playbook open — focus on the visual clutter, the small text, the lack of diff. A cropped before/after pair (Designer vs. our YAML in Monaco) sells the point.

**3. The product principle**
- 📷 _Optional_: a `git diff` of a playbook YAML change in your terminal or a GitHub PR review screen. Reinforces "valid YAML in git" as the goal.

## Section 2 — AI is the driver, but only because the chassis works (Slides 4-6)

**4. Why AI is the right driver here**
- 📷 Chat panel showing a one-line user ask ("enrich every alert with VirusTotal") and the agent's first 2-3 tool calls (`find_recipe`, `find_connector`, `get_op_schema`). Crop to just the conversation.

**5. But this is more than "just AI"**
- 📷 Side-by-side: left = a plausible-looking YAML the LLM wrote alone (with a typo in `vars.steps.X.statuss`); right = `analyze_playbook` output catching it. Caption: "what AI gives you" vs "what AI + cornerstones gives you".

**6. The cornerstones (six pillars under the AI layer)**
- 🎨 Consider drawing a quick layered-cake diagram in Keynote/PowerPoint over the bullets — AI on top, cornerstones as colored bricks underneath. Or just leave the bullets; this slide reads fine textual.

## Section 3 — Cornerstones (Slides 7-14)

**7. The core idea**
- 🎨 Built-in `core` diagram (three surfaces → YAML IR → compiler → FSR JSON). No screenshot needed.

**8. Why YAML is the right IR**
- 📷 Monaco editor showing a real playbook YAML — pick something with `for_each`, a Decision, and a couple of `vars.steps` references so the structure is visible. Syntax highlighting + line numbers helps.

**9. Cornerstone 1 — SQLite-first reference store**
- 📷 `fsrpb find_connector jira` and `fsrpb find_operation jira get_ticket_details` CLI output side-by-side. Or, the `/inventory` page in the web app if it's polished enough.

**10. Cornerstone 2 — Library-first compiler**
- 📷 A `validate_yaml` failure with a structured diagnostic — line/col, code, message, suggestion. Show the error pointing into the YAML. Either CLI output or the Monaco red squiggle.

**11. Cornerstone 3 — Render-path validator**
- 📷 `fsrpb analyze /tmp/test.yaml` showing 3-4 diagnostics across kinds (unreachable_var_path, missing_key, picklist_drift). Use the deliberately-broken example we tested earlier — it nails the demo. Bonus: include the suggestion lines so the close-key heuristic shows.

**12. Cornerstone 4 — Live-FSR probes ground simulator truth**
- 📷 Either: (a) `python -m probes.probe_render_path --scenario for_each_break_loop` running with the "saved → fixtures/.../for_each_break_loop.json" line visible; or (b) snippet of one of the captured fixtures showing `loop_seen: [{current: 1, ...}, {current: 2, ...}]` next to a slide of the rendered playbook YAML that produced it.

**13. Cornerstone 5 — Step-param audit**
- 📷 The INDEX.md table from `docs/step_params/INDEX.md` — easy to read and shows the gap counts column. Or open one specific report (FindRecords.md is the spiciest because of the `query` gap) and screenshot the "Unrecognized keys" section.

**14. Cornerstone 6 — MCP as the agent contract**
- 📷 _Optional_: terminal showing `curl POST /api/mcp/find_connector` returning JSON. Or a Claude Code chat where the tool call + structured response are visible. Either makes the "any client" point.

## Section 4 — The success ladder + agent integration (Slides 15-19)

**15. The success ladder**
- 🎨 Built-in `ladder` diagram. No screenshot needed.

**16. The agent prompt — workflow gates that close the loop**
- 📷 Excerpt from `python/agent/system_prompt.md` — the new "Required workflow" section showing steps 6-7 (the analyze gate + execute_safe_ops auto-trigger). Crop to ~15 lines so the rules are readable. Highlight step 6 with a colored box overlay.

**17. Two distinct agent flows**
- 🎨 Built-in `agent_flow` diagram. No screenshot needed; the flow lanes render directly on the slide.

**18. The visual editor closes the loop for humans**
- 📷 **High-priority screenshot.** The visual editor with: (a) red badges on 2-3 nodes that have diagnostics; (b) the diagnostics drawer open showing render-path rows; (c) one row expanded with the "Suggest fix" before/after diff visible. This is the headline visual — spend the time to make it look good.

**19. The full MCP toolbelt — 49 tools**
- 🎨 Built-in `tool_catalog` 5-column layout. No screenshot needed.

## Section 5 — Reach + roadmap (Slides 20-23)

**20. Recipes — from blank page to working playbook**
- 📷 `fsrpb generate-recipe threat-feed-ingestion --out /tmp/feed.yaml` followed by `head -40 /tmp/feed.yaml` showing the generated playbook. OR the recipe library list (`find_recipe` output).

**21. HTTP virtual-connector — covering the long tail**
- 📷 `fsrpb search-api-examples microsoft graph users` returning 5-6 hits with method/path/auth visible. Optionally next to a `synthesize_http_step` output showing the resulting YAML step pre-filled.

**22. Roadmap — vendor doc ingest (zero-day SaaS support)** _(NEW)_
- 📷 _Optional but compelling_: split-screen of a fresh vendor's OpenAPI spec page (e.g. Stripe, GitHub, Snyk, Wiz, Okta — pick one with a clean spec URL) on the left, and a mock fsrpb output saying "ingested 412 ops · 38 auth flows · ready" on the right. Even if the right side is staged, it sells the future capability vividly.
- Alt: a small grid of 6-8 vendor logos with "supported today" / "after ingest" labels.

**23. Live verification loop**

- 📷 `fsrpb run_op jira get_ticket_details ...` showing the live response inline + a follow-up `verification_status` showing `tested_pass` was recorded.

## Section 6 — Demos (Slides 24-25)

**24. Demo 1 — vague ask to working playbook**
- 📷 Chat transcript scroll: user prompt at top → 4-5 tool calls → final YAML → `analyze_playbook` returns clean → `push` succeeds. A real-time GIF or screen recording works even better than a static screenshot if you can embed it.

**25. Demo 2 — the killer: triage and fix**
- 📷 Visual editor screenshot showing: red badge on a step → drawer with the missing_key diagnostic → "Suggest fix" expanded → green diff. Caption with timestamps if you have them ("18s from open to fixed").

## Section 7 — Numbers + roadmap + close (Slides 26-30)

**26. What we've indexed — FortiSOAR knowledge**
- 🎨 Built-in `stats` grid. No screenshot needed.

**27. What we've indexed — third-party APIs**
- 🎨 Built-in `stats` grid. No screenshot needed.

**28. What's already shipped**
- 📷 _Optional_: terminal showing `pytest` output `407 passed` + `vitest` `214 passed`. Or `git log --oneline | head -20` to show velocity. Reinforces "this is real, not a demo".

**29. What's next**
- _No screenshot — text only._ Keep the slide aspirational, not screenshot-y.

**30. Takeaways**
- 📷 _Optional but powerful_: a small montage of three thumbnails — the analyze CLI output, the visual editor with badges, and the agent chat. Caption: "Same data. Three surfaces. One source of truth." Pulls everything together.

---

## Capture priority

If you're short on time, lock in these in order:

1. **Slide 18** — visual editor with badges + drawer + suggest-fix. The headline.
2. **Slide 11** — `fsrpb analyze` CLI output catching multiple kinds. Sells the cornerstone.
3. **Slide 24** — the "killer demo" triage flow. Closes the deck emotionally.
4. **Slide 5** — broken-without-cornerstones vs caught-with-cornerstones side-by-side.
5. **Slide 16** — system prompt excerpt with the analyze gate highlighted.
6. **Slides 8, 9, 10, 13** — supporting cornerstone visuals.

Everything else is a nice-to-have or already-handled by a built-in diagram.
