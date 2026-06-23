2026-06-19
add devel scripts for making github releases
add skill for release/version history
add skill for automated plan review back and forth
add tests/ script to add links for files in the repo
add mechanism for using .github like deploy_pages.yml


2026-05-21: Rejected audit-suffixed date headings; use audit-labeled bullets instead. See docs/CHANGELOG.md under ## 2026-05-21 / ### Decisions and Failures.

devel/bump_version.py = pre-existing helper. Could wire into check_version_freshness() later as auto-bump option (currently plan non-goal). Worth a future follow-on plan.

commit_changelog.py takes all changes for the day, including ones from a previous submission
