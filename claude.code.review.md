Code review takes a lot of resources especially from your context windows. To mitigate this we do several things:

* When I ask you to do code review you should first ask me about the scope. The default scope is added and changed
  files in the current task
    * A narrower scope is only files that are staged in git
    * A wider scope would be all python and template files in the project
    * I may also supply a specific python package to review or even a specific file
    * When unclear ask and present a menu to clarify use the AskUserQuestion tool
* Code reviews should be performed by the `code-reviewer` subagent. You shall give it the context of the work that
  was done, the ticket we're working on, and the scope of the review, plus any specific instruction I gave when
  asking for the review. For instance - maybe I was looking for duplicate logic or for circular dependencies.
    * You should instruct the subagent to produce its report in a dedicated memory named `latest-code-review-report.md`
    * In its response to you the agent should only include a brief summary of the results, highlighting the most
      important issues found and limiting the content to no more than 500 words, preferably under 200 words, if it
      fits. Further details will be in the review report memory file.
    * After it's done open the `latest-code-review-report.md` memory file in the IDE for me to read.
      If I want, I'll instruct you to read it. The `code-reviewer` subagent must give you the full path of the report
      it wrote. You must verify that it's a fresh report and not a previous one.
      If it did not write it correctly you should instruct it to do so again.

This approach should reduce the bloat in your context window, bringing in the most pertinent information, while not
losing any of the results.


## external tools

* When told to do external code analysis you can use the command line `uvx pyscn analyze --json --skip-deps .`
    * For a faster, more limited analysis, you can run the same analysis for a specific directory.
      For instance, to run the analysis only for the `flowers/app` directory,
      you can run `uvx pyscn analyze --json --skip-deps flowers/app` (this is an example from the flower project but it should be clear how to use it in this project)
    * In either case the results of the analysis is stored in a timestamped JSON file in the project's `.pyscn/reports`
      directory. After the analysis is complete - you can pick up the latest json file there, read it and see the results.
    