---
title: Untitled
type: note
permalink: toolguard/too-8/untitled
---

Taking a note for myself of open issues before we can close out TOO-8 (just a copy/paste from a claude session)

● Here's the full open-items list, boss — everything still pending before we dive into TOO-17.                                                                                                                     
                                            
  The blocker we're diverting to                                                             
  - TOO-17 — multi-line Bash fail-open bypass. Show-stopper. Blocks publishing the docs. Task memory written; not started. Its scope includes the multi-line doc updates (permission-patterns.md compound section +
  security.md), so those are intentionally not in the current docs pass.                                                                                            
  Code follow-ups (TOO-8 tail, not started)                                                        
  1. Migrate scripts/migrate_permissions.py off load_takeover_mode_config → Configuration.takeover_mode, then delete the last legacy loader.                                                                       
  2. Coverage gap: confirm the live hierarchical Bash takeover-filtering path is covered by newer tests (the removed legacy _load_permissions tests used to exercise it).                                          
                                                                                                                                                                                                                   
  Docs / publication state                                                                                                                               
  1. Publication blocked on TOO-17. The rest of the Phase 7 doc restructure is done (thin README + docs/ split, agent-guides, llms.txt/AGENTS.md, install/hooks incl. global setup, recognition-vs-governance,     
  ignored_allow_patterns, config-sync "divergence is normal," security review + maintenance practices, patterns→permission-patterns rename, Alpha removed).                                                        
  2. run_hook.sh retirement = TOO-16, deliberately not done (docs reference the entry points; the file stays, marked legacy in architecture.md).                                                                   
                                                                                                                                                                                                                   
  Git state (yours to do)                                                                         
  1. Everything is uncommitted. docs/ is now git-tracked; the patterns.md → permission-patterns.md rename was a plain mv and needs staging (git will detect the rename). New/modified: all docs/*, README,         
  technical-notes, the TOO-8 plan memory, and the new TOO-17 task memory.                                                                                                    
  Offered but not added (your call later)                                                                                                                                                                          
                                                                                    
  2. Security-maintenance recommendations #5–7 (prune obsolete rules; test-denies-fire / re-verify after upgrades; single-owner for takeover/hard_deny).                                                           
                                                                                                                                                                                                                   
  Future, separate ticket                                                                                                                                                                                            
  1. TOO-16 — uv tool install packaging/testing + actual run_hook.sh retirement.                                                                                                                                                                                                                         
  While pulling this, I noticed a duplicated "Follow-ups still open" header in the plan memory — let me tidy that.