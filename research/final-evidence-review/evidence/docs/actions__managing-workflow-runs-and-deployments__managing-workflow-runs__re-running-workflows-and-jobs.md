# Re-running workflows and jobs

You can re-run a workflow run, all failed jobs in a workflow run, or specific jobs in a workflow run up to 30 days after its initial run.

Re-runs use the privileges of the actor who initially triggered the workflow, not the privileges of the actor who initiated the re-run. The workflow will also use the same `GITHUB_SHA` (commit SHA) and `GITHUB_REF` (git ref) of the original event that triggered the workflow run.

A workflow run can be re-run a maximum of 50 times. This limit includes both full re-runs and re-runs of a subset of jobs.

## Re-running all the jobs in a workflow

<div class="ghd-tool webui">

1. On GitHub, navigate to the main page of the repository.

2. Under your repository name, click **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-play" aria-label="play" role="img"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm4.879-2.773 4.264 2.559a.25.25 0 0 1 0 .428l-4.264 2.559A.25.25 0 0 1 6 10.559V5.442a.25.25 0 0 1 .379-.215Z"></path></svg> Actions**.

   ![Screenshot of the tabs for the "github/docs" repository. The "Actions" tab is highlighted with an orange outline.](/assets/images/help/repository/actions-tab-global-nav-update.png)

3. In the left sidebar, click the workflow you want to see.

   ![Screenshot of the left sidebar of the "Actions" tab. A workflow, "CodeQL," is outlined in dark orange.](/assets/images/help/actions/superlinter-workflow-sidebar.png)

4. From the list of workflow runs, click the name of the run to see the workflow run summary.

5. In the upper-right corner of the workflow, re-run jobs.

   * If any jobs failed, select the **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-sync" aria-label="sync" role="img"><path d="M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z"></path></svg> Re-run jobs** dropdown menu and click **Re-run all jobs**.
   * If no jobs failed, click **Re-run all jobs**.

6. Optionally, to enable runner diagnostic logging and step debug logging for the re-run, select **Enable debug logging**. For more information, see [Enabling debug logging](/en/actions/how-tos/monitor-workflows/enable-debug-logging).

7. Click **Re-run jobs**.

</div>

<div class="ghd-tool cli">

1. To re-run a failed workflow run, use the `run rerun` subcommand, replacing `RUN_ID` with the ID of the failed run that you want to re-run. If you don't specify a `run-id`, GitHub CLI returns an interactive menu for you to choose a recent failed run.

   ```shell copy
   gh run rerun RUN_ID
   ```

   To enable runner diagnostic logging and step debug logging for the re-run, use the `--debug` flag.

   ```shell copy
   gh run rerun RUN_ID --debug
   ```

2. To view the progress of the workflow run, use the `run watch` subcommand and select the run from the interactive list.

   ```shell copy
   gh run watch
   ```

</div>

## Re-running failed jobs in a workflow

<div class="ghd-tool webui">

1. On GitHub, navigate to the main page of the repository.
2. Under your repository name, click **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-play" aria-label="play" role="img"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm4.879-2.773 4.264 2.559a.25.25 0 0 1 0 .428l-4.264 2.559A.25.25 0 0 1 6 10.559V5.442a.25.25 0 0 1 .379-.215Z"></path></svg> Actions**.

   ![Screenshot of the tabs for the "github/docs" repository. The "Actions" tab is highlighted with an orange outline.](/assets/images/help/repository/actions-tab-global-nav-update.png)
3. In the left sidebar, click the workflow you want to see.

   ![Screenshot of the left sidebar of the "Actions" tab. A workflow, "CodeQL," is outlined in dark orange.](/assets/images/help/actions/superlinter-workflow-sidebar.png)
4. From the list of workflow runs, click the name of the run to see the workflow run summary.
5. In the upper-right corner of the workflow, select the **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-sync" aria-label="sync" role="img"><path d="M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z"></path></svg> Re-run jobs** dropdown menu, and click **Re-run failed jobs**.
6. Optionally, to enable runner diagnostic logging and step debug logging for the re-run, select **Enable debug logging**. For more information, see [Enabling debug logging](/en/actions/how-tos/monitor-workflows/enable-debug-logging).
7. Click **Re-run jobs**.

</div>

<div class="ghd-tool cli">

To re-run failed jobs in a workflow run, use the `run rerun` subcommand with the `--failed` flag. Replace `RUN_ID` with the ID of the run for which you want to re-run failed jobs. If you don't specify a `run-id`, GitHub CLI returns an interactive menu for you to choose a recent failed run.

```shell
gh run rerun RUN_ID --failed
```

To enable runner diagnostic logging and step debug logging for the re-run, use the `--debug` flag.

```shell
gh run rerun RUN_ID --failed --debug
```

</div>

## Re-running a specific job in a workflow

<div class="ghd-tool webui">

1. On GitHub, navigate to the main page of the repository.

2. Under your repository name, click **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-play" aria-label="play" role="img"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm4.879-2.773 4.264 2.559a.25.25 0 0 1 0 .428l-4.264 2.559A.25.25 0 0 1 6 10.559V5.442a.25.25 0 0 1 .379-.215Z"></path></svg> Actions**.

   ![Screenshot of the tabs for the "github/docs" repository. The "Actions" tab is highlighted with an orange outline.](/assets/images/help/repository/actions-tab-global-nav-update.png)

3. In the left sidebar, click the workflow you want to see.

   ![Screenshot of the left sidebar of the "Actions" tab. A workflow, "CodeQL," is outlined in dark orange.](/assets/images/help/actions/superlinter-workflow-sidebar.png)

4. From the list of workflow runs, click the name of the run to see the workflow run summary.

5. Under the "Jobs" section of the left sidebar, next to the job that you want to re-run, click <svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-sync" aria-label="The re-run icon" role="img"><path d="M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z"></path></svg>.

6. Optionally, to enable runner diagnostic logging and step debug logging for the re-run, select **Enable debug logging**. For more information, see [Enabling debug logging](/en/actions/how-tos/monitor-workflows/enable-debug-logging).

7. Click **Re-run jobs**.

</div>

<div class="ghd-tool cli">

To re-run a specific job in a workflow run, use the `run rerun` subcommand with the `--job` flag. Replace `JOB_ID` with the ID of the job that you want to re-run.

```shell
gh run rerun --job JOB_ID
```

To enable runner diagnostic logging and step debug logging for the re-run, use the `--debug` flag.

```shell
gh run rerun --job JOB_ID --debug
```

</div>

## Reviewing previous workflow runs

1. On GitHub, navigate to the main page of the repository.
2. Under your repository name, click **<svg version="1.1" width="16" height="16" viewBox="0 0 16 16" class="octicon octicon-play" aria-label="play" role="img"><path d="M8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Zm4.879-2.773 4.264 2.559a.25.25 0 0 1 0 .428l-4.264 2.559A.25.25 0 0 1 6 10.559V5.442a.25.25 0 0 1 .379-.215Z"></path></svg> Actions**.

   ![Screenshot of the tabs for the "github/docs" repository. The "Actions" tab is highlighted with an orange outline.](/assets/images/help/repository/actions-tab-global-nav-update.png)
3. In the left sidebar, click the workflow you want to see.

   ![Screenshot of the left sidebar of the "Actions" tab. A workflow, "CodeQL," is outlined in dark orange.](/assets/images/help/actions/superlinter-workflow-sidebar.png)
4. From the list of workflow runs, click the name of the run to see the workflow run summary.
5. To the right of the run name, select the **Latest** dropdown menu and click a previous run attempt.