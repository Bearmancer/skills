# After approval

Load this when `Approve plan` is answered `Yes` (full path), or when a light plan is in place and you start the edits.

## Carry on into the build

Do not stop and wait. Approval is the go-ahead: start the first task whose `Depends:` are all ticked, in plan order. (This is an instruction to you; the system does not make you go on.)

For each task, one at a time:

1. Read the task, the criteria it covers, and the plan's `## Seams`, `## Decisions` and `## Checkpoints`.
2. Work test-first at the agreed seams: write the test for the covered criteria, watch it fail for the right reason, then write the least code that makes it pass. Expected values come from the spec or a worked example, never from recomputing what the code does.
3. Touch only the paths listed in this task's `Edits:` and `Creates:`. Do not tidy nearby code. Note anything else you noticed in chat and leave it.
4. Keep it simple. The naive correct version first. No abstraction for a use that does not exist yet.
5. Run the task's `Verify:` command and the project's standing checks. Do not tick the task until they pass and you have seen the output.
6. Tick the task: change `- [ ]` to `- [x]`. That, and edits to `## Review`, are the only plan changes allowed now.
7. At a checkpoint, report in a few lines what is done and what was checked.

If a task fails twice with two different approaches, stop and ask through the question tool: the preview says what failed and what you tried; the options are two ways forward, your recommendation first.

Never lower the quality bar to get a task green: no new skipped tests, suppressions or removed assertions, and no thresholds edited down. That is a question for the user.

## The plan is read-only

Once approved, the plan is frozen apart from ticks and `## Review`. Writes to other files are allowed only for paths named in some task's `Edits:` or in a `Creates:` entry or glob. A blocked write says what to do: ask with `Amend plan`.

## Amendments

When the work needs something the plan does not allow (a new file, a changed task, a changed criterion):

1. Ask with header `Amend plan`. In the preview say exactly what will change and why. First option: "Yes, amend the plan". Second: "No, keep the plan as it is".
2. On `Yes`, edit the plan. Keep the change as small as possible.
3. Read the status note that comes back.
   - **Behaviours and criteria unchanged:** the approval moves to the new text automatically, as long as the drafted checks still pass. The window closes with your first edit to a project file.
   - **A new claim needs evidence:** a `cmd:` or `doc:` claim added in an amendment has no recorded run or fetch yet, so the approval cannot move and the note says `drafting` with that claim listed. Run the command or fetch the page now (evidence is recorded only while the note says intent or drafting), then write the plan again with a small edit so the approval moves, or ask `Approve plan`.
   - **A behaviour or criterion changed:** the approval is dropped and review restarts with a fresh round count. Run both reviewers again on the new text (review.md), resolve the findings, and ask `Approve plan` again. Do not touch project files until the note says the stage is build (that is what "approved" means).
   - **The Intent changed:** ask `Sign intent` again first, then review only if the behaviours or criteria also changed, then `Approve plan` as above.
   - **The note lists gaps:** fix exactly those.
   - **An edit slipped through and broke the approval:** the note says the approval was dropped. Fix the gaps and ask `Approve plan` again.

Dark mode example: the user wants the switch on the profile page too. That adds a file, so `Amend plan` (add the file to T-1's `Edits:`). If it also adds a behaviour ("B-3: ... the profile page shall ..."), review restarts.

Do not amend by writing a different file name, by shell redirection or by editing outside the allowed paths.

## A different job appears

If the user wants a second, separate piece of work while this plan is unfinished, do not start another plan. Ask with header `Replace plan`: "Yes, drop the current plan and start the new one" or "No, finish the current plan first". On `Yes`, the next plan you write may use a new `name:`, or, while the old plan is not yet approved, the same name with a different Intent. Once the old plan is approved (the build), a same-name rewrite is blocked and the new plan needs a new `name:`. Say in the preview what happens to unticked tasks (they are abandoned). One `Yes` replaces one plan, with the first plan write after it.

The new plan starts clean: the old answers, the Intent sign-off, any approval and the old command and fetch evidence are dropped, so re-ask the questions its `Q-n` lines mark answered and re-run the commands and fetches its claims cite (evidence recorded after the user's `Yes` is kept). A first word `quick` or `full` applies only to the plan it was typed for; type it again for the new one. `.rigor/map.md` stays. Nothing is logged for the dropped plan: there is no `done.log` line for it.

## Closing the plan

When every task is ticked, or the user wants to stop:

1. Check the standing bar once more for the whole change and look at the output.
2. Say in two or three lines what was done, what was verified, and anything left open.
3. Ask with header `Close plan`.
   - All tasks done: "Yes, close it as done" and "No, keep the plan open".
   - Tasks left: "Yes, abandoned: close it with the tasks unfinished" and "No, keep the plan open". The outcome in the log is `abandoned` if the label says abandoned (a light plan too); otherwise `done` if every task is ticked or the plan is light; otherwise `closed`.
4. On `Yes`, the plan, the map and all working state are deleted and one line is added to the done log: the date, the plan name and the outcome. That is the only record kept.

A light plan closes the same way once its steps are done.

## Light path while editing

With a light plan in place you may edit only the files under `## Files`. If you need another file, a block says so. Either rewrite the plan as `path: full`, or ask the user through the question tool and then add the file to `## Files` directly (`Amend plan` is for the build stage only). Do not widen the list silently; the light check still applies to the longer list.

## A one-file job while a plan is open

Edits are blocked. Ask through the question tool: fold it into the plan, or finish and close the plan first (`Close plan`). Folding in: in the build ask `Amend plan` and then edit the plan. In the intent, drafting or light stages `Amend plan` does nothing; add the file to the plan directly: in drafting a task's `Edits:`, in a light plan `## Files`. In the intent stage no tasks exist yet, so ask the user and record the file in the Intent lines or as a question. Do not edit it from a shell.

## Closing, dark mode example

T-1 and T-2 are ticked and their Verify commands passed. The `Close plan` preview lists both tasks and the checks. On `Yes`, the log gets `2026-11-10 dark-mode-settings done`.
